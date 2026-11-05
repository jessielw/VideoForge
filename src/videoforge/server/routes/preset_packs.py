"""Selective preset sharing that never exports or imports application settings."""

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from videoforge.core.template_io import MAX_NAME
from videoforge.server.preset_pack import MAX_BYTES, read_preset_pack
from videoforge.server.routes import presets

router = APIRouter(prefix="/api/preset-packs")


async def _read(request: Request) -> dict[str, Any]:
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > MAX_BYTES:
            raise HTTPException(413, "Preset packs must be 20 MiB or smaller")
    try:
        return read_preset_pack(json.loads(raw))
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError) as ex:
        raise HTTPException(422, f"Invalid preset pack: {ex}") from None


def _names(request: Request, bundle: dict[str, Any], *, preview: bool = False) -> dict[str, Any]:
    reserved = presets.reserved_names(request)
    names, actions = request.app.state.store.import_preset_pack(
        bundle["presets"],
        max_name=MAX_NAME,
        preview=preview,
        reserved={"template": reserved, "video": reserved},
        keep_both=presets.keep_both(request),
    )
    return {"names": names, "actions": actions}


class ManagedRef(BaseModel):
    plugin: str
    kind: str
    key: str


@router.get("/managed")
def managed_presets(request: Request) -> dict[str, Any]:
    """The presets plugins ship, in the active profile: each one's state (current, edited, removed), whether
    its plugin has a newer version of it, and any plugin pack that couldn't be read."""
    state = request.app.state
    return {"presets": state.store.managed_presets(), "problems": state.preset_pack_problems}


@router.post("/managed/reset")
def reset_managed_preset(ref: ManagedRef, request: Request) -> dict[str, Any]:
    """Put a managed preset back as its plugin ships it (discarding edits, or restoring a removed one)."""
    try:
        name = request.app.state.store.reset_managed(ref.plugin, ref.kind, ref.key)
    except KeyError:
        raise HTTPException(404, "No such preset in an installed plugin") from None
    return {"name": name, "presets": presets._all(request)}


@router.post("/export")
async def export_preset_pack(request: Request) -> dict[str, Any]:
    return await _read(request)


@router.post("/preview")
async def preview_preset_pack(request: Request) -> dict[str, Any]:
    bundle = await _read(request)
    return {"bundle": bundle} | _names(request, bundle, preview=True)


@router.post("/import")
async def import_preset_pack(request: Request) -> dict[str, Any]:
    bundle = await _read(request)
    names = _names(request, bundle)
    return {"presets": presets._all(request)} | names
