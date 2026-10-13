"""The FastAPI app: the API under /api, the built Svelte app everywhere else.

create_app() wires the engine to the web: app config, profiles, the SQLite store,
the job queue (and its worker) and the event hub. Tests pass their own settings
and fake services.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from videoforge.core.config import AppConfig, load_app_config, with_tools
from videoforge.core.history import JobHistory
from videoforge.core.profile import Profile
from videoforge.core.video import vs as vsx
from videoforge.server.events import EventHub
from videoforge.server.queue import JobQueue, Services
from videoforge.server.routes import config, jobs, queue, system, video
from videoforge.server.settings import SavedSettings, ServerSettings
from videoforge.server.store import Store


def create_app(
    settings: ServerSettings | None = None,
    app_config: AppConfig | None = None,
    *,
    profiles: Callable[[str], Profile] | None = None,
    profile_ids: list[str] | None = None,
    services: Services | None = None,
    setup_vapoursynth: bool = True,
) -> FastAPI:
    from videoforge.profiles import default_profile_id, get_profile
    from videoforge.profiles import profile_ids as registered

    settings = settings or ServerSettings()
    base = app_config or load_app_config()  # videoforge.toml (+ .local); the Settings page layers over it
    ids = profile_ids or registered()
    if services is None:
        history = JobHistory(settings.data_dir / "history")
        services = Services(record=history.record)

    store = Store(settings.db_path)
    saved = SavedSettings.load(store)
    default = default_profile_id(saved.profile or base.profile, ids)
    cfg = replace(with_tools(base, saved.tools), profile=default)
    default_roots = list(settings.roots)
    if saved.roots:
        settings.roots = [Path(r) for r in saved.roots]
    events = EventHub()
    job_queue = JobQueue(cfg, profiles or get_profile, store, events, services, settings.probe_workers)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        events.bind(asyncio.get_running_loop())
        if setup_vapoursynth:
            vsx.configure(cfg.tools.vs_plugins)
            await asyncio.to_thread(vsx.ensure_vspipe, cfg.tools.vspipe)
        job_queue.load()
        try:
            yield
        finally:
            job_queue.shutdown()
            store.close()

    app = FastAPI(title="VideoForge", lifespan=lifespan)
    app.state.settings = settings
    app.state.base_config = base
    app.state.default_roots = default_roots
    app.state.saved = saved
    app.state.restart_for = set()  # settings changed since start that need a restart to take full effect
    app.state.config = cfg
    app.state.store = store
    app.state.events = events
    app.state.queue = job_queue
    app.state.clips = vsx.ClipCache()
    app.state.profile_ids = ids
    app.state.default_profile = default
    for module in (jobs, queue, video, system, config):
        app.include_router(module.router)
    _mount_frontend(app, settings)
    return app


def _mount_frontend(app: FastAPI, settings: ServerSettings) -> None:
    """Serve frontend/dist; any non-API path falls back to index.html (client-side routes)."""
    dist = settings.frontend_dir
    index = dist / "index.html"
    if not index.is_file():
        return
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str, request: Request) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(404)
        file = (dist / path).resolve()
        if path and file.is_file() and dist.resolve() in file.parents:
            return FileResponse(file)
        return FileResponse(index)
