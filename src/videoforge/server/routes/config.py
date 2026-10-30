"""The Settings page: tool paths (with each tool found and its version), folder-browser roots,
the default profile, whether batch indexing waits for an encode on the same disk, where
notifications go (Apprise URLs, each with the events it wants), the actions run after a job or the
queue ends, and which plugins load.

Changes are saved in the store (layered over videoforge.toml) and applied at once: new
jobs, probes and runs use them. Switching a plugin on or off takes effect on the next start.
"""

from __future__ import annotations

from contextlib import suppress
from dataclasses import asdict
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request

from videoforge.core.actions import ACTION_LABELS, JOB_TOKENS, QUEUE_TOKENS, Action
from videoforge.core.config import with_tools
from videoforge.core.execute.audio import ENCODES
from videoforge.core.execute.control import Priority
from videoforge.core.notify import DEFAULT_EVENTS, EVENT_LABELS, Destination
from videoforge.core.plan_io import to_json
from videoforge.core.tools import TOOL_NAMES, TOOLS, check, detect, missing_for_encodes
from videoforge.core.video import options as video_options, vs as vsx
from videoforge.core.video.settings import Encoder
from videoforge.plugins.loader import describe as describe_plugins
from videoforge.profiles import default_profile_id
from videoforge.server.settings import MAX_PARALLEL_AUDIO, SavedSettings

router = APIRouter(prefix="/api/config")
RESTART_FOR: dict[str, str] = {  # setting -> why VideoForge needs a restart for it
    "plugins": "Plugins switched on or off load (or stop loading) when VideoForge starts again.",
    "configuration": "Imported plugin settings take effect when VideoForge starts again.",
    "plugin_files": "Installed, replaced or removed plugins take effect when VideoForge starts again.",
    "plugin_settings": "Plugin settings take effect when VideoForge starts again.",
}


def _state(request: Request) -> dict[str, Any]:
    s = request.app.state
    saved: SavedSettings = s.saved
    base_tools, tools = asdict(s.base_config.tools), asdict(s.config.tools)
    ids = s.profile_ids
    profiles = s.queue.profiles
    return {
        "tools": [
            {
                "name": t.name,
                "label": t.label,
                "purpose": t.purpose,
                "folder": t.folder,
                "path": tools[t.name],
                "default": base_tools[t.name],
                "custom": saved.tools.get(t.name),
            }
            for t in TOOLS
        ],
        "roots": [str(r) for r in s.settings.roots],
        "roots_custom": saved.roots is not None,
        "default_roots": [str(r) for r in s.default_roots],
        "profile": s.default_profile,
        "profile_default": default_profile_id(s.base_config.profile, ids),
        "profiles": [{"id": pid, "name": profiles(pid).name} for pid in ids],
        "restart": [RESTART_FOR[n] for n in sorted(s.restart_for)],
        "index_waits_for_disk": saved.index_waits_for_disk,
        "sample_quality": saved.sample_quality,
        "parallel_audio": s.config.parallel_audio,
        "parallel_audio_default": s.base_config.parallel_audio,
        "delete_work_dir": s.config.delete_work_dir,
        "delete_work_dir_default": s.base_config.delete_work_dir,
        "encoder_priority": s.config.encoder_priority,
        "encoder_priority_default": s.base_config.encoder_priority,
        "tool_priority": s.config.tool_priority,
        "tool_priority_default": s.base_config.tool_priority,
        "priorities": [p.value for p in Priority],
        "records_dir": str(s.settings.records_dir),
        "notifications": [d.to_json() for d in saved.notifications],
        "notification_events": [
            {"id": e.value, "label": label, "default": e in DEFAULT_EVENTS} for e, label in EVENT_LABELS.items()
        ],
        "actions": [a.to_json() for a in saved.actions],
        "action_kinds": [{"id": k.value, "label": label} for k, label in ACTION_LABELS.items()],
        "action_tokens": {"job": JOB_TOKENS, "queue": QUEUE_TOKENS},
        "allow_commands": s.base_config.allow_commands,
        "plugins": describe_plugins(s.plugins.report, saved.disabled_plugins) | {"folder": str(s.settings.plugins_dir)},
    }


@router.get("")
def get_config(request: Request) -> dict[str, Any]:
    return _state(request)


@router.put("")
def put_config(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    """Change any of: tools ({name: path, or "" / null for the default}), roots (a list, or null
    for every drive), profile (an id, or null for videoforge.toml's), index_waits_for_disk (bool),
    sample_quality (bool: a test encode measures its SSIMULACRA2 and XPSNR),
    parallel_audio (audio encodes at once beside the video, 0 to MAX_PARALLEL_AUDIO; null for videoforge.toml's),
    delete_work_dir (bool: delete a done job's work folder; null for videoforge.toml's),
    encoder_priority / tool_priority (a Priority; null for videoforge.toml's),
    notifications (the whole list: [{name, url, enabled, events}]), actions (the whole list:
    [{name, kind, target, enabled, events, overwrite}]), disabled_plugins (plugin ids)."""
    s = request.app.state
    saved: SavedSettings = s.saved
    tools = dict(saved.tools)
    for name, path in (body.get("tools") or {}).items():
        if name not in TOOL_NAMES:
            raise HTTPException(422, f"Unknown tool {name!r}")
        if path and str(path).strip():
            tools[name] = str(path).strip()
        else:
            tools.pop(name, None)
    roots = saved.roots
    if "roots" in body:
        roots = [str(r).strip() for r in body["roots"] if str(r).strip()] if body["roots"] is not None else None
        missing = [r for r in roots or [] if not os.path.isdir(r)]
        if missing:
            raise HTTPException(422, "Not a folder: " + ", ".join(missing))
        roots = roots or None
    profile = saved.profile
    if "profile" in body:
        profile = body["profile"] or None
        if profile is not None and profile not in s.profile_ids:
            raise HTTPException(422, f"No profile {profile!r} is installed")
    waits = bool(body["index_waits_for_disk"]) if "index_waits_for_disk" in body else saved.index_waits_for_disk
    quality = bool(body["sample_quality"]) if "sample_quality" in body else saved.sample_quality
    parallel = saved.parallel_audio
    if "parallel_audio" in body:
        parallel = body["parallel_audio"]
        if parallel is not None and (
            not isinstance(parallel, int) or isinstance(parallel, bool) or not 0 <= parallel <= MAX_PARALLEL_AUDIO
        ):
            raise HTTPException(422, f"parallel_audio: a whole number from 0 to {MAX_PARALLEL_AUDIO}")
    delete_work = saved.delete_work_dir
    if "delete_work_dir" in body:
        delete_work = body["delete_work_dir"]
        if delete_work is not None and not isinstance(delete_work, bool):
            raise HTTPException(422, "delete_work_dir: true, false or null")
    priorities = {}
    for key in ("encoder_priority", "tool_priority"):
        priorities[key] = getattr(saved, key)
        if key in body:
            if body[key] is not None and body[key] not in tuple(Priority):
                raise HTTPException(422, f"{key}: one of {', '.join(Priority)}, or null")
            priorities[key] = None if body[key] is None else Priority(body[key])
    destinations = saved.notifications
    if "notifications" in body:
        try:
            destinations = [Destination.from_json(d) for d in body["notifications"] or []]
        except (ValueError, TypeError, AttributeError) as ex:
            raise HTTPException(422, str(ex)) from None

    actions = saved.actions
    if "actions" in body:
        try:
            actions = [Action.from_json(a) for a in body["actions"] or []]
        except (ValueError, TypeError, AttributeError) as ex:
            raise HTTPException(422, str(ex)) from None
    disabled = saved.disabled_plugins
    if "disabled_plugins" in body:
        disabled = sorted({str(i) for i in body["disabled_plugins"] or []})

    new = SavedSettings(
        tools,
        roots,
        profile,
        waits,
        destinations,
        actions,
        disabled,
        parallel,
        delete_work,
        plugin_settings=saved.plugin_settings,
        sample_quality=quality,
        **priorities,
    )
    new.save(s.store)
    apply_settings(request, new)
    return _state(request)


def apply_settings(request: Request, new: SavedSettings) -> None:
    """Apply validated, persisted settings to the running services."""
    s = request.app.state
    before = s.config.tools
    s.saved = new
    s.queue.set_index_waits_for_disk(new.index_waits_for_disk)
    s.queue.set_sample_quality(new.sample_quality)
    s.notifier.destinations = new.notifications
    s.actions.actions = new.actions
    s.actions.allow_commands = s.base_config.allow_commands
    if frozenset(new.disabled_plugins) != s.plugins_off_at_start:
        s.restart_for.add("plugins")
    else:
        s.restart_for.discard("plugins")
    if new.plugin_settings != s.plugin_settings_at_start:
        s.restart_for.add("plugin_settings")
    else:
        s.restart_for.discard("plugin_settings")
    s.default_profile = default_profile_id(new.profile or s.base_config.profile, s.profile_ids)
    cfg = new.app_config(s.base_config, s.default_profile)
    s.config = cfg
    s.queue.app = cfg  # new probes and runs use it; a running job keeps the one it started with
    s.settings.roots = [Path(r) for r in new.roots] if new.roots else list(s.default_roots)
    if cfg.tools != before:
        s.queue.replan_all()  # an encode whose tool went missing (or came back) blocks (or unblocks)
    if cfg.tools.vs_plugins != before.vs_plugins:
        vsx.configure(cfg.tools.vs_plugins)  # vspipe runs inherit it from now on
        request.app.state.preview.restart("The VapourSynth plugin folder changed")  # ... and the next preview worker
    if cfg.tools.vspipe != before.vspipe:
        with suppress(Exception):  # a broken vspipe shows in the tools check
            vsx.ensure_vspipe(cfg.tools.vspipe)


@router.post("/notifications/test")
def test_notification(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    """Send a test message to an Apprise URL (saved or not): {ok}, or 400 with why it didn't go."""
    url = str(body.get("url") or "").strip()
    if not url:
        raise HTTPException(422, "No Apprise URL to test")
    error = request.app.state.notifier.test(url)
    if error:
        raise HTTPException(400, error)
    return {"ok": True}


@router.get("/encoders")
def encoders(request: Request) -> list[dict[str, Any]]:
    """The audio encodes (execute.audio.ENCODES) for the track editor: layouts, bitrates, and the
    tools each one is missing ([] = it can run)."""
    missing = missing_for_encodes(request.app.state.config.tools)
    return [
        {
            "id": e.action.value,
            "label": e.label,
            "codec": e.codec.value,
            "layouts": [str(x) for x in e.layouts],
            "bitrates": None if e.bitrates is None else {str(c): k for c, k in e.bitrates.items()},
            "bitrate_choices": list(e.bitrate_choices),
            "bitrate_range": e.bitrate_range,
            "per_channel_max": e.per_channel_max,
            "vbr_default": e.vbr_default,
            "default_max": str(e.default_max) if e.default_max else None,
            "missing": missing[e.action],
            "options": [
                {
                    "key": o.key,
                    "label": o.label,
                    "default": o.default,
                    "help": o.help,
                    "choices": [{"value": v, "label": lab} for v, lab in o.choices],
                    "range": list(o.range) if o.range else None,
                    "step": 1 if o.int_range else 0.1,
                    "when": {"key": o.when[0], "value": o.when[1]} if o.when else None,
                }
                for o in e.options
            ],
        }
        for e in ENCODES.values()
    ]


@router.get("/video-options/{encoder}")
def encoder_options(request: Request, encoder: Encoder) -> dict[str, Any]:
    """The option names a video encoder takes, from its own help (the Encoder tab's suggestions and checks):
    [] when the encoder isn't found or lists none."""
    known = video_options.known_options(encoder, request.app.state.config.tools)
    return {
        "dashes": video_options.dashes(encoder),
        "options": [{"name": k, "help": v} for k, v in sorted(known.items())],
    }


@router.get("/tools")
def tool_checks(request: Request) -> list[dict[str, Any]]:
    """Each tool: found or not, and its version (runs every tool's version command)."""
    return [to_json(c) for c in detect(request.app.state.config.tools)]


@router.post("/tools/check")
def check_path(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    """Check one tool at a path that isn't saved yet (the Test button)."""
    name, path = body.get("name"), str(body.get("path") or "").strip()
    info = next((t for t in TOOLS if t.name == name), None)
    if info is None:
        raise HTTPException(422, f"Unknown tool {name!r}")
    resolved = getattr(with_tools(request.app.state.base_config, {info.name: path}).tools, info.name) if path else ""
    return to_json(check(info, resolved))
