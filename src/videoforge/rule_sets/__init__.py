"""Rule set registry: every installed `videoforge.rule_sets` entry point (id = "module:Class").

VideoForge registers its built-in `manual` rule set there; a group's rule set is a
separate package that registers its own entry in its pyproject.toml:

    [project.entry-points."videoforge.rule_sets"]
    mygroup = "videoforge_mygroup:MyGroupRuleSet"

A rule set can also be a folder in the plugins folder (Settings > Plugins > Install ZIP), for
installs where packages can't be added (portable, Docker). Its videoforge-plugin.toml names the
class instead of an event plugin object:

    id = "mygroup"
    module = "videoforge_mygroup"
    rule_set = "MyGroupRuleSet"

The folder (and its `vendor/`, for pure-Python dependencies) goes on the import path after
VideoForge's own packages. The built-in wins an id, then the plugins folder, then entry points.
"""

from __future__ import annotations

from collections.abc import Collection
from functools import cache
import importlib
from importlib.metadata import entry_points
import logging
from pathlib import Path
import sys

from videoforge.core.rule_set import RuleSet
from videoforge.plugins.loader import VENDOR, _is_below
from videoforge.plugins.manifest import MANIFEST, PluginError, read_manifest

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "videoforge.rule_sets"
BUILTIN = "manual"
_BUILTINS = {BUILTIN: "videoforge.rule_sets.manual:ManualRuleSet"}

_folder: Path | None = None
_disabled: frozenset[str] = frozenset()
_failures: dict[str, str] = {}


class UnknownRuleSet(KeyError):
    pass


def use_folder(folder: Path | None, disabled: Collection[str] = ()) -> None:
    """Look for folder rule sets in `folder` (the plugins folder); `disabled` ids are skipped.
    Call before the registry is read (it is cached)."""
    global _folder, _disabled
    _folder, _disabled = folder, frozenset(disabled)
    registry.cache_clear()
    get_rule_set.cache_clear()


def folder_failures() -> dict[str, str]:
    """Folder rule sets that couldn't be registered: id -> why."""
    registry()
    return dict(_failures)


def _folder_rule_sets() -> dict[str, str]:
    _failures.clear()
    found: dict[str, str] = {}
    if _folder is None or not _folder.is_dir():
        return found
    try:
        roots = sorted((p for p in _folder.iterdir() if p.is_dir()), key=lambda p: p.name.casefold())
    except OSError as ex:
        logger.warning("Can't read the plugins folder %s: %s", _folder, ex)
        return found
    for root in roots:
        if not (root / MANIFEST).is_file():
            continue
        try:
            m = read_manifest(root / MANIFEST)
        except PluginError as ex:
            logger.warning("Plugin manifest in %s: %s", root, ex)
            continue
        if not m.rule_set or m.id in _disabled:
            continue
        if m.id.casefold() in {i.casefold() for i in found}:
            _failures[m.id] = f"The id {m.id!r} is taken by a rule set loaded before it"
            continue
        existing = sys.modules.get(m.module)
        if existing is not None and not _is_below(Path(getattr(existing, "__file__", None) or "/"), root):
            _failures[m.id] = f"A module named {m.module!r} is already loaded from somewhere else; rename it"
            continue
        for path in (root, root / VENDOR):
            if path.is_dir() and str(path) not in sys.path:
                sys.path.append(str(path))  # after VideoForge's own packages: it can't replace them
        found[m.id] = f"{m.module}:{m.rule_set}"
    return found


@cache
def registry() -> dict[str, str]:
    """Rule set id -> "module:Class"; the built-in first, then the installed ones by id."""
    found = {ep.name: ep.value for ep in entry_points(group=ENTRY_POINT_GROUP)}
    found.update(_folder_rule_sets())
    found.update(_BUILTINS)  # also present when running from a checkout that was never installed
    return {pid: found[pid] for pid in sorted(found, key=lambda p: (p not in _BUILTINS, p))}


def rule_set_ids() -> list[str]:
    return list(registry())


def default_rule_set_id(configured: str | None, ids: list[str] | None = None) -> str:
    """The configured default (videoforge.toml `rule_set`) when it is one of ids, else the built-in."""
    ids = ids or rule_set_ids()
    if configured in ids:
        return configured
    return BUILTIN if BUILTIN in ids else ids[0]


@cache
def get_rule_set(rule_set_id: str) -> RuleSet:
    try:
        target = registry()[rule_set_id]
    except KeyError:
        raise UnknownRuleSet(f"Unknown rule set {rule_set_id!r}; installed: {', '.join(registry())}") from None
    module, _, cls = target.partition(":")
    return getattr(importlib.import_module(module), cls)()
