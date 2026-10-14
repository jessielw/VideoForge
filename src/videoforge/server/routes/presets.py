"""User presets for a job's video processing and its encoder, and templates (core.template: the
whole run's settings), saved in the store.

Each profile's own defaults are the built-in presets (the UI has them from /api/profiles);
these are the user's, on top. A video preset holds the source filter, resize, filters
and custom body, not the crop: that belongs to each source (a template says what to do with it).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request

from videoforge.core.plan_io import from_json, to_json
from videoforge.core.template import Template
from videoforge.core.video.settings import EncoderSettings, VideoSettings

router = APIRouter(prefix="/api/presets")
KINDS: dict[str, type] = {"video": VideoSettings, "encoder": EncoderSettings, "template": Template}
MAX_NAME = 80


def _all(request: Request) -> dict[str, list[dict[str, Any]]]:
    store = request.app.state.store
    return {kind: [{"name": n, "data": d} for n, d in store.presets(kind).items()] for kind in KINDS}


def _kind(kind: str) -> type:
    if kind not in KINDS:
        raise HTTPException(404, f"No preset kind {kind!r}")
    return KINDS[kind]


def normalize(kind: str, data: Any) -> dict[str, Any]:
    """The preset as stored: every field filled in, a video preset without its crop."""
    try:
        value = from_json(_kind(kind), data)
    except (TypeError, ValueError, KeyError, AttributeError) as ex:
        raise HTTPException(422, f"Bad {kind} settings: {ex}") from None
    out = to_json(value)
    if kind == "video":
        out.pop("crop", None)
    return out


@router.get("")
def list_presets(request: Request) -> dict[str, list[dict[str, Any]]]:
    return _all(request)


@router.put("/{kind}/{name}")
def save_preset(request: Request, kind: str, name: str, data: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    name = name.strip()
    if not name or len(name) > MAX_NAME:
        raise HTTPException(422, f"A preset name needs 1 to {MAX_NAME} characters")
    request.app.state.store.save_preset(kind, name, normalize(kind, data))
    return _all(request)


@router.delete("/{kind}/{name}")
def delete_preset(request: Request, kind: str, name: str) -> dict[str, Any]:
    _kind(kind)
    request.app.state.store.delete_preset(kind, name)
    return _all(request)
