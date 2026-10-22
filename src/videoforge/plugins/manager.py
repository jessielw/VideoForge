"""Offline ZIP installation, manifest inventory, and restart-time directory transactions."""

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
from importlib import metadata
import io
import json
import logging
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import threading
from typing import Any
from uuid import uuid4
import zipfile
import zlib

from videoforge.plugins.loader import ENTRY_POINT_GROUP, PluginHost
from videoforge.plugins.manifest import (
    MANIFEST,
    RESERVED,
    Manifest,
    PluginError,
    parse_manifest,
    read_manifest,
    safe_id,
)

MAX_ZIP_BYTES = 50 * 1024 * 1024
MAX_EXTRACTED_BYTES = 250 * 1024 * 1024
MAX_ENTRIES = 5000
logger = logging.getLogger(__name__)


class PluginConflict(PluginError):
    """The user must preview the current installation again."""


def _safe_parts(name: str) -> tuple[str, ...]:
    parts = name.rstrip("/").split("/")
    if (
        not name
        or name.startswith("/")
        or any(
            not p
            or p in {".", ".."}
            or p.endswith((".", " "))
            or any(c in p for c in '\\:<>"|?*')
            or any(ord(c) < 32 for c in p)
            or p.split(".")[0].casefold() in RESERVED
            for p in parts
        )
    ):
        raise PluginError(f"Unsafe archive path: {name!r}")
    return tuple(parts)


@dataclass
class Package:
    manifest: Manifest
    files: dict[str, bytes]


def read_package(raw: bytes) -> Package:
    """Read bounded file contents, checking CRCs even for preview; no code is evaluated."""
    if len(raw) > MAX_ZIP_BYTES:
        raise PluginError("Plugin ZIP files must be 50 MiB or smaller")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ENTRIES:
                raise PluginError("A plugin ZIP can contain at most 5,000 entries")
            seen: dict[str, bool] = {}
            spellings: dict[str, str] = {}
            total = 0
            files: dict[str, bytes] = {}
            for entry in entries:
                parts = _safe_parts(entry.orig_filename)
                path = "/".join(parts)
                key = path.casefold()
                for index in range(1, len(parts) + 1):
                    prefix = "/".join(parts[:index])
                    previous = spellings.setdefault(prefix.casefold(), prefix)
                    if previous != prefix:
                        raise PluginError(f"Archive paths collide on Windows: {prefix}")
                mode = entry.external_attr >> 16
                if entry.flag_bits & 1 or stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}:
                    raise PluginError("Encrypted files and links are not supported")
                if key in seen:
                    raise PluginError(f"Duplicate archive path: {path}")
                seen[key] = entry.is_dir()
                if entry.is_dir():
                    continue
                total += entry.file_size
                if total > MAX_EXTRACTED_BYTES:
                    raise PluginError("Extracted plugin files must be 250 MiB or smaller")
                with archive.open(entry) as stream:
                    content = stream.read(min(entry.file_size, MAX_EXTRACTED_BYTES) + 1)
                if len(content) != entry.file_size:
                    raise PluginError("Invalid extracted file size")
                files[path] = content
            for key in seen:
                for parent in PurePosixPath(key).parents:
                    if str(parent) in seen and not seen[str(parent)]:
                        raise PluginError("An archive file is also used as a directory")
            roots = [p for p in files if PurePosixPath(p).name == MANIFEST]
            if len(roots) != 1:
                raise PluginError(f"A plugin ZIP needs exactly one {MANIFEST}")
            manifest_path = PurePosixPath(roots[0])
            prefix = "" if str(manifest_path.parent) == "." else f"{manifest_path.parent}/"
            if len(manifest_path.parts) > 2 or any(not p.startswith(prefix) for p in files):
                raise PluginError("Put the plugin at the ZIP root or inside one enclosing folder")
            manifest = parse_manifest(files[str(manifest_path)].decode("utf-8"), package=True)
            files = {p[len(prefix) :]: data for p, data in files.items()}
            if f"{manifest.module}.py" not in files and f"{manifest.module}/__init__.py" not in files:
                raise PluginError(f"No module {manifest.module!r} in the ZIP")
            return Package(manifest, files)
    except (zipfile.BadZipFile, UnicodeError, OSError, RuntimeError, NotImplementedError, EOFError, zlib.error) as ex:
        raise PluginError(f"Invalid plugin ZIP: {ex}") from None


def _plain_directory(path: Path, parent: Path) -> None:
    """Managed operations cannot traverse symlinks or Windows directory junctions."""
    if path.is_symlink() or path.is_junction() or path.resolve().parent != parent.resolve():
        raise PluginError(f"Unsafe plugin directory: {path.name}")


def _revision(root: Path | None) -> str:
    if root is None:
        return "absent"
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or path.is_junction():
            raise PluginError("Managed plugins cannot contain links or junctions")
        if path.is_file():
            relative = path.relative_to(root)
            if "__pycache__" in relative.parts:
                continue
            digest.update(str(relative).replace("\\", "/").encode())
            digest.update(b"\0")
            with path.open("rb") as stream:
                while block := stream.read(1024 * 1024):
                    digest.update(block)
    return digest.hexdigest()


class PluginManager:
    def __init__(self, data_dir: Path):
        self.folder = data_dir / "plugins"
        self.staging = data_dir / "plugin-staging"
        self.lock = threading.RLock()
        self.startup_failures: list[str] = []

    def _folders(self) -> list[Path]:
        if not self.folder.exists():
            return []
        _plain_directory(self.folder, self.folder.parent)
        return sorted((p for p in self.folder.iterdir() if p.is_dir()), key=lambda p: p.name.casefold())

    def installed(self) -> dict[str, tuple[Path, Manifest]]:
        result = {}
        for root in self._folders():
            try:
                _plain_directory(root, self.folder)
                manifest = read_manifest(root / MANIFEST)
                if manifest.id.casefold() in result:
                    raise PluginError(f"Duplicate plugin id: {manifest.id}")
                result[manifest.id.casefold()] = (root, manifest)
            except PluginError:
                continue  # the loader's report displays malformed or duplicate manifests
        return result

    def pending(self) -> list[tuple[Path, dict]]:
        if not self.staging.exists():
            return []
        _plain_directory(self.staging, self.staging.parent)
        operations = []
        for root in sorted(self.staging.iterdir()):
            if root.name.startswith(".") or not root.is_dir():
                continue
            _plain_directory(root, self.staging)
            try:
                value = json.loads((root / "operation.json").read_text(encoding="utf-8"))
                if (
                    not isinstance(value, dict)
                    or set(value) != {"id", "kind", "target"}
                    or any(not isinstance(v, str) for v in value.values())
                ):
                    raise PluginError("Invalid staged operation metadata")
                safe_id(value["id"])
                if value["kind"] not in {"install", "remove"} or len(_safe_parts(value["target"])) != 1:
                    raise PluginError("Invalid staged operation")
                operations.append((root, value))
            except (OSError, ValueError, KeyError, TypeError) as ex:
                raise PluginError(f"Can't read staged plugin operation {root.name}: {ex}") from None
        return operations

    def _target(self, pid: str) -> tuple[Path | None, Manifest | None]:
        safe_id(pid)
        found = self.installed().get(pid.casefold())
        if found:
            return found
        # Do not overwrite an unrecognised directory, or shadow an installed entry point.
        if (self.folder.exists() and any(p.name.casefold() == pid.casefold() for p in self.folder.iterdir())) or any(
            ep.name.casefold() == pid.casefold() for ep in metadata.entry_points(group=ENTRY_POINT_GROUP)
        ):
            raise PluginConflict(f"The id {pid!r} belongs to an unmanaged plugin or directory")
        return None, None

    def _available(self, pid: str) -> None:
        if any(op["id"].casefold() == pid.casefold() for _, op in self.pending()):
            raise PluginConflict("This plugin already has a pending change; restart VideoForge first")

    def preview(self, package: Package) -> dict[str, Any]:
        with self.lock:
            self._available(package.manifest.id)
            root, current = self._target(package.manifest.id)
            return {
                "plugin": package.manifest.metadata(),
                "current": current.metadata() if current else None,
                "revision": _revision(root),
            }

    @contextmanager
    def _transaction(self):
        self.staging.mkdir(parents=True, exist_ok=True)
        _plain_directory(self.staging, self.staging.parent)
        temporary = Path(tempfile.mkdtemp(prefix=".tmp-", dir=self.staging))
        try:
            yield temporary
            temporary.rename(self.staging / uuid4().hex)
        finally:
            if temporary.exists():
                _plain_directory(temporary, self.staging)
                shutil.rmtree(temporary)

    def stage_install(self, package: Package, revision: str, *, replace: bool = False) -> None:
        with self.lock:
            preview = self.preview(package)
            if revision != preview["revision"]:
                raise PluginConflict("The installed plugin changed; preview the ZIP again")
            if preview["current"] and not replace:
                raise PluginConflict("A plugin with this id is installed; explicitly choose Replace")
            root, current = self._target(package.manifest.id)
            pid = current.id if current else package.manifest.id
            if current and current.id != package.manifest.id:
                raise PluginConflict("Replacement must preserve the exact plugin id, including letter case")
            target = root.name if root else pid
            with self._transaction() as temporary:
                incoming = temporary / "new"
                incoming.mkdir()
                for name, data in package.files.items():
                    destination = incoming.joinpath(*_safe_parts(name))
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(data)
                (temporary / "operation.json").write_text(
                    json.dumps({"id": pid, "target": target, "kind": "install"}), encoding="utf-8"
                )

    def stage_remove(self, pid: str, revision: str) -> None:
        with self.lock:
            self._available(pid)
            root, manifest = self._target(pid)
            if root is None or manifest is None:
                raise PluginError("No removable folder plugin with this id")
            if revision != _revision(root):
                raise PluginConflict("The plugin changed; refresh its details before removing it")
            with self._transaction() as temporary:
                (temporary / "operation.json").write_text(
                    json.dumps({"id": manifest.id, "target": root.name, "kind": "remove"}), encoding="utf-8"
                )

    def apply_pending(self) -> None:
        """Idempotent across a process exit between any two directory renames."""
        with self.lock:
            try:
                operations = self.pending()
            except (PluginError, OSError) as ex:
                self.startup_failures.append(str(ex))
                return
            # A completed rename is the commit point. Retry interrupted cleanup on the next start.
            if self.staging.exists():
                for abandoned in self.staging.iterdir():
                    if abandoned.name.startswith((".done-", ".tmp-")) and abandoned.is_dir():
                        try:
                            _plain_directory(abandoned, self.staging)
                            shutil.rmtree(abandoned)
                        except (OSError, PluginError):
                            logger.warning("Couldn't clean up old plugin transaction %s", abandoned.name)
            for operation, value in operations:
                target = self.folder / value["target"]
                incoming, old = operation / "new", operation / "old"
                try:
                    self.folder.mkdir(parents=True, exist_ok=True)
                    _plain_directory(self.folder, self.folder.parent)
                    for path in (target, incoming, old):
                        _plain_directory(path, path.parent)
                    if value["kind"] == "install":
                        if incoming.exists():
                            if read_manifest(incoming / MANIFEST).id != value["id"]:
                                raise PluginError("Staged plugin id does not match the operation")
                            if target.exists():
                                if old.exists():
                                    raise PluginError(
                                        "Both the current and recovery folders exist; resolve the conflict"
                                    )
                                target.rename(old)
                            incoming.rename(target)
                        elif not target.exists():
                            if old.exists():
                                old.rename(target)
                            raise PluginError(
                                "Incoming plugin files are missing; previous files restored when available"
                            )
                    elif target.exists():
                        if old.exists():
                            raise PluginError("Removal has both current and recovery folders; resolve the conflict")
                        target.rename(old)
                    # Mark committed before cleanup: interrupted deletion must never look pending.
                    completed = operation.with_name(f".done-{operation.name}")
                    operation.rename(completed)
                    try:
                        _plain_directory(completed, self.staging)
                        shutil.rmtree(completed)
                    except (OSError, PluginError):
                        logger.warning("Plugin change applied; cleanup will be retried for %s", value["id"])
                except (OSError, PluginError) as ex:
                    if not target.exists() and old.exists():
                        try:
                            old.rename(target)
                        except OSError:
                            logger.exception("Couldn't restore previous plugin %s", value["id"])
                    self.startup_failures.append(f"{value['id']}: {ex}")
                    logger.exception("Couldn't apply pending plugin change for %s", value["id"])

    def effective_settings(self, base: dict, overrides: dict) -> dict:
        result = {pid: dict(values) for pid, values in base.items()}
        for pid, values in overrides.items():
            result[pid] = result.get(pid, {}) | values
        try:
            installed = self.installed()
        except (PluginError, OSError) as ex:
            self.startup_failures.append(f"Can't inspect plugin defaults: {ex}")
            installed = {}
        for _, manifest in installed.values():
            result[manifest.id] = manifest.effective(base.get(manifest.id, {}), overrides.get(manifest.id, {}))
        return result

    def inventory(self, host: PluginHost, disabled: list[str], base: dict, overrides: dict) -> dict:
        with self.lock:
            pending = self.pending()
            installed = self.installed()
            loaded = {p.id: p for p in host.report.loaded}
            errors = {f.id: f.reason for f in host.report.failures if f.id}
            entries = {}
            for root, manifest in installed.values():
                try:
                    revision = _revision(root)
                    safe_id(manifest.id)
                    removable = True
                except PluginError:
                    revision, removable = "", False
                entries[manifest.id] = self._entry(manifest, base, overrides) | {
                    "source": str(root),
                    "removable": removable,
                    "revision": revision,
                    "pending": None,
                }
                active = loaded.get(manifest.id)
                if active:
                    for field in ("name", "version", "description"):
                        if not getattr(manifest, field):
                            entries[manifest.id][field] = getattr(active.plugin, field)
            for operation_root, operation in pending:
                pid = operation["id"]
                if operation["kind"] == "install":
                    incoming = operation_root / "new" / MANIFEST
                    if incoming.exists():
                        manifest = read_manifest(incoming)
                        entries[pid] = (
                            entries.get(pid, {})
                            | self._entry(manifest, base, overrides)
                            | {
                                "source": str(self.folder / operation["target"]),
                                "removable": False,
                                "revision": "",
                                "pending": "install" if pid not in entries else "replace",
                            }
                        )
                if pid in entries:
                    entries[pid]["pending"] = entries[pid].get("pending") or "remove"
            for p in host.report.loaded:
                entries.setdefault(
                    p.id,
                    {
                        "id": p.id,
                        "name": p.plugin.name,
                        "version": p.plugin.version,
                        "description": p.plugin.description,
                        "source": p.source,
                        "settings": [],
                        "values": {},
                        "configured_passwords": [],
                        "removable": False,
                        "revision": "",
                        "pending": None,
                    },
                )
            for p in host.report.disabled:
                entries.setdefault(
                    p.id,
                    {
                        "id": p.id,
                        "name": p.id,
                        "version": "",
                        "description": "",
                        "source": p.source,
                        "settings": [],
                        "values": {},
                        "configured_passwords": [],
                        "removable": False,
                        "revision": "",
                        "pending": None,
                    },
                )
            for pid, item in entries.items():
                active = loaded.get(pid)
                item.update(
                    enabled=pid not in disabled,
                    running=active is not None and pid not in host.setup_failed,
                    running_version=active.plugin.version if active else None,
                    events=[t.__name__ for t in active.plugin.hooks()] if active else [],
                    error=errors.get(pid) or host.failures.get(pid),
                )
            return {
                "folder": str(self.folder),
                "items": sorted(entries.values(), key=lambda p: p["id"].casefold()),
                "failures": [f"{f.id or f.source}: {f.reason}" for f in host.report.failures if f.id not in entries]
                + self.startup_failures,
            }

    @staticmethod
    def _entry(manifest: Manifest, base: dict, overrides: dict) -> dict:
        values = manifest.effective(base.get(manifest.id, {}), overrides.get(manifest.id, {}))
        secrets = {s.key for s in manifest.settings if s.type == "password"}
        fields = manifest.metadata()["settings"]
        for setting in fields:
            if setting["type"] == "password":
                setting["default"] = None
        return {
            "id": manifest.id,
            "name": manifest.name or manifest.id,
            "version": manifest.version,
            "description": manifest.description,
            "settings": fields,
            "values": {s.key: values[s.key] for s in manifest.settings if s.key in values and s.key not in secrets},
            "configured_passwords": [key for key in secrets if values.get(key)],
        }

    def settings_manifest(self, pid: str) -> Manifest:
        for root, operation in self.pending():
            if operation["id"] == pid and operation["kind"] == "install" and (root / "new" / MANIFEST).exists():
                return read_manifest(root / "new" / MANIFEST)
        found = self.installed().get(pid.casefold())
        if found and found[1].id == pid:
            return found[1]
        raise PluginError("No folder plugin with this id")
