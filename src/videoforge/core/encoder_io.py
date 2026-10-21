"""Portable encoder presets, independent of jobs, templates, and local storage IDs."""

from typing import Any

from videoforge.core.plan_io import from_json, to_json
from videoforge.core.template_io import MAX_NAME, check_settings
from videoforge.core.video.settings import EncoderSettings

FORMAT = "videoforge.encoders"
VERSION = 1
MAX_PRESETS = 500


def read_encoder_bundle(doc: Any) -> dict[str, Any]:
    if not isinstance(doc, dict) or doc.get("format") != FORMAT:
        raise ValueError("Choose a VideoForge encoder preset export (.json)")
    if type(doc.get("version")) is not int or doc["version"] != VERSION:
        raise ValueError(f"Unsupported encoder format version; this app supports version {VERSION}")
    if set(doc) != {"format", "version", "encoders"}:
        raise ValueError("Unknown or missing encoder file fields; check the VideoForge version")
    entries = doc["encoders"]
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_PRESETS:
        raise ValueError(f"An encoder file must contain 1 to {MAX_PRESETS} presets")
    out = []
    for i, entry in enumerate(entries, 1):
        if not isinstance(entry, dict) or set(entry) != {"label", "group", "data"}:
            raise ValueError(f"Encoder preset {i}: expected label, group, and data")
        label, group = entry["label"], entry["group"]
        if not isinstance(label, str) or not 1 <= len(label.strip()) <= MAX_NAME:
            raise ValueError(f"Encoder preset {i}: a name needs 1 to {MAX_NAME} characters")
        if (
            not isinstance(group, list)
            or len(group) > 8
            or any(not isinstance(part, str) or not 1 <= len(part.strip()) <= MAX_NAME or "/" in part for part in group)
        ):
            raise ValueError(f"Encoder preset {i}: use up to 8 folders of 1 to {MAX_NAME} characters without /")
        try:
            check_settings(EncoderSettings, entry["data"], f"Encoder preset {i}")
            data = to_json(from_json(EncoderSettings, entry["data"]))
        except (TypeError, ValueError, KeyError, AttributeError, OverflowError) as ex:
            raise ValueError(f"Invalid encoder preset {label!r}: {ex}") from None
        out.append({"label": label.strip(), "group": [part.strip() for part in group], "data": data})
    return {"format": FORMAT, "version": VERSION, "encoders": out}
