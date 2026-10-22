"""Finding plugins, loading them, and running their functions when events come.

Two places, in this order:

1. Folders under `<data dir>/plugins/`, sorted by name (case ignored). Each holds a
   `videoforge-plugin.toml`; its `module` is imported from that folder only (a module of that name
   already loaded from somewhere else is refused), and a `vendor/` folder in it, when there is one,
   goes on the import path after VideoForge's own (for the packages it brings along).
2. Installed packages' `videoforge.plugins` entry points, sorted by name (the name is the id).

An id taken by an earlier plugin fails the later one: the plugin the user put in the folder wins over
an installed one. A plugin switched off on the Settings page isn't imported at all (that is the way to
step around one that breaks VideoForge as it loads), so switching takes effect on the next start.
Anything that goes wrong is a failure in the report, shown on the Settings page; it never stops the app.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
from functools import partial
from importlib import machinery, metadata, util
import logging
from pathlib import Path
import sys
import threading
from typing import Any

from videoforge.core.events import EventBus
from videoforge.plugins import API_VERSION, Hook, Plugin, PluginContext
from videoforge.plugins.manifest import MANIFEST, Manifest, PluginError, read_manifest

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "videoforge.plugins"
VENDOR = "vendor"


@dataclass(frozen=True, slots=True)
class LoadedPlugin:
    id: str
    plugin: Plugin
    source: str  # its folder, or "entry point <module:object>"


@dataclass(frozen=True, slots=True)
class PluginFailure:
    source: str
    reason: str
    id: str | None = None


@dataclass(frozen=True, slots=True)
class SkippedPlugin:
    """Switched off on the Settings page: found, not imported."""

    id: str
    source: str


@dataclass(frozen=True, slots=True)
class PluginReport:
    loaded: tuple[LoadedPlugin, ...] = ()
    failures: tuple[PluginFailure, ...] = ()
    disabled: tuple[SkippedPlugin, ...] = ()


def load_plugins(folder: Path | None, disabled: Collection[str] = ()) -> PluginReport:
    loaded: list[LoadedPlugin] = []
    failures: list[PluginFailure] = []
    skipped: list[SkippedPlugin] = []
    taken: set[str] = set()

    def add(pid: str, source: str, load: Callable[[], Plugin]) -> None:
        if not pid or pid in {".", ".."} or any(c in pid for c in "/\\:\0"):
            failures.append(PluginFailure(source, "Plugin id must be a single folder name", pid))
            return
        if pid.casefold() in taken:
            failures.append(PluginFailure(source, f"The id {pid!r} is taken by a plugin loaded before it", pid))
            return
        taken.add(pid.casefold())
        if pid in disabled:
            skipped.append(SkippedPlugin(pid, source))
            return
        try:
            plugin = load()
            if not isinstance(plugin, Plugin):
                raise PluginError(f"It must export a videoforge.plugins.Plugin, not {type(plugin).__name__}")
            if plugin.api_version > API_VERSION:
                raise PluginError(
                    f"It needs plugin API {plugin.api_version}; this VideoForge has {API_VERSION} (update VideoForge)"
                )
        except SystemExit as ex:
            failures.append(PluginFailure(source, f"It exited while loading: {ex}", pid))
        except Exception as ex:
            logger.exception("Plugin %s failed to load", source)
            failures.append(PluginFailure(source, str(ex) or type(ex).__name__, pid))
        else:
            loaded.append(LoadedPlugin(pid, plugin, source))

    for root in _folders(folder):
        manifest = root / MANIFEST
        if not manifest.is_file():
            continue
        try:
            m = read_manifest(manifest)
        except PluginError as ex:
            failures.append(PluginFailure(str(root), str(ex)))
            continue
        add(m.id, str(root), lambda m=m, root=root: _load_folder(root, m))

    for ep in sorted(metadata.entry_points(group=ENTRY_POINT_GROUP), key=lambda e: e.name):
        add(ep.name, f"entry point {ep.value}", ep.load)

    if loaded:
        logger.info("Plugins: %s", ", ".join(f"{p.id} {p.plugin.version}".rstrip() for p in loaded))
    return PluginReport(tuple(loaded), tuple(failures), tuple(skipped))


def _folders(folder: Path | None) -> list[Path]:
    if folder is None:
        return []
    try:
        folder.mkdir(parents=True, exist_ok=True)
        return sorted((p for p in folder.iterdir() if p.is_dir()), key=lambda p: p.name.casefold())
    except OSError as ex:
        logger.warning("Can't read the plugins folder %s: %s", folder, ex)
        return []


def _load_folder(root: Path, m: Manifest) -> Any:
    existing = sys.modules.get(m.module)
    if existing is not None:
        file = getattr(existing, "__file__", None)
        if file is None or not _is_below(Path(file), root):
            raise PluginError(f"A module named {m.module!r} is already loaded from somewhere else; rename it")
        module = existing
    else:
        spec = machinery.PathFinder.find_spec(m.module, [str(root)])
        if spec is None or spec.loader is None or spec.origin is None:
            raise PluginError(f"No module {m.module!r} in {root}")
        vendor = root / VENDOR
        if vendor.is_dir() and str(vendor) not in sys.path:
            sys.path.append(str(vendor))  # after VideoForge's own packages: a plugin can't replace them
        module = util.module_from_spec(spec)
        sys.modules[m.module] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(m.module, None)
            raise
    try:
        return getattr(module, m.object)
    except AttributeError:
        raise PluginError(f"{m.module} has no {m.object!r}") from None


def _is_below(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


# --- running them ----------------------------------------------------------------------------


class PluginHost:
    """The loaded plugins on the event bus: each has a thread of its own, its calls in event order."""

    def __init__(
        self,
        report: PluginReport,
        bus: EventBus,
        *,
        data_dir: Path,
        settings: Mapping[str, Mapping[str, Any]] | None = None,
        job_log: Callable[[str, str], None] | None = None,
    ) -> None:
        self.report = report
        self.failures: dict[str, str] = {}
        self.setup_failed: set[str] = set()
        self._failure_lock = threading.Lock()
        self._pools: dict[str, ThreadPoolExecutor] = {}
        self._unsubscribe: list[Callable[[], None]] = []
        for p in report.loaded:
            ctx = PluginContext(
                id=p.id,
                data_dir=data_dir / p.id,
                settings=deepcopy(dict((settings or {}).get(p.id, {}))),
                log=logging.getLogger(f"videoforge.plugin.{p.id}"),
                job_log=job_log or (lambda _job, _line: None),
            )
            pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"plugin-{p.id}")
            self._pools[p.id] = pool
            pool.submit(self._call, p.id, "setup", partial(_setup, ctx, p.plugin.setup, p.source))
            for kind, hook in p.plugin.hooks().items():
                self._unsubscribe.append(bus.subscribe(self._submitter(p.id, hook, ctx), kind, name=f"plugin {p.id}"))

    def _submitter(self, pid: str, hook: Hook, ctx: PluginContext) -> Callable[[Any], None]:
        pool = self._pools[pid]

        def submit(event: Any) -> None:
            snapshot = deepcopy(event)

            def run() -> None:
                if not self._call(pid, type(event).__name__, lambda: hook(snapshot, ctx)):
                    spec = getattr(snapshot, "spec", None)
                    if spec is not None:
                        ctx.job_log(spec.id, f"Plugin {pid} failed on {type(event).__name__}; see the application log")

            pool.submit(run)

        return submit

    def _call(self, pid: str, what: str, fn: Callable[[], object]) -> bool:
        if what != "setup" and pid in self.setup_failed:
            return True  # setup failure is already reported; don't call an uninitialised plugin
        try:
            fn()
        except (Exception, SystemExit) as ex:  # plugin exits must not kill its worker
            with self._failure_lock:
                self.failures[pid] = f"{what}: {str(ex) or type(ex).__name__}"
                if what == "setup":
                    self.setup_failed.add(pid)
            logger.exception("Plugin %s failed on %s", pid, what)
            return False
        return True

    def wait(self) -> None:
        """Until every plugin call made so far has returned."""
        for pool in self._pools.values():
            pool.submit(lambda: None).result()

    def close(self) -> None:
        for unsubscribe in self._unsubscribe:
            unsubscribe()
        for pool in self._pools.values():
            pool.shutdown(wait=False)


def _setup(ctx: PluginContext, setup: Callable[[PluginContext], object] | None, source: str = "") -> None:
    manifest = Path(source) / MANIFEST
    if manifest.is_file():
        read_manifest(manifest).validate_settings(dict(ctx.settings))
    ctx.data_dir.mkdir(parents=True, exist_ok=True)
    if setup is not None:
        setup(ctx)


def describe(report: PluginReport, disabled: Iterable[str]) -> dict[str, Any]:
    """The Settings page's view of the plugins."""
    off = set(disabled)
    return {
        "loaded": [
            {
                "id": p.id,
                "name": p.plugin.name,
                "version": p.plugin.version,
                "description": p.plugin.description,
                "source": p.source,
                "events": [t.__name__ for t in p.plugin.hooks()],
                "enabled": p.id not in off,
            }
            for p in report.loaded
        ],
        "disabled": [{"id": s.id, "source": s.source, "enabled": s.id not in off} for s in report.disabled],
        "failures": [{"id": f.id, "source": f.source, "reason": f.reason} for f in report.failures],
    }
