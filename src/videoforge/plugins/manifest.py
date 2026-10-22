"""Declarative plugin metadata and settings. Reading a manifest never imports Python."""

from dataclasses import asdict, dataclass, field
from pathlib import Path
import re
import tomllib
from typing import Any

from videoforge.plugins import API_VERSION

MANIFEST = "videoforge-plugin.toml"
RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(10)), *(f"lpt{i}" for i in range(10))}


class PluginError(ValueError):
    pass


def safe_id(value: str) -> str:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", value) or value.casefold() in RESERVED:
        raise PluginError("Plugin id must be 1–64 letters, digits, underscores or hyphens, and a valid folder name")
    return value


@dataclass(frozen=True, slots=True)
class Setting:
    key: str
    label: str
    type: str = "text"
    help: str = ""
    required: bool = False
    default: Any = None
    choices: tuple[str, ...] = ()

    def validate(self, value: Any) -> None:
        valid = {
            "text": isinstance(value, str),
            "password": isinstance(value, str),
            "checkbox": type(value) is bool,
            "integer": type(value) is int,
            "choice": isinstance(value, str) and value in self.choices,
        }[self.type]
        if not valid or (self.required and isinstance(value, str) and not value.strip()):
            raise PluginError(f"{self.label}: expected {'a non-empty ' if self.required else ''}{self.type} value")


@dataclass(frozen=True, slots=True)
class Manifest:
    id: str
    module: str
    object: str = "plugin"
    name: str = ""
    version: str = ""
    description: str = ""
    api_version: int = 1
    settings: tuple[Setting, ...] = field(default_factory=tuple)

    def metadata(self) -> dict[str, Any]:
        return asdict(self)

    def effective(self, base: dict, overrides: dict) -> dict:
        return {s.key: s.default for s in self.settings if s.default is not None} | base | overrides

    def validate_settings(self, values: dict, *, required: bool = True) -> None:
        for setting in self.settings:
            if setting.key in values:
                setting.validate(values[setting.key])
            elif setting.required and required:
                raise PluginError(f"{setting.label}: a value is required")


def parse_manifest(text: str, *, package: bool = False) -> Manifest:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as ex:
        raise PluginError(f"Can't read {MANIFEST}: {ex}") from None
    values = {}
    for key, default in (("id", None), ("module", None), ("object", "plugin")):
        value = data.get(key, default)
        if not isinstance(value, str) or not value.strip():
            raise PluginError(f"{MANIFEST} needs `{key}`, a non-empty string")
        values[key] = value.strip()
    if not values["module"].isidentifier():
        raise PluginError(f"{MANIFEST}: `module` must be a top-level module or package name (no dots)")
    if not values["object"].isidentifier():
        raise PluginError(f"{MANIFEST}: `object` must be a Python name")
    for key in ("name", "version", "description"):
        value = data.get(key, "")
        if not isinstance(value, str) or (package and key != "description" and not value.strip()):
            raise PluginError(f"{MANIFEST} needs `{key}` as text")
        values[key] = value
    api = data.get("api_version", None if package else 1)
    if type(api) is not int or not 1 <= api <= API_VERSION:
        raise PluginError(f"Plugin needs a supported api_version (1–{API_VERSION}); update VideoForge if necessary")
    definitions = data.get("settings", [])
    if not isinstance(definitions, list) or len(definitions) > 100:
        raise PluginError("settings must be an array of up to 100 field declarations")
    settings, seen = [], set()
    for definition in definitions:
        if not isinstance(definition, dict) or set(definition) - {
            "key",
            "label",
            "type",
            "help",
            "required",
            "default",
            "choices",
        }:
            raise PluginError("Invalid settings declaration")
        key = definition.get("key")
        if not isinstance(key, str) or not key.isidentifier() or key in seen:
            raise PluginError("Each setting needs a unique Python identifier as its key")
        seen.add(key)
        label, help_text = definition.get("label", key), definition.get("help", "")
        kind, required = definition.get("type", "text"), definition.get("required", False)
        if not isinstance(label, str) or not isinstance(help_text, str) or type(required) is not bool:
            raise PluginError(f"Invalid label, help or required flag for {key}")
        if not isinstance(kind, str) or kind not in {"text", "password", "checkbox", "integer", "choice"}:
            raise PluginError(f"Unknown setting type for {key}")
        choices = definition.get("choices", [])
        if not isinstance(choices, list) or any(not isinstance(c, str) for c in choices):
            raise PluginError(f"{key}: choices must be strings")
        if kind == "choice" and (not choices or len(set(choices)) != len(choices)):
            raise PluginError(f"{key}: choices must be non-empty and unique")
        setting = Setting(key, label, kind, help_text, required, definition.get("default"), tuple(choices))
        if "default" in definition:
            setting.validate(setting.default)
        settings.append(setting)
    if package:
        safe_id(values["id"])
    return Manifest(**values, api_version=api, settings=tuple(settings))


def read_manifest(path: Path) -> Manifest:
    try:
        return parse_manifest(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as ex:
        raise PluginError(f"Can't read {MANIFEST}: {ex}") from None
