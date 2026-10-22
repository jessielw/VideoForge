"""Selective preset sharing that never exports or imports application settings."""

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request

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


def _names(request: Request, bundle: dict[str, Any], *, preview: bool = False) -> dict[str, list[str]]:
    state = request.app.state
    reserved = tuple(f"{state.queue.profiles(pid).name} defaults" for pid in state.profile_ids)
    return state.store.import_preset_pack(
        bundle["presets"], max_name=MAX_NAME, preview=preview, reserved={"template": reserved, "video": reserved}
    )


@router.post("/export")
async def export_preset_pack(request: Request) -> dict[str, Any]:
    return await _read(request)


@router.post("/preview")
async def preview_preset_pack(request: Request) -> dict[str, Any]:
    bundle = await _read(request)
    return {"bundle": bundle, "names": _names(request, bundle, preview=True)}


@router.post("/import")
async def import_preset_pack(request: Request) -> dict[str, Any]:
    bundle = await _read(request)
    names = _names(request, bundle)
    return {"presets": presets._all(request), "names": names}
