"""User presets for a job's video processing and its encoder, and templates (core.template: the
whole run's settings), saved in the store.

Each profile's own defaults are the built-in presets (the UI has them from /api/profiles);
these are the user's, on top. A video preset holds the source filter, resize, filter chain
and custom body, not the crop: that belongs to each source (a template says what to do with it).
Each profile can have one of the user's templates as its default: New jobs starts on it, and
jobs added with no settings of their own get it.
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
DEFAULTS = "template_defaults"  # setting: {profile id: template name}


def _all(request: Request) -> dict[str, Any]:
    store = request.app.state.store
    out: dict[str, Any] = {
        kind: [{"name": n, "data": _upgraded(kind, d)} for n, d in store.presets(kind).items()] for kind in KINDS
    }
    out["template_defaults"] = template_defaults(store)
    return out


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


@router.put("/{kind}/{name}")
def save_preset(request: Request, kind: str, name: str, data: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    request.app.state.store.save_preset(kind, _check_name(name), normalize(kind, data))
    return _all(request)


@router.post("/{kind}/{name}/rename")
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
        store.save_preset(kind, to, saved[name])
        store.delete_preset(kind, name)
        for pid, n in defaults.items():
            if n == name:
                _set_default(store, pid, to)
    return _all(request)


@router.delete("/{kind}/{name}")
def delete_preset(request: Request, kind: str, name: str) -> dict[str, Any]:
    _kind(kind)
    request.app.state.store.delete_preset(kind, name)  # a default it was falls back to the profile's
    return _all(request)
