"""Plugin management endpoints. ZIP validation and inventory never import plugin code."""

from dataclasses import replace as replace_settings
import json

from fastapi import APIRouter, Body, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from videoforge.plugins.manager import MAX_ZIP_BYTES, PluginConflict, read_package
from videoforge.plugins.manifest import PluginError
from videoforge.server.routes.config import _state, apply_settings

router = APIRouter(prefix="/api/plugins")


def _allowed(request: Request) -> None:
    if not request.app.state.settings.can_manage_plugins:
        raise HTTPException(
            403, "Plugin management is disabled. Start VideoForge with --plugin-management to enable it."
        )


def _inventory(request: Request) -> dict:
    s = request.app.state
    try:
        result = s.plugin_manager.inventory(
            s.plugins, s.saved.disabled_plugins, s.base_config.plugins, s.saved.plugin_settings
        )
    except (PluginError, OSError) as ex:
        result = {"folder": str(s.settings.plugins_dir), "items": [], "failures": [str(ex)]}
    return result | {"management_enabled": s.settings.can_manage_plugins, "restart": _state(request)["restart"]}


def _error(ex: Exception) -> HTTPException:
    return HTTPException(409 if isinstance(ex, PluginConflict) else 422, str(ex))


async def _zip(request: Request) -> bytes:
    _allowed(request)
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > MAX_ZIP_BYTES:
            raise HTTPException(413, "Plugin ZIP files must be 50 MiB or smaller")
    return bytes(raw)


@router.get("")
def inventory(request: Request) -> dict:
    return _inventory(request)


@router.post("/preview")
async def preview(request: Request) -> dict:
    raw = await _zip(request)

    def inspect() -> dict:
        try:
            result = request.app.state.plugin_manager.preview(read_package(raw))
            # Password defaults should not be displayed in the browser.
            for setting in result["plugin"]["settings"]:
                if setting["type"] == "password":
                    setting["default"] = None
            if result["current"]:
                for setting in result["current"]["settings"]:
                    if setting["type"] == "password":
                        setting["default"] = None
            return result
        except (PluginError, OSError) as ex:
            raise _error(ex) from None

    return await run_in_threadpool(inspect)


@router.post("/import")
async def install(request: Request, revision: str, replace: bool = False) -> dict:
    raw = await _zip(request)

    def stage() -> dict:
        s = request.app.state
        try:
            package = read_package(raw)
            s.plugin_manager.stage_install(package, revision, replace=replace)
            if not replace and package.manifest.id in s.saved.disabled_plugins:
                new = replace_settings(
                    s.saved, disabled_plugins=[p for p in s.saved.disabled_plugins if p != package.manifest.id]
                )
                new.save(s.store)
                apply_settings(request, new)
            s.restart_for.add("plugin_files")
            return _inventory(request)
        except (PluginError, OSError) as ex:
            raise _error(ex) from None

    return await run_in_threadpool(stage)


@router.delete("/{pid}")
def remove(request: Request, pid: str, revision: str) -> dict:
    _allowed(request)
    s = request.app.state
    try:
        s.plugin_manager.stage_remove(pid, revision)
    except (PluginError, OSError) as ex:
        raise _error(ex) from None
    s.restart_for.add("plugin_files")
    return _inventory(request)


@router.put("/{pid}/settings")
def save_settings(request: Request, pid: str, body: dict = Body(...)) -> dict:  # noqa: B008
    """Patch declared values; reset lists override keys to delete. Omitted passwords are preserved."""
    _allowed(request)
    s = request.app.state
    try:
        if set(body) - {"values", "reset"}:
            raise PluginError("Expected values and optional reset keys")
        values, reset = body.get("values", {}), body.get("reset", [])
        if not isinstance(values, dict) or not isinstance(reset, list) or any(not isinstance(k, str) for k in reset):
            raise PluginError("values must be an object and reset must be a list of field keys")
        json.dumps(values, allow_nan=False)
        with s.plugin_manager.lock:
            manifest = s.plugin_manager.settings_manifest(pid)
            declared = {setting.key for setting in manifest.settings}
            if (set(values) | set(reset)) - declared:
                raise PluginError("Only declared plugin settings can be edited")
            overrides = dict(s.saved.plugin_settings.get(pid, {}))
            for key in reset:
                overrides.pop(key, None)
            overrides.update(values)
            manifest.validate_settings(manifest.effective(s.base_config.plugins.get(pid, {}), overrides))
            new = replace_settings(s.saved, plugin_settings=s.saved.plugin_settings | {pid: overrides})
            new.save(s.store)
            apply_settings(request, new)
        return _inventory(request)
    except (PluginError, OSError, ValueError, TypeError) as ex:
        raise _error(ex) from None


@router.put("/{pid}/enabled")
def enable(request: Request, pid: str, body: dict = Body(...)) -> dict:  # noqa: B008
    _allowed(request)
    s = request.app.state
    if set(body) != {"enabled"} or type(body["enabled"]) is not bool:
        raise HTTPException(422, "enabled must be true or false")
    with s.plugin_manager.lock:
        if pid not in {item["id"] for item in _inventory(request)["items"]}:
            raise HTTPException(404, "No plugin with this id")
        disabled = set(s.saved.disabled_plugins)
        if body["enabled"]:
            disabled.discard(pid)
        else:
            disabled.add(pid)
        new = replace_settings(s.saved, disabled_plugins=sorted(disabled))
        new.save(s.store)
        apply_settings(request, new)
    return _inventory(request)
