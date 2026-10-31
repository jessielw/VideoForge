"""Rule set registry: every installed `videoforge.rule_sets` entry point (id = "module:Class").

VideoForge registers its built-in `manual` rule set there; a group's rule set is a
separate package that registers its own entry in its pyproject.toml:

    [project.entry-points."videoforge.rule_sets"]
    mygroup = "videoforge_mygroup:MyGroupRuleSet"
"""

from __future__ import annotations

from functools import cache
import importlib
from importlib.metadata import entry_points

from videoforge.core.rule_set import RuleSet

ENTRY_POINT_GROUP = "videoforge.rule_sets"
BUILTIN = "manual"
_BUILTINS = {BUILTIN: "videoforge.rule_sets.manual:ManualRuleSet"}


class UnknownRuleSet(KeyError):
    pass


@cache
def registry() -> dict[str, str]:
    """Rule set id -> "module:Class"; the built-in first, then the installed ones by id."""
    found = {ep.name: ep.value for ep in entry_points(group=ENTRY_POINT_GROUP)}
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
