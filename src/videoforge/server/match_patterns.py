"""Name patterns the user taught by matching a set of files by hand (pairing.learn_patterns), kept per profile in the
settings store so later batches match files of that shape the same way. Newest first, at most LIMIT."""

from __future__ import annotations

from typing import Any

from videoforge.core.match_names import NamePattern

KEY = "match_patterns"
LIMIT = 200


def load(store: Any) -> list[NamePattern]:
    out = []
    for item in store.get_setting(KEY, []) or []:
        try:
            out.append(NamePattern(str(item["shape"]), int(item["position"]), str(item.get("example", ""))))
        except (KeyError, TypeError, ValueError):
            continue  # a damaged entry is dropped, not fatal
    return out


def _save(store: Any, patterns: list[NamePattern]) -> None:
    store.set_setting(KEY, [{"shape": p.shape, "position": p.position, "example": p.example} for p in patterns[:LIMIT]])


def remember(store: Any, new: list[NamePattern]) -> None:
    """Put new patterns first; one per shape, the newest winning."""
    if not new:
        return
    shapes = {p.shape for p in new}
    _save(store, new + [p for p in load(store) if p.shape not in shapes])


def forget(store: Any, shape: str | None) -> int:
    """Forget one shape's pattern, or all of them (shape None). Returns how many were forgotten."""
    patterns = load(store)
    kept = [p for p in patterns if shape is not None and p.shape != shape]
    _save(store, kept)
    return len(patterns) - len(kept)
