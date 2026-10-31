"""Profiles: whole configurations (Settings, templates and the preset libraries), one active at a time.

A new profile starts as a fresh install does, or as a copy of the active one. Switching applies the
other profile's settings at once, as an import does; it waits for the queue to stop, since its tools and
folders may differ. The queue itself is shared by every profile.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request

from videoforge.core.config import AppConfig
from videoforge.core.plan_io import from_json
from videoforge.server.configuration import BASE_KEY
from videoforge.server.routes import config, presets
from videoforge.server.settings import SavedSettings
from videoforge.server.store import ProfileInUse

router = APIRouter(prefix="/api/profiles")


def _list(request: Request) -> dict[str, Any]:
    store = request.app.state.store
    return {"profiles": store.profiles(), "active": store.profile}


def idle(request: Request) -> None:
    """409 while the queue runs or a job is busy: settings that change under a run would mix two setups."""
    q = request.app.state.queue
    if q.running or any(e.busy or e.indexing or e.sampling for e in q.entries()):
        raise HTTPException(409, "Stop the queue and wait for indexing and test encodes to finish first")


@router.get("")
def list_profiles(request: Request) -> dict[str, Any]:
    return _list(request)


@router.post("")
def create_profile(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    """{name, copy}: a new profile, as a fresh install (copy false) or a copy of the active one."""
    store = request.app.state.store
    try:
        store.create_profile(body.get("name"), store.profile if body.get("copy") else None)
    except ValueError as ex:
        raise HTTPException(422, str(ex)) from None
    return _list(request)


@router.patch("/{profile_id}")
def rename_profile(request: Request, profile_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    try:
        request.app.state.store.rename_profile(profile_id, body.get("name"))
    except KeyError:
        raise HTTPException(404, "No such profile") from None
    except ValueError as ex:
        raise HTTPException(422, str(ex)) from None
    return _list(request)


@router.delete("/{profile_id}")
def delete_profile(request: Request, profile_id: str) -> dict[str, Any]:
    try:
        request.app.state.store.delete_profile(profile_id)
    except KeyError:
        raise HTTPException(404, "No such profile") from None
    except ProfileInUse as ex:
        raise HTTPException(409, str(ex)) from None
    return _list(request)


@router.post("/{profile_id}/activate")
def activate_profile(request: Request, profile_id: str) -> dict[str, Any]:
    """Make it the active profile and apply its settings: {profiles, active, config, presets}."""
    state = request.app.state
    if profile_id != state.store.profile:
        idle(request)
        try:
            state.store.switch_profile(profile_id)
        except KeyError:
            raise HTTPException(404, "No such profile") from None
        restored = state.store.get_setting(BASE_KEY)
        state.base_config = from_json(AppConfig, restored) if restored else state.file_config
        if state.base_config.plugins != state.plugin_base_at_start:
            state.restart_for.add("profile")
        else:
            state.restart_for.discard("profile")
        config.apply_settings(request, SavedSettings.load(state.store))
    return _list(request) | {"config": config._state(request), "presets": presets._all(request)}
