"""The Settings page: tool paths (with each tool found and its version), folder-browser roots,
and the default profile.

Changes are saved in the store (layered over videoforge.toml) and applied at once: new
jobs, probes and runs use them. Only the preview's VapourSynth plugin folder needs a restart.
"""

from __future__ import annotations

import os
from contextlib import suppress
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request

from videoforge.core.config import with_tools
from videoforge.core.plan_io import to_json
from videoforge.core.tools import TOOL_NAMES, TOOLS, check, detect, missing_for_encodes
from videoforge.core.video import vs as vsx
from videoforge.profiles import default_profile_id
from videoforge.server.settings import SavedSettings

router = APIRouter(prefix="/api/config")
RESTART_FOR = {"vs_plugins": "The preview loads VapourSynth plugins once: restart VideoForge to use the new folder there"}


def _state(request: Request) -> dict[str, Any]:
    s = request.app.state
    saved: SavedSettings = s.saved
    base_tools, tools = asdict(s.base_config.tools), asdict(s.config.tools)
    ids = s.profile_ids
    profiles = s.queue.profiles
    return {
        "tools": [{"name": t.name, "label": t.label, "purpose": t.purpose, "folder": t.folder,
                   "path": tools[t.name], "default": base_tools[t.name], "custom": saved.tools.get(t.name)}
                  for t in TOOLS],
        "roots": [str(r) for r in s.settings.roots],
        "roots_custom": saved.roots is not None,
        "default_roots": [str(r) for r in s.default_roots],
        "profile": s.default_profile,
        "profile_default": default_profile_id(s.base_config.profile, ids),
        "profiles": [{"id": pid, "name": profiles(pid).name} for pid in ids],
        "restart": [RESTART_FOR[n] for n in sorted(s.restart_for)],
    }


@router.get("")
def get_config(request: Request) -> dict[str, Any]:
    return _state(request)


@router.put("")
def put_config(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    """Change any of: tools ({name: path, or "" / null for the default}), roots (a list, or null
    for every drive), profile (an id, or null for videoforge.toml's)."""
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

    before = s.config.tools
    new = SavedSettings(tools, roots, profile)
    new.save(s.store)
    s.saved = new
    s.default_profile = default_profile_id(profile or s.base_config.profile, s.profile_ids)
    cfg = replace(with_tools(s.base_config, tools), profile=s.default_profile)
    s.config = cfg
    s.queue.app = cfg  # new probes and runs use it; a running job keeps the one it started with
    s.settings.roots = [Path(r) for r in roots] if roots else list(s.default_roots)
    if cfg.tools != before:
        s.queue.replan_all()  # an encode whose tool went missing (or came back) blocks (or unblocks)
    if cfg.tools.vs_plugins != before.vs_plugins:
        vsx.configure(cfg.tools.vs_plugins)  # vspipe runs inherit it from now on
        s.restart_for.add("vs_plugins")
    if cfg.tools.vspipe != before.vspipe:
        with suppress(Exception):  # a broken vspipe shows in the tools check
            vsx.ensure_vspipe(cfg.tools.vspipe)
    return _state(request)


@router.get("/encoders")
def encoders(request: Request) -> dict[str, list[str]]:
    """Each audio encode's missing tools ([] = available); cheap (looks for the files only)."""
    return {action.value: missing for action, missing in missing_for_encodes(request.app.state.config.tools).items()}


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
    resolved = getattr(with_tools(request.app.state.base_config, {name: path}).tools, name) if path else ""
    return to_json(check(info, resolved))
