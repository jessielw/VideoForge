"""Shareable preset libraries; application settings and local identities are excluded."""

import json
from typing import Any

from videoforge.server.configuration import read_libraries
from videoforge.server.routes.presets import KINDS

FORMAT = "videoforge.presets"
VERSION = 1
MAX_BYTES = 20 * 1024 * 1024


def read_preset_pack(doc: Any) -> dict[str, Any]:
    if not isinstance(doc, dict) or doc.get("format") != FORMAT:
        raise ValueError("Choose a VideoForge preset pack (.json)")
    if type(doc.get("version")) is not int or doc["version"] != VERSION:
        raise ValueError(f"Unsupported preset pack version; this app supports version {VERSION}")
    if set(doc) != {"format", "version", "presets"}:
        raise ValueError("Preset packs contain only format, version, and presets")
    json.dumps(doc, allow_nan=False)
    libraries = doc["presets"]
    if not isinstance(libraries, dict) or set(libraries) != set(KINDS):
        raise ValueError("Expected template, video, encoder, and audio preset libraries")
    validated = {}
    for kind, entries in libraries.items():
        if not isinstance(entries, list) or len(entries) > 5000:
            raise ValueError(f"{kind}: expected up to 5000 presets")
        validated[kind] = []
        for i, entry in enumerate(entries):
            grouped = kind in ("encoder", "audio")
            keys = {"label", "group", "data"} if grouped else {"name", "data"}
            if not isinstance(entry, dict) or set(entry) != keys:
                raise ValueError(f"{kind}: unexpected preset fields")
            validated[kind].append({**entry, "name": str(i)} if grouped else entry)
    if not any(validated.values()):
        raise ValueError("Choose at least one preset to share")
    normalized = read_libraries(validated, allow_duplicates=True)
    for kind in ("encoder", "audio"):
        normalized[kind] = [{key: entry[key] for key in ("label", "group", "data")} for entry in normalized[kind]]
    return {"format": FORMAT, "version": VERSION, "presets": normalized}
