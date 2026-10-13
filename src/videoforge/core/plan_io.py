"""Plans to and from JSON (plan.json), shared by the CLI and the GUI.

The models are plain dataclasses, so one type-driven codec covers them all:
paths are strings, enums are their values, a Layout is "5.1", and frozensets
are sorted lists. Fields missing from an older file fall back to their defaults.
Version 1 files (per-subtitle forced/sdh/dub overrides) are upgraded on load.
"""

from __future__ import annotations

import dataclasses
import json
import types
import typing
from enum import Enum
from functools import cache
from pathlib import Path
from typing import Any

from videoforge.core.models import Layout, Plan

FORMAT_VERSION = 2
_V1_SUB_FLAGS = ("forced", "sdh", "dub")


class PlanFormatError(ValueError):
    pass


@cache
def _hints(cls: type) -> dict[str, Any]:
    return typing.get_type_hints(cls)


def to_json(value: Any) -> Any:
    """A dataclass tree as JSON-ready values (also used by core.history)."""
    if isinstance(value, Layout):
        return str(value)
    if dataclasses.is_dataclass(value):
        return {f.name: to_json(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, frozenset):
        return sorted(to_json(v) for v in value)
    if isinstance(value, list):
        return [to_json(v) for v in value]
    if isinstance(value, dict):
        return {k: to_json(v) for k, v in value.items()}
    return value


def from_json(tp: Any, value: Any) -> Any:
    """The inverse of to_json, driven by the type hints of tp."""
    origin = typing.get_origin(tp)
    args = typing.get_args(tp)
    if origin in (typing.Union, types.UnionType):
        if value is None:
            return None
        (inner,) = [a for a in args if a is not type(None)]
        return from_json(inner, value)
    if origin is list:
        return [from_json(args[0], v) for v in value]
    if origin is frozenset:
        return frozenset(from_json(args[0], v) for v in value)
    if origin is dict:
        return {from_json(args[0], k): from_json(args[1], v) for k, v in value.items()}
    if tp is int and isinstance(value, str):  # a JSON object key
        return int(value)
    if tp is Layout:
        return Layout.parse(value)
    if tp is Path:
        return Path(value)
    if isinstance(tp, type) and issubclass(tp, Enum):
        return tp(value)
    if dataclasses.is_dataclass(tp):
        hints = _hints(tp)
        names = {f.name for f in dataclasses.fields(tp)}
        return tp(**{k: from_json(hints[k], v) for k, v in value.items() if k in names})
    return value


def plan_to_dict(plan: Plan) -> dict[str, Any]:
    return to_json(plan)


def plan_from_dict(data: dict[str, Any]) -> Plan:
    return from_json(Plan, data)


def _upgrade_v1(plan: dict[str, Any]) -> dict[str, Any]:
    """v1 -> v2: overrides.subs became overrides.tracks with profile flags.

    v1 plans carry no profile; Plan.profile stays "" and the caller picks one.
    """
    plan = dict(plan)
    overrides = dict(plan.get("overrides") or {})
    subs = overrides.pop("subs", None) or {}
    overrides["tracks"] = {
        key: {
            "exclude": ov.get("exclude"),
            "language": ov.get("language"),
            "flags": {k: ov[k] for k in _V1_SUB_FLAGS if ov.get(k) is not None},
        }
        for key, ov in subs.items()
    }
    plan["overrides"] = overrides
    return plan


def dump_plans(plans: list[Plan], path: Path) -> None:
    doc = {"version": FORMAT_VERSION, "plans": [plan_to_dict(p) for p in plans]}
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")


def load_plans(path: Path) -> list[Plan]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    version = doc.get("version")
    if version not in (1, FORMAT_VERSION):
        raise PlanFormatError(f"{path.name}: plan format version {version!r}, expected {FORMAT_VERSION}")
    try:
        plans = doc["plans"] if version == FORMAT_VERSION else [_upgrade_v1(p) for p in doc["plans"]]
        return [plan_from_dict(p) for p in plans]
    except (AttributeError, KeyError, TypeError, ValueError) as e:
        raise PlanFormatError(f"{path.name}: {e}") from e
