"""Shareable preset libraries; application settings and local identities are excluded."""

import json
import re
from typing import Any

from videoforge.server.configuration import read_libraries
from videoforge.server.routes.presets import KINDS

FORMAT = "videoforge.presets"
VERSION = 1
MAX_BYTES = 20 * 1024 * 1024
KEY = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")


def read_preset_pack(doc: Any, *, keep_keys: bool = False) -> dict[str, Any]:
    """Validate a pack and return it normalized.

    An entry may carry a `key`, its stable identity ("remux-1080p"): a plugin's pack (manifest `presets`)
    needs one on every entry, so an update finds the preset it shipped before whatever it is named now.
    Keys are dropped unless `keep_keys`, as a user's own import makes plain presets.
    """
    if not isinstance(doc, dict) or doc.get("format") != FORMAT:
        raise ValueError("Choose a VideoForge preset pack (.json)")
    if type(doc.get("version")) is not int or doc["version"] != VERSION:
        raise ValueError(f"Unsupported preset pack version; this app supports version {VERSION}")
    if set(doc) != {"format", "version", "presets"}:
        raise ValueError("Preset packs contain only format, version, and presets")
    json.dumps(doc, allow_nan=False)
    libraries = doc["presets"]
    pack_keys: dict[str, list[str | None]] = {}
    if not isinstance(libraries, dict) or set(libraries) != set(KINDS):
        raise ValueError("Expected template, video, encoder, and audio preset libraries")
    validated = {}
    for kind, entries in libraries.items():
        if not isinstance(entries, list) or len(entries) > 5000:
            raise ValueError(f"{kind}: expected up to 5000 presets")
        validated[kind], pack_keys[kind] = [], []
        for i, entry in enumerate(entries):
            grouped = kind in ("encoder", "audio")
            keys = {"label", "group", "data"} if grouped else {"name", "data"}
            if not isinstance(entry, dict) or set(entry) - {"key"} != keys:
                raise ValueError(f"{kind}: unexpected preset fields")
            key = entry.get("key")
            if key is not None and (not isinstance(key, str) or not KEY.fullmatch(key) or key in pack_keys[kind]):
                raise ValueError(f"{kind}: a preset key is unique, lowercase letters, digits, . _ -, up to 64")
            pack_keys[kind].append(key)
            entry = {k: v for k, v in entry.items() if k != "key"}
            validated[kind].append({**entry, "name": str(i)} if grouped else entry)
    if not any(validated.values()):
        raise ValueError("Choose at least one preset to share")
    normalized = read_libraries(validated, allow_duplicates=True)
    for kind in ("encoder", "audio"):
        normalized[kind] = [{key: entry[key] for key in ("label", "group", "data")} for entry in normalized[kind]]
    if keep_keys:
        for kind, entries in normalized.items():
            for entry, key in zip(entries, pack_keys[kind], strict=True):
                if key is not None:
                    entry["key"] = key
    return {"format": FORMAT, "version": VERSION, "presets": normalized}
