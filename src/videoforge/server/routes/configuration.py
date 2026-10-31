"""Full configuration backup and restore from Settings, with a read-only preview, and a reset to defaults."""

from datetime import datetime
import json
import os
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request

from videoforge.core.config import AppConfig
from videoforge.core.plan_io import from_json, to_json
from videoforge.rule_sets import default_rule_set_id
from videoforge.server.configuration import (
    BASE_KEY,
    FOLDER_KEYS,
    FORMAT,
    MAX_BYTES,
    SETTING_KEYS,
    VERSION,
    read_configuration,
    storage_presets,
)
from videoforge.server.routes import config, presets, profiles
from videoforge.server.settings import SavedSettings

router = APIRouter(prefix="/api/configuration")


@router.get("/export")
def export_configuration(request: Request) -> dict[str, Any]:
    state = request.app.state
    snapshot = state.store.configuration_snapshot(
        SETTING_KEYS + FOLDER_KEYS + (BASE_KEY, "template_defaults", presets.SUBS_DEFAULT), tuple(presets.KINDS)
    )
    saved = snapshot["settings"]
    libraries = {}
    for kind, records in snapshot["presets"].items():
        libraries[kind] = []
        for name, data in records.items():
            entry = presets._entry(kind, name, data)
            if kind in ("encoder", "audio"):
                entry = {**entry, "label": entry.get("label", name), "group": entry.get("group", [])}
            libraries[kind].append(entry)
    profile = next(p["name"] for p in state.store.profiles() if p["id"] == state.store.profile)
    bundle = {
        "format": FORMAT,
        "version": VERSION,
        "profile": profile,
        "application": saved.get(BASE_KEY, to_json(state.base_config)),
        "settings": to_json(SavedSettings()) | {key: saved[key] for key in SETTING_KEYS if key in saved},
        "folders": {key: saved.get(key, "") for key in FOLDER_KEYS},
        "presets": libraries,
        "template_defaults": {
            pid: name
            for pid, name in saved.get("template_defaults", {}).items()
            if name in snapshot["presets"]["template"]
        },
        "subs_default": saved.get(presets.SUBS_DEFAULT) or None,
    }
    try:
        return read_configuration(bundle)
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as ex:
        raise HTTPException(422, f"Cannot export configuration: {ex}") from None


async def _read(request: Request) -> dict[str, Any]:
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > MAX_BYTES:
            raise HTTPException(413, "Configuration files must be 20 MiB or smaller")
    try:
        return read_configuration(json.loads(raw))
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError) as ex:
        raise HTTPException(422, f"Invalid configuration file: {ex}") from None


def _preview(request: Request, bundle: dict[str, Any]) -> dict[str, Any]:
    state = request.app.state
    warnings = []
    rule_sets = {bundle["application"]["rule_set"], bundle["settings"]["rule_set"], *bundle["template_defaults"]} - {
        None
    }
    for rule_set in sorted(rule_sets - set(state.rule_set_ids)):
        warnings.append(
            f"Rule set {rule_set!r} is not installed. Install it to use its defaults; new jobs use an available rule set."
        )
    for root in bundle["settings"]["roots"] or []:
        if not os.path.isdir(root):
            warnings.append(f"Folder browser path is unavailable on this computer: {root}")
    warnings.append("Check tool paths and output folders when moving this backup to another computer.")
    counts = state.store.preset_counts()
    return {
        "bundle": bundle,
        "counts": {kind: len(entries) for kind, entries in bundle["presets"].items()},
        # every profile's library sizes: what an import into it replaces (a new profile's are all 0)
        "profile_counts": {
            p["id"]: {kind: counts.get(p["id"], {}).get(kind, 0) for kind in presets.KINDS}
            for p in state.store.profiles()
        },
        "warnings": warnings,
    }


@router.post("/preview")
async def preview_configuration(request: Request) -> dict[str, Any]:
    return _preview(request, await _read(request))


@router.post("/import")
async def import_configuration(
    request: Request, profile: str | None = None, new: str | None = None, switch: bool = False
) -> dict[str, Any]:
    """Into the active profile, another one (`profile`: its id) or a new one (`new`: its name); `switch`
    makes it the active profile as well. Only the active profile's settings are applied."""
    if profile is not None and new is not None:
        raise HTTPException(422, "Choose a profile or a new profile's name, not both")
    bundle = await _read(request)
    state = request.app.state
    store = state.store
    target = store.profile if profile is None else profile
    if new is None and target not in {p["id"] for p in store.profiles()}:
        raise HTTPException(404, "No such profile")
    if switch and (new is not None or target != store.profile):
        profiles.idle(request)
    base = from_json(AppConfig, bundle["application"])
    saved = from_json(SavedSettings, bundle["settings"])
    saved.app_config(base, default_rule_set_id(saved.rule_set or base.rule_set, state.rule_set_ids))
    settings = (
        bundle["settings"]
        | bundle["folders"]
        | {
            BASE_KEY: bundle["application"],
            "template_defaults": bundle["template_defaults"],
            presets.SUBS_DEFAULT: bundle["subs_default"],
        }
    )
    if new is not None:
        try:
            target = store.create_profile(new)
        except ValueError as ex:
            raise HTTPException(422, str(ex)) from None
    # One transaction for every library, default reference, and setting.
    try:
        store.restore_configuration(settings, storage_presets(bundle), target)
    except Exception:
        if new is not None:
            store.delete_profile(target)
        raise
    if switch and target != store.profile:
        store.switch_profile(target)
    if target == store.profile:
        if base.plugins != state.base_config.plugins:
            state.restart_for.add("configuration")
        state.base_config = base
        config.apply_settings(request, saved)
    return {
        "config": config._state(request),
        "presets": presets._all(request),
        "warnings": _preview(request, bundle)["warnings"],
        "profiles": store.profiles(),
        "active": store.profile,
        "profile": target,
    }


RESET_SCOPES = ("settings", "presets", "jobs")


@router.post("/reset")
def reset_configuration(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    """{settings, presets, jobs}: go back to videoforge.toml's settings (tool paths, folders, notifications,
    actions, plugin settings), empty the preset libraries (with default templates), and/or remove every job.
    A backup of the configuration is written to the data folder first. Installed plugins, their files,
    work folders and kept job records stay. Refused (409) while anything runs."""
    if any(not isinstance(body.get(scope, False), bool) for scope in RESET_SCOPES):
        raise HTTPException(422, "settings, presets and jobs: true or false")
    scopes = {scope for scope in RESET_SCOPES if body.get(scope)}
    if not scopes:
        raise HTTPException(422, "Choose what to reset")
    state = request.app.state
    q = state.queue
    profiles.idle(request)
    backup = state.settings.data_dir / "backups" / f"reset-{datetime.now():%Y%m%d-%H%M%S}.json"
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_text(json.dumps(export_configuration(request), indent=2) + "\n", encoding="utf-8")
    keys = SETTING_KEYS + FOLDER_KEYS + (BASE_KEY, presets.SUBS_DEFAULT) if "settings" in scopes else ()
    kinds = tuple(presets.KINDS) if "presets" in scopes else ()
    state.store.reset_configuration(keys + ((presets.DEFAULTS,) if kinds else ()), kinds)
    if "settings" in scopes:
        base = state.file_config
        if base.plugins != state.base_config.plugins:
            state.restart_for.add("configuration")
        state.base_config = base
        config.apply_settings(request, SavedSettings.load(state.store))
    removed = q.remove([e.id for e in q.entries()]) if "jobs" in scopes else []
    return {
        "config": config._state(request),
        "presets": presets._all(request),
        "backup": str(backup),
        "removed": removed,
    }
