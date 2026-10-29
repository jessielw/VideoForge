"""Versioned configuration backups. Validation never changes storage or runs included code."""

from dataclasses import fields
import json
from typing import Any

from videoforge.core.actions import Action
from videoforge.core.config import AppConfig
from videoforge.core.models import TemplateSubs
from videoforge.core.notify import Destination
from videoforge.core.plan_io import from_json, to_json
from videoforge.core.template_io import MAX_NAME, check_settings
from videoforge.core.tools import TOOL_NAMES
from videoforge.server.routes.presets import KINDS
from videoforge.server.settings import MAX_PARALLEL_AUDIO, SavedSettings

FORMAT = "videoforge.configuration"
VERSION = 3  # 3: subs_default
MAX_BYTES = 20 * 1024 * 1024
BASE_KEY = "configuration_base"
SETTING_KEYS = tuple(f.name for f in fields(SavedSettings))
FOLDER_KEYS = ("output_dir", "last_dir")


def _object(value: Any, keys: set[str], path: str) -> None:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{path}: missing or unknown fields; check the VideoForge version")


def _name(value: Any, path: str, *, limit: int = MAX_NAME) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{path}: expected 1 to {limit} characters")
    return value


def read_configuration(doc: Any) -> dict[str, Any]:
    if not isinstance(doc, dict) or doc.get("format") != FORMAT:
        raise ValueError("Choose a VideoForge configuration export (.json)")
    if type(doc.get("version")) is not int or doc["version"] not in (1, 2, VERSION):
        raise ValueError(f"Unsupported configuration version; this app supports version {VERSION}")
    keys = {"format", "version", "application", "settings", "folders", "presets", "template_defaults"}
    _object(doc, keys | {"subs_default"} if doc["version"] >= 3 else keys, "Configuration")
    # JSON-native values only, including plugin-owned settings; reject NaN/Infinity anywhere.
    json.dumps(doc, allow_nan=False)
    _object(doc["application"], {f.name for f in fields(AppConfig)}, "Application settings")
    check_settings(AppConfig, doc["application"], "Application settings")
    application = from_json(AppConfig, doc["application"])
    if not 0 <= application.parallel_audio <= MAX_PARALLEL_AUDIO:
        raise ValueError(f"parallel_audio: a whole number from 0 to {MAX_PARALLEL_AUDIO}")
    if not isinstance(application.plugins, dict) or any(not isinstance(v, dict) for v in application.plugins.values()):
        raise ValueError("Plugin settings must be objects")
    saved_values = doc["settings"]
    if doc["version"] == 1:
        _object(saved_values, set(SETTING_KEYS) - {"plugin_settings"}, "Saved settings")
        saved_values = saved_values | {"plugin_settings": {}}
    _object(saved_values, set(SETTING_KEYS), "Saved settings")
    check_settings(SavedSettings, saved_values, "Saved settings")
    settings = from_json(SavedSettings, saved_values)
    if any(not isinstance(value, dict) for value in settings.plugin_settings.values()):
        raise ValueError("Plugin settings must be objects")
    if settings.tools.keys() - TOOL_NAMES:
        raise ValueError("Unknown tool paths; check the VideoForge version")
    if settings.parallel_audio is not None and not 0 <= settings.parallel_audio <= MAX_PARALLEL_AUDIO:
        raise ValueError(f"parallel_audio: a whole number from 0 to {MAX_PARALLEL_AUDIO}")
    settings.notifications = [Destination.from_json(d) for d in doc["settings"]["notifications"]]
    settings.actions = [Action.from_json(a) for a in doc["settings"]["actions"]]
    _object(doc["folders"], set(FOLDER_KEYS), "Folder choices")
    if any(not isinstance(value, str) for value in doc["folders"].values()):
        raise ValueError("Folder choices must be text")
    libraries = read_libraries(doc["presets"])
    defaults = doc["template_defaults"]
    if not isinstance(defaults, dict) or any(
        not isinstance(pid, str) or name not in {e["name"] for e in libraries["template"]}
        for pid, name in defaults.items()
    ):
        raise ValueError("Default template selections must refer to templates included in this backup")
    subs = doc.get("subs_default")  # version 3: Settings' default subtitle rules
    if subs is not None:
        if not isinstance(subs, dict):
            raise ValueError("Default subtitle rules must be an object or null")
        check_settings(TemplateSubs, subs, "Default subtitle rules")
        subs = to_json(from_json(TemplateSubs, subs))
    return {
        "format": FORMAT,
        "version": VERSION,
        "application": to_json(application),
        "settings": to_json(settings),
        "folders": doc["folders"],
        "presets": libraries,
        "template_defaults": defaults,
        "subs_default": subs,
    }


def read_libraries(value: Any, *, allow_duplicates: bool = False) -> dict[str, list[dict[str, Any]]]:
    """Validate settings and metadata independently of private application configuration."""
    _object(value, set(KINDS), "Preset libraries")
    libraries = {}
    for kind, cls in KINDS.items():
        entries = value[kind]
        if not isinstance(entries, list) or len(entries) > 5000:
            raise ValueError(f"{kind}: expected up to 5000 presets")
        seen, destinations, library = set(), set(), []
        for entry in entries:
            grouped = kind in ("encoder", "audio")
            _object(entry, {"name", "label", "group", "data"} if grouped else {"name", "data"}, f"{kind} preset")
            name = _name(entry["name"], f"{kind} preset identity")
            if name in seen and not allow_duplicates:
                raise ValueError(f"Duplicate {kind} preset identity {name!r}")
            seen.add(name)
            check_settings(cls, entry["data"], f"{kind} preset {name!r}")
            data = to_json(from_json(cls, entry["data"]))
            if kind == "video":
                data.pop("crop", None)
            record = {"name": name, "data": data}
            if grouped:
                label, group = _name(entry["label"], "Preset name"), entry["group"]
                if not isinstance(group, list) or len(group) > 8:
                    raise ValueError("A preset can have up to 8 nested folders")
                for part in group:
                    if "/" in _name(part, "Preset folder"):
                        raise ValueError("A preset folder name cannot contain /")
                parent = data["encoder" if kind == "encoder" else "action"]
                destination = (parent, tuple(group), label)
                if destination in destinations and not allow_duplicates:
                    raise ValueError(f"Duplicate {kind} preset name in the same folder: {label!r}")
                destinations.add(destination)
                record.update(label=label, group=group)
            library.append(record)
        libraries[kind] = library
    return libraries


def storage_presets(bundle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        kind: {
            entry["name"]: (
                {"label": entry["label"], "group": entry["group"], "settings": entry["data"]}
                if kind in ("encoder", "audio")
                else entry["data"]
            )
            for entry in entries
        }
        for kind, entries in bundle["presets"].items()
    }
