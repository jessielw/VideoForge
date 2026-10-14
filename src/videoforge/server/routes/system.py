"""Folder browser, profiles, app settings, health, and the event WebSocket."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, Request, WebSocket, WebSocketDisconnect

from videoforge.core.execute.mux import MUXERS
from videoforge.core.plan_io import to_json
from videoforge.core.template import Template
from videoforge.server.events import EventHub

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True}


# --- folder browser -------------------------------------------------------------------


@router.get("/fs/roots")
def roots(request: Request) -> list[str]:
    return [str(p) for p in request.app.state.settings.roots]


@router.get("/fs/list")
def list_dir(request: Request, path: str, extensions: str = "") -> dict[str, Any]:
    """A folder's subfolders and files (files filtered by comma-separated extensions)."""
    folder = Path(path)
    allowed = request.app.state.settings.roots
    if allowed and not any(_under(folder, r) for r in allowed):
        raise HTTPException(403, "Outside the browsable folders")
    if not folder.is_dir():
        raise HTTPException(404, f"No folder {path}")
    wanted = {e.strip().lower() for e in extensions.split(",") if e.strip()}
    dirs, files = [], []
    try:
        with os.scandir(folder) as it:
            for entry in it:
                try:
                    if entry.is_dir():
                        dirs.append({"name": entry.name, "path": entry.path})
                    elif not wanted or Path(entry.name).suffix.lower() in wanted:
                        st = entry.stat()
                        files.append({"name": entry.name, "path": entry.path, "size": st.st_size,
                                      "mtime": st.st_mtime})
                except OSError:
                    continue
    except OSError as ex:
        raise HTTPException(403, str(ex)) from None
    key = lambda d: d["name"].lower()
    parent = str(folder.parent) if folder.parent != folder else None
    return {"path": str(folder), "parent": parent, "dirs": sorted(dirs, key=key), "files": sorted(files, key=key)}


@router.post("/fs/kinds")
def path_kinds(request: Request, paths: list[str] = Body(..., embed=True)) -> list[dict[str, str]]:  # noqa: B008
    """What each dropped or pasted path is: file, folder, missing, or outside the browsable folders."""
    allowed = request.app.state.settings.roots
    out = []
    for raw in paths:
        p = Path(raw)
        if not p.is_absolute():
            kind = "missing"
        elif allowed and not any(_under(p, r) for r in allowed):
            kind = "outside"
        else:
            kind = "folder" if p.is_dir() else "file" if p.is_file() else "missing"
        out.append({"path": str(p) if p.is_absolute() else raw, "kind": kind})
    return out


def _under(path: Path, root: Path) -> bool:
    # No resolve(): a mapped network drive would turn into its UNC path.
    p, r = (os.path.normcase(os.path.abspath(x)) for x in (path, root))
    return p == r or p.startswith(r.rstrip("\\/") + os.sep)


@router.post("/shutdown")
def shutdown(request: Request, tasks: BackgroundTasks) -> dict[str, Any]:
    """Stop VideoForge (a running job is cancelled). How depends on how it runs: `serve` and the window
    each set `app.state.shutdown`. It runs once this reply has gone out."""
    stop = getattr(request.app.state, "shutdown", None)
    if stop is None:
        raise HTTPException(404, "This server can't be stopped from the page")
    tasks.add_task(stop)
    return {"ok": True}


@router.post("/window/show")
def show_window(request: Request) -> dict[str, Any]:
    """Bring up the app's window (`serve --window`), e.g. when it is started a second time."""
    show = getattr(request.app.state, "show_window", None)
    if show is None:
        raise HTTPException(404, "No window: this server runs in the browser")
    show()
    return {"ok": True}


# --- profiles and settings -----------------------------------------------------------


@router.get("/profiles")
def profiles(request: Request) -> list[dict[str, Any]]:
    out = []
    for pid in request.app.state.profile_ids:
        p = request.app.state.queue.profiles(pid)
        video, encoder = p.video_defaults()
        out.append({
            "id": pid, "name": p.name, "container": p.container, "external_subtitles": p.external_subtitles,
            "containers": [{"id": c, "label": MUXERS[c].label, "extension": MUXERS[c].extension, "tool": MUXERS[c].tool}
                           for c in dict.fromkeys((p.container, *p.containers))],
            "track_properties": [to_json(t) for t in p.track_properties], "track_editor": p.track_editor,
            "defaults": {"video": to_json(video), "encoder": to_json(encoder),
                         "template": to_json(Template.defaults(p))},
            "default": pid == request.app.state.default_profile,
        })
    return out


@router.get("/settings")
def get_settings(request: Request) -> dict[str, Any]:
    store = request.app.state.store
    return {"output_dir": store.get_setting("output_dir", ""), "last_dir": store.get_setting("last_dir", "")}


@router.put("/settings")
def put_settings(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    store = request.app.state.store
    for key in ("output_dir", "last_dir"):
        if key in body:
            store.set_setting(key, body[key])
    return get_settings(request)


# --- events -------------------------------------------------------------------------


@router.websocket("/events")
async def events(ws: WebSocket) -> None:
    hub: EventHub = ws.app.state.events
    await ws.accept()
    q = hub.subscribe()

    async def send() -> None:
        await ws.send_json({"type": "hello", **ws.app.state.queue.queue_state()})
        while True:
            await ws.send_json(await q.get())

    # Also read, or a closed connection (the page gone, or the server shutting down) would only be noticed
    # at the next event, and the server's shutdown would wait for this handler until its timeout.
    sender = asyncio.create_task(send())
    try:
        while (await ws.receive())["type"] != "websocket.disconnect":
            pass
    except (WebSocketDisconnect, asyncio.CancelledError, RuntimeError):
        pass
    finally:
        sender.cancel()
        hub.unsubscribe(q)
