"""Profile registry: every installed `videoforge.profiles` entry point (id = "module:Class").

VideoForge registers its built-in `manual` profile there; a group's profile is a
separate package that registers its own entry in its pyproject.toml:

    [project.entry-points."videoforge.profiles"]
    mygroup = "videoforge_mygroup:MyGroupProfile"
"""

from __future__ import annotations

from functools import cache
import importlib
from importlib.metadata import entry_points

from videoforge.core.profile import Profile

ENTRY_POINT_GROUP = "videoforge.profiles"
BUILTIN = "manual"
_BUILTINS = {BUILTIN: "videoforge.profiles.manual:ManualProfile"}


class UnknownProfile(KeyError):
    pass


@cache
def registry() -> dict[str, str]:
    """Profile id -> "module:Class"; the built-in first, then the installed ones by id."""
    found = {ep.name: ep.value for ep in entry_points(group=ENTRY_POINT_GROUP)}
    found.update(_BUILTINS)  # also present when running from a checkout that was never installed
    return {pid: found[pid] for pid in sorted(found, key=lambda p: (p not in _BUILTINS, p))}


def profile_ids() -> list[str]:
    return list(registry())


def default_profile_id(configured: str | None, ids: list[str] | None = None) -> str:
    """The configured default (videoforge.toml `profile`) when it is one of ids, else the built-in."""
    ids = ids or profile_ids()
    if configured in ids:
        return configured
    return BUILTIN if BUILTIN in ids else ids[0]


@cache
def get_profile(profile_id: str) -> Profile:
    try:
        target = registry()[profile_id]
    except KeyError:
        raise UnknownProfile(f"Unknown profile {profile_id!r}; installed: {', '.join(registry())}") from None
    module, _, cls = target.partition(":")
    return getattr(importlib.import_module(module), cls)()
