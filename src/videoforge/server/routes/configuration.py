"""Full configuration backup and restore from Settings, with a read-only preview."""

import json
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from videoforge.core.config import AppConfig
from videoforge.core.plan_io import from_json, to_json
from videoforge.profiles import default_profile_id
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
from videoforge.server.routes import config, presets
from videoforge.server.settings import SavedSettings

router = APIRouter(prefix="/api/configuration")


@router.get("/export")
def export_configuration(request: Request) -> dict[str, Any]:
    state = request.app.state
    snapshot = state.store.configuration_snapshot(
        SETTING_KEYS + FOLDER_KEYS + (BASE_KEY, "template_defaults"), tuple(presets.KINDS)
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
    bundle = {
        "format": FORMAT,
        "version": VERSION,
        "application": saved.get(BASE_KEY, to_json(state.base_config)),
        "settings": to_json(SavedSettings()) | {key: saved[key] for key in SETTING_KEYS if key in saved},
        "folders": {key: saved.get(key, "") for key in FOLDER_KEYS},
        "presets": libraries,
        "template_defaults": {
            pid: name
            for pid, name in saved.get("template_defaults", {}).items()
            if name in snapshot["presets"]["template"]
        },
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
    profiles = {bundle["application"]["profile"], bundle["settings"]["profile"], *bundle["template_defaults"]} - {None}
    for profile in sorted(profiles - set(state.profile_ids)):
        warnings.append(
            f"Profile {profile!r} is not installed. Install it to use its defaults; new jobs use an available profile."
        )
    for root in bundle["settings"]["roots"] or []:
        if not os.path.isdir(root):
            warnings.append(f"Folder browser path is unavailable on this computer: {root}")
    warnings.append("Check tool paths and output folders when moving this backup to another computer.")
    return {
        "bundle": bundle,
        "counts": {kind: len(entries) for kind, entries in bundle["presets"].items()},
        "current_counts": {kind: len(state.store.presets(kind)) for kind in presets.KINDS},
        "warnings": warnings,
    }


@router.post("/preview")
async def preview_configuration(request: Request) -> dict[str, Any]:
    return _preview(request, await _read(request))


@router.post("/import")
async def import_configuration(request: Request) -> dict[str, Any]:
    bundle = await _read(request)
    state = request.app.state
    base = from_json(AppConfig, bundle["application"])
    saved = from_json(SavedSettings, bundle["settings"])
    saved.app_config(base, default_profile_id(saved.profile or base.profile, state.profile_ids))
    settings = (
        bundle["settings"]
        | bundle["folders"]
        | {BASE_KEY: bundle["application"], "template_defaults": bundle["template_defaults"]}
    )
    # One transaction for every library, default reference, and setting.
    state.store.restore_configuration(settings, storage_presets(bundle))
    if base.plugins != state.base_config.plugins:
        state.restart_for.add("configuration")
    state.base_config = base
    config.apply_settings(request, saved)
    return {
        "config": config._state(request),
        "presets": presets._all(request),
        "warnings": _preview(request, bundle)["warnings"],
    }
