"""Folder browser, profiles, app settings, health, and the event WebSocket."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import os
from pathlib import Path
import re
import shutil
import stat
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, Request, WebSocket, WebSocketDisconnect

from videoforge import version
from videoforge.core.execute.mux import MUXERS
from videoforge.core.plan_io import to_json
from videoforge.core.template import Template
from videoforge.core.video.filters import PRESETS
from videoforge.server.events import EventHub

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "version": version()}


# --- folder browser -------------------------------------------------------------------


@router.get("/fs/roots")
def roots(request: Request) -> list[str]:
    return [str(p) for p in request.app.state.settings.roots]


_WINDOWS_PROGRAMS = {".exe", ".bat", ".cmd", ".com"}


def _is_program(entry: os.DirEntry[str]) -> bool:
    """A file a tool path can point at: on Windows by its extension; elsewhere one that can run, or has no
    extension (a program whose execute bit got lost, e.g. copied over SMB: the tool check then says so)."""
    suffix = Path(entry.name).suffix.lower()
    if os.name == "nt":
        return suffix in _WINDOWS_PROGRAMS
    return not suffix or os.access(entry.path, os.X_OK)


@router.get("/fs/list")
def list_dir(request: Request, path: str, extensions: str = "", programs: bool = False) -> dict[str, Any]:
    """A folder's subfolders and files (files filtered by comma-separated extensions, or to programs)."""
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
                    elif _is_program(entry) if programs else not wanted or Path(entry.name).suffix.lower() in wanted:
                        st = entry.stat()
                        files.append({"name": entry.name, "path": entry.path, "size": st.st_size, "mtime": st.st_mtime})
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


def _browsable(request: Request, path: str) -> Path:
    """An absolute path inside the browsable folders (403 outside them)."""
    p = Path(path)
    allowed = request.app.state.settings.roots
    if not p.is_absolute() or (allowed and not any(_under(p, r) for r in allowed)):
        raise HTTPException(403, "Outside the browsable folders")
    return p


@router.post("/fs/mkdir")
def make_dir(request: Request, path: str = Body(...), name: str = Body(...)) -> dict[str, str]:
    """A new folder `name` in the folder `path`."""
    clean = name.strip()
    if not clean or clean in (".", "..") or re.search(r'[<>:"/\\|?*\x00-\x1f]', clean):
        raise HTTPException(422, f"Not a folder name: {name}")
    folder = _browsable(request, path) / clean
    try:
        folder.mkdir()
    except FileExistsError:
        raise HTTPException(409, f"{clean} already exists") from None
    except OSError as ex:
        raise HTTPException(403, str(ex)) from None
    return {"path": str(folder)}


@router.get("/fs/contents")
def dir_contents(request: Request, path: str) -> dict[str, int]:
    """What deleting a folder would take with it: its files and subfolders (all the way down), and their size."""
    folder = _browsable(request, path)
    if not folder.is_dir():
        raise HTTPException(404, f"No folder {path}")
    files = dirs = size = 0
    for here, subdirs, names in os.walk(folder, onerror=lambda _: None):
        dirs += len(subdirs)
        # Links and junctions to folders are deleted, not what they point at: don't count into them.
        subdirs[:] = [d for d in subdirs if not (os.path.islink(p := os.path.join(here, d)) or os.path.isjunction(p))]
        for n in names:
            files += 1
            try:
                size += os.lstat(os.path.join(here, n)).st_size
            except OSError:
                pass
    return {"files": files, "dirs": dirs, "bytes": size}


@router.post("/fs/rmdir")
def remove_dir(request: Request, path: str = Body(...), recursive: bool = Body(False)) -> dict[str, str]:
    """Delete a folder; one with anything in it only when `recursive`. Never a browsable root or a drive."""
    folder = _browsable(request, path)
    roots = request.app.state.settings.roots
    if folder.parent == folder or any(_under(r, folder) for r in roots):
        raise HTTPException(403, f"{folder} can't be deleted")
    if folder.is_symlink() or folder.is_junction():
        raise HTTPException(422, f"{folder.name} is a link to a folder, not one")
    if not folder.is_dir():
        raise HTTPException(404, f"No folder {path}")
    try:
        if recursive:
            shutil.rmtree(folder, onexc=_clear_read_only)
        else:
            folder.rmdir()
    except OSError as ex:
        if not recursive and any(folder.iterdir()):
            raise HTTPException(409, f"{folder.name} isn't empty") from None
        raise HTTPException(403, str(ex)) from None
    return {"path": str(folder)}


def _clear_read_only(func: Callable[[str], object], path: str, _: BaseException) -> None:
    # Windows won't delete a read-only file; clear the flag and try once more.
    os.chmod(path, stat.S_IWRITE)
    func(path)


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
        out.append(
            {
                "id": pid,
                "name": p.name,
                "container": p.container,
                "external_subtitles": p.external_subtitles,
                "containers": [
                    {"id": c, "label": MUXERS[c].label, "extension": MUXERS[c].extension, "tool": MUXERS[c].tool}
                    for c in dict.fromkeys((p.container, *p.containers))
                ],
                "track_properties": [to_json(t) for t in p.track_properties],
                "track_editor": p.track_editor,
                "picks_tracks": p.picks_tracks,
                "defaults": {
                    "video": to_json(video),
                    "encoder": to_json(encoder),
                    "template": to_json(Template.defaults(p)),
                },
                "default": pid == request.app.state.default_profile,
            }
        )
    return out


@router.get("/filter-presets")
def filter_presets() -> list[dict[str, Any]]:
    """The built-in filter presets (core.video.filters), in their categories' chain order."""
    return [to_json(p) for p in sorted(PRESETS, key=lambda p: p.category.rank)]


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
