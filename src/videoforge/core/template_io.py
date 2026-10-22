"""Portable template bundles. Reading a bundle only validates data; it never runs scripts."""

from __future__ import annotations

import dataclasses
from enum import Enum
from functools import cache
import math
import types
from typing import Any, Union, get_args, get_origin, get_type_hints

from videoforge.core.models import Layout
from videoforge.core.plan_io import from_json, to_json
from videoforge.core.template import Template

FORMAT = "videoforge.templates"
VERSION = 1
MAX_TEMPLATES = 500
MAX_BYTES = 5 * 1024 * 1024
MAX_NAME = 80


@cache
def _hints(cls: type) -> dict[str, Any]:
    return get_type_hints(cls)


def check_settings(tp: Any, value: Any, path: str) -> None:
    """Check imported JSON before the forgiving persistence decoder fills in defaults.

    Unknown fields are rejected so sharing with an older app cannot silently lose settings.
    Keep Layout's wire representation and the existing dataclass upgrade hooks.
    """
    origin, args = get_origin(tp), get_args(tp)
    if origin in (Union, types.UnionType):
        if value is None and type(None) in args:
            return
        (inner,) = [a for a in args if a is not type(None)]
        return check_settings(inner, value, path)
    if tp is Layout or (isinstance(tp, type) and issubclass(tp, Enum)):
        if not isinstance(value, str):
            raise ValueError(f"{path}: expected text")
        from_json(tp, value)
    elif dataclasses.is_dataclass(tp):
        if not isinstance(value, dict):
            raise ValueError(f"{path}: expected an object")
        if upgrade := getattr(tp, "upgrade_json", None):
            value = upgrade(value)
        hints = _hints(tp)
        for key, item in value.items():
            if key not in hints:
                raise ValueError(f"{path}.{key}: unknown setting; check the VideoForge version")
            check_settings(hints[key], item, f"{path}.{key}")
    elif origin in (list, tuple, frozenset):
        if not isinstance(value, list):
            raise ValueError(f"{path}: expected a list")
        for i, item in enumerate(value):
            check_settings(args[0], item, f"{path}[{i + 1}]")
    elif origin is dict:
        if not isinstance(value, dict):
            raise ValueError(f"{path}: expected an object")
        for key, item in value.items():
            check_settings(args[0], key, path)
            check_settings(args[1], item, f"{path}.{key}")
    elif tp is float:
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(f"{path}: expected a finite number")
    elif tp in (str, int, bool) and type(value) is not tp:
        raise ValueError(f"{path}: expected {tp.__name__}")


def read_bundle(doc: Any) -> dict[str, Any]:
    """Validate the entire file and return normalized settings, without changing storage."""
    if not isinstance(doc, dict) or doc.get("format") != FORMAT:
        raise ValueError("Choose a VideoForge template export (.json)")
    if type(doc.get("version")) is not int or doc["version"] != VERSION:
        raise ValueError(f"Unsupported template format version; this app supports version {VERSION}")
    if set(doc) - {"format", "version", "templates"}:
        raise ValueError("Unknown template file fields; check the VideoForge version")
    entries = doc.get("templates")
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_TEMPLATES:
        raise ValueError(f"A template file must contain 1 to {MAX_TEMPLATES} templates")
    out = []
    for i, entry in enumerate(entries, 1):
        if not isinstance(entry, dict) or set(entry) != {"name", "data"}:
            raise ValueError(f"Template {i}: expected name and data")
        name = entry["name"]
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= MAX_NAME:
            raise ValueError(f"Template {i}: a name needs 1 to {MAX_NAME} characters")
        try:
            check_settings(Template, entry["data"], f"Template {i}")
            data = to_json(from_json(Template, entry["data"]))
        except (TypeError, ValueError, KeyError, AttributeError, OverflowError) as ex:
            raise ValueError(f"Invalid template {name!r}: {ex}") from None
        out.append({"name": name.strip(), "data": data})
    return {"format": FORMAT, "version": VERSION, "templates": out}
