"""User presets for a job's video processing and its encoder, and templates (core.template: the
whole run's settings), saved in the store.

Each profile's own defaults are the built-in presets (the UI has them from /api/profiles), with the
starter encoder presets (core.video.starters, listed here); these are the user's, on top. A video preset holds the source filter, resize, filter chain
and custom body, not the crop: that belongs to each source (a template says what to do with it).
Each profile can have one of the user's templates as its default: New jobs starts on it, and
jobs added with no settings of their own get it.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel, Field

from videoforge.core.audio_io import read_audio_bundle
from videoforge.core.audio_preset import AudioPresetSettings
from videoforge.core.encoder_io import read_encoder_bundle
from videoforge.core.models import TemplateSubs
from videoforge.core.plan_io import from_json, to_json
from videoforge.core.template import Template
from videoforge.core.template_io import MAX_BYTES, MAX_NAME, read_bundle
from videoforge.core.video.settings import EncoderSettings, VideoSettings
from videoforge.core.video.starters import starters

router = APIRouter(prefix="/api/presets")
KINDS: dict[str, type] = {
    "video": VideoSettings,
    "encoder": EncoderSettings,
    "audio": AudioPresetSettings,
    "template": Template,
}
DEFAULTS = "template_defaults"  # setting: {profile id: template name}
SUBS_DEFAULT = "subs_default"  # setting: subtitle rules (TemplateSubs) for new jobs whose template has none


class GroupedPresetBody(BaseModel):
    name: str | None = None  # storage identity; omitted when creating a preset
    label: str = Field(min_length=1, max_length=MAX_NAME)
    group: list[str] = Field(default_factory=list, max_length=8)
    data: dict[str, Any]


def _all(request: Request) -> dict[str, Any]:
    store = request.app.state.store
    out: dict[str, Any] = {kind: [_entry(kind, n, d) for n, d in store.presets(kind).items()] for kind in KINDS}
    out["template_defaults"] = template_defaults(store)
    default_subs = subs_default(store)
    out["subs_default"] = to_json(default_subs) if default_subs else None
    out["encoder_starters"] = [{"name": s.name, "label": s.label, "data": to_json(s.settings)} for s in starters()]
    return out


def _entry(kind: str, name: str, data: Any) -> dict[str, Any]:
    # Grouped presets wrap their settings in the existing JSON column. Older flat
    # presets stay readable without a database migration; metadata never enters a job's settings.
    if kind in ("encoder", "audio") and "settings" in data:
        return {"name": name, "label": data["label"], "group": data["group"], "data": _upgraded(kind, data["settings"])}
    return {"name": name, "data": _upgraded(kind, data)}


def _upgraded(kind: str, data: Any) -> Any:
    """A stored preset in the current shape (one saved by an older version is rewritten as it's read)."""
    try:
        return normalize(kind, data)
    except HTTPException:
        return data


def template_defaults(store: Any) -> dict[str, str]:
    """Each profile's default template, by name (only ones that still exist)."""
    saved = store.presets("template")
    return {pid: name for pid, name in (store.get_setting(DEFAULTS) or {}).items() if name in saved}


def subs_default(store: Any) -> TemplateSubs | None:
    """The subtitle rules every new job gets unless its template sets its own (Settings -> Default subtitles)."""
    data = store.get_setting(SUBS_DEFAULT)
    try:
        return from_json(TemplateSubs, data) if data else None
    except (TypeError, ValueError, KeyError, AttributeError):
        return None


def default_template(store: Any, profile_id: str) -> Template | None:
    name = template_defaults(store).get(profile_id)
    return from_json(Template, store.presets("template")[name]) if name else None


def _set_default(store: Any, profile_id: str, name: str | None) -> None:
    defaults = template_defaults(store)
    if name:
        defaults[profile_id] = name
    else:
        defaults.pop(profile_id, None)
    store.set_setting(DEFAULTS, defaults)


def _check_name(name: str) -> str:
    name = name.strip()
    if not name or len(name) > MAX_NAME:
        raise HTTPException(422, f"A preset name needs 1 to {MAX_NAME} characters")
    return name


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
def list_presets(request: Request) -> dict[str, Any]:
    return _all(request)


async def _bundle(request: Request, *, encoder: bool = False, audio: bool = False) -> dict[str, Any]:
    label = "Audio preset" if audio else "Encoder preset" if encoder else "Template"
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > MAX_BYTES:
            raise HTTPException(413, f"{label} files must be 5 MiB or smaller")
    try:
        reader = read_audio_bundle if audio else read_encoder_bundle if encoder else read_bundle
        return reader(json.loads(raw))
    except (ValueError, RecursionError) as ex:
        raise HTTPException(422, f"Invalid {label.lower()} file: {ex}") from None


@router.post("/audio/export")
async def export_audio(request: Request) -> dict[str, Any]:
    return await _bundle(request, audio=True)


@router.post("/audio/preview")
async def preview_audio(request: Request) -> dict[str, Any]:
    bundle = await _bundle(request, audio=True)
    names = request.app.state.store.import_preset_pack({"audio": bundle["audio"]}, max_name=MAX_NAME, preview=True)
    return {"bundle": bundle, "names": names["audio"]}


@router.post("/audio/import")
async def import_audio(request: Request) -> dict[str, Any]:
    bundle = await _bundle(request, audio=True)
    names = request.app.state.store.import_preset_pack({"audio": bundle["audio"]}, max_name=MAX_NAME)
    return {"presets": _all(request), "names": names["audio"]}


@router.post("/encoders/export")
async def export_encoders(request: Request) -> dict[str, Any]:
    return await _bundle(request, encoder=True)


@router.post("/encoders/preview")
async def preview_encoders(request: Request) -> dict[str, Any]:
    bundle = await _bundle(request, encoder=True)
    names = request.app.state.store.import_encoder_presets(bundle["encoders"], max_name=MAX_NAME, preview=True)
    return {"bundle": bundle, "names": names}


@router.post("/encoders/import")
async def import_encoders(request: Request) -> dict[str, Any]:
    bundle = await _bundle(request, encoder=True)
    names = request.app.state.store.import_encoder_presets(bundle["encoders"], max_name=MAX_NAME)
    return {"presets": _all(request), "names": names}


@router.post("/templates/export")
async def export_templates(request: Request) -> dict[str, Any]:
    """Export saved templates, built-in defaults, or the editor's unsaved settings."""
    return await _bundle(request)


@router.post("/templates/preview")
async def preview_templates(request: Request) -> dict[str, Any]:
    bundle = await _bundle(request)
    names = _import_names(request, bundle, preview=True)
    return {"bundle": bundle, "names": names}


@router.post("/templates/import")
async def import_templates(request: Request) -> dict[str, Any]:
    bundle = await _bundle(request)
    names = _import_names(request, bundle)
    return {"presets": _all(request), "names": names}


def _import_names(request: Request, bundle: dict[str, Any], *, preview: bool = False) -> list[str]:
    state = request.app.state
    reserved = tuple(f"{state.queue.profiles(pid).name} defaults" for pid in state.profile_ids)
    return state.store.import_presets(
        "template", bundle["templates"], max_name=MAX_NAME, preview=preview, reserved=reserved
    )


@router.put("/template-default/{profile_id}")
def set_template_default(request: Request, profile_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    """{name}: the profile's default template; null: back to the profile's own defaults."""
    store = request.app.state.store
    if profile_id not in request.app.state.profile_ids:
        raise HTTPException(404, f"No profile {profile_id!r}")
    name = body.get("name")
    if name and name not in store.presets("template"):
        raise HTTPException(404, f"No template {name!r}")
    _set_default(store, profile_id, name or None)
    return _all(request)


@router.put("/subs-default")
def set_subs_default(request: Request, body: dict[str, Any] | None = Body(None)) -> dict[str, Any]:  # noqa: B008
    """Subtitle rules (a template's `subs`) for every new job whose template has none; null: none."""
    store = request.app.state.store
    if body is None:
        store.set_setting(SUBS_DEFAULT, None)
    else:
        try:
            rules = from_json(TemplateSubs, body)
        except (TypeError, ValueError, KeyError, AttributeError) as ex:
            raise HTTPException(422, f"Bad subtitle rules: {ex}") from None
        store.set_setting(SUBS_DEFAULT, to_json(rules))
    return _all(request)


@router.put("/{kind}/{name:path}")
def save_preset(request: Request, kind: str, name: str, data: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    store = request.app.state.store
    name = _check_name(name)
    settings = normalize(kind, data)
    old = store.presets(kind).get(name, {})
    if kind in ("encoder", "audio") and "settings" in old:
        settings = {**old, "settings": settings}
    store.save_preset(kind, name, settings)
    return _all(request)


@router.post("/encoder")
def save_encoder_preset(request: Request, body: GroupedPresetBody) -> dict[str, Any]:
    """Create or update an encoder preset. Names can repeat in different encoders or folders."""
    return _save_grouped(request, "encoder", body)


@router.post("/audio")
def save_audio_preset(request: Request, body: GroupedPresetBody) -> dict[str, Any]:
    """Create or update an audio preset with an optional custom title, without languages, flags, or timing."""
    return _save_grouped(request, "audio", body)


def _save_grouped(request: Request, kind: str, body: GroupedPresetBody) -> dict[str, Any]:
    label = _check_name(body.label)
    group = [_check_name(part) for part in body.group]
    if any("/" in part for part in group):
        raise HTTPException(422, "A folder name cannot contain /")
    data = normalize(kind, body.data)
    store = request.app.state.store
    saved = store.presets(kind)
    if body.name is not None and body.name not in saved:
        raise HTTPException(404, f"No {kind} preset {body.name!r}")
    parent = "encoder" if kind == "encoder" else "action"
    for name, record in saved.items():
        entry = _entry(kind, name, record)
        if (
            name != body.name
            and entry.get("label", name) == label
            and entry.get("group", []) == group
            and entry["data"][parent] == data[parent]
        ):
            raise HTTPException(409, f"An {kind} preset with this name already exists in this folder")
    name = body.name if body.name is not None else uuid4().hex
    store.save_preset(kind, name, {"label": label, "group": group, "settings": data})
    return _all(request)


@router.post("/{kind}/{name:path}/rename")
def rename_preset(request: Request, kind: str, name: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    """{to}: a new name (replacing a preset of that name); a default template stays the default."""
    _kind(kind)
    store = request.app.state.store
    to = _check_name(str(body.get("to") or ""))
    saved = store.presets(kind)
    if name not in saved:
        raise HTTPException(404, f"No {kind} preset {name!r}")
    if to != name:
        defaults = template_defaults(store) if kind == "template" else {}
        data = saved[name]
        if kind in ("encoder", "audio") and "settings" in data:
            data = {**data, "label": to}
        store.save_preset(kind, to, data)
        store.delete_preset(kind, name)
        for pid, n in defaults.items():
            if n == name:
                _set_default(store, pid, to)
    return _all(request)


@router.delete("/{kind}/{name:path}")
def delete_preset(request: Request, kind: str, name: str) -> dict[str, Any]:
    _kind(kind)
    request.app.state.store.delete_preset(kind, name)  # a default it was falls back to the profile's
    return _all(request)
