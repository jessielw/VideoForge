"""The output folders a user picks from on New jobs: every folder used before (newest first, the unpinned capped),
plus the pinned ones, one of which can be the default that pre-fills the field. Machine-local: not in configuration exports."""

from typing import Any

KEY = "output_folders"
DEFAULT_KEY = "output_default"
MAX_RECENT = 10
MAX_PINNED = 50


def clean(value: Any) -> list[dict[str, Any]]:
    """A list of {path, pinned} from a request or storage; anything else in it is dropped, duplicates (by case) collapse."""
    if not isinstance(value, list):
        raise ValueError("output_folders: expected a list")
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in value:
        path = item.get("path") if isinstance(item, dict) else None
        if not isinstance(path, str) or not path.strip() or path.lower() in seen:
            continue
        seen.add(path.lower())
        out.append({"path": path, "pinned": item.get("pinned") is True})
    pinned = [f for f in out if f["pinned"]][:MAX_PINNED]
    recent = [f for f in out if not f["pinned"]][:MAX_RECENT]
    return [f for f in out if f in pinned or f in recent]


def remember(folders: list[dict[str, Any]], path: str) -> list[dict[str, Any]]:
    """The list with `path` used now: a new or unpinned folder moves to the front of the recent ones."""
    existing = next((f for f in folders if f["path"].lower() == path.lower()), None)
    if existing and existing["pinned"]:
        return folders
    rest = [f for f in folders if f is not existing]
    return clean(
        [*[f for f in rest if f["pinned"]], {"path": path, "pinned": False}, *[f for f in rest if not f["pinned"]]]
    )
