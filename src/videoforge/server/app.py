"""The FastAPI app: the API under /api, the built Svelte app everywhere else.

create_app() wires the engine to the web: app config, profiles, the SQLite store,
the job queue (and its worker) and the event hub. Tests pass their own settings
and fake services.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from functools import partial
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from videoforge.core.actions import ActionRunner
from videoforge.core.config import AppConfig, load_app_config
from videoforge.core.events import EventBus, JobFinished, QueueFinished
from videoforge.core.notify import Notifier
from videoforge.core.profile import Profile
from videoforge.core.record import QUEUE_EVENTS, QUEUE_EVENTS_MAX, JsonLines, event
from videoforge.core.video import vs as vsx
from videoforge.core.video.preview import Preview
from videoforge.plugins.loader import PluginHost, load_plugins
from videoforge.server.events import EventHub
from videoforge.server.queue import JobQueue, Services
from videoforge.server.routes import config, jobs, presets, queue, system, video
from videoforge.server.settings import SavedSettings, ServerSettings
from videoforge.server.store import Store

logger = logging.getLogger(__name__)


def create_app(
    settings: ServerSettings | None = None,
    app_config: AppConfig | None = None,
    *,
    profiles: Callable[[str], Profile] | None = None,
    profile_ids: list[str] | None = None,
    services: Services | None = None,
    setup_vapoursynth: bool = True,
) -> FastAPI:
    from videoforge.profiles import default_profile_id, get_profile, profile_ids as registered

    settings = settings or ServerSettings()
    base = app_config or load_app_config()  # videoforge.toml (+ .local); the Settings page layers over it
    ids = profile_ids or registered()
    services = services or Services()

    store = Store(settings.db_path)
    saved = SavedSettings.load(store)
    default = default_profile_id(saved.profile or base.profile, ids)
    cfg = saved.app_config(base, default)
    default_roots = list(settings.roots)
    if saved.roots:
        settings.roots = [Path(r) for r in saved.roots]
    events = EventHub()
    preview = Preview()  # VapourSynth for the preview, in a child process started on first use
    if services.detect_crop is None:
        services.detect_crop = partial(video.source_crop, preview)
    if services.release_preview is None:
        services.release_preview = preview.release
    queue_events = JsonLines(settings.data_dir / "logs" / QUEUE_EVENTS, max_bytes=QUEUE_EVENTS_MAX)
    bus = EventBus()  # what runs do, for notifications, actions and plugins
    job_queue = JobQueue(
        cfg,
        profiles or get_profile,
        store,
        events,
        services,
        settings.probe_workers,
        queue_events=queue_events,
        bus=bus,
        records_dir=settings.records_dir,
    )
    job_queue.index_waits_for_disk = saved.index_waits_for_disk
    notifier = Notifier(services.send_notification, list(saved.notifications))
    bus.subscribe(notifier.on_event, JobFinished, QueueFinished, name="notifications")
    actions = ActionRunner(
        list(saved.actions),
        allow_commands=base.allow_commands,
        job_log=job_queue.job_log,
        report=lambda kind, **fields: queue_events.write(event(kind, **fields)),
    )
    bus.subscribe(actions.on_event, JobFinished, QueueFinished, name="actions")
    plugin_report = load_plugins(settings.plugins_dir, saved.disabled_plugins)
    plugins = PluginHost(
        plugin_report, bus, data_dir=settings.plugin_data_dir, settings=base.plugins, job_log=job_queue.job_log
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        events.bind(asyncio.get_running_loop())
        if setup_vapoursynth:
            vsx.configure(cfg.tools.vs_plugins)
            await asyncio.to_thread(vsx.ensure_vspipe, cfg.tools.vspipe)
        job_queue.load()
        logger.info("Data folder %s, default profile %s", settings.data_dir, default)
        try:
            yield
        finally:
            logger.info("Shutting down")
            job_queue.shutdown()
            notifier.close()
            actions.close()
            plugins.close()
            preview.close()
            store.close()
            queue_events.close()

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
    app.state.notifier = notifier
    app.state.actions = actions
    app.state.plugins = plugins
    app.state.plugins_off_at_start = frozenset(saved.disabled_plugins)
    app.state.preview = preview
    app.state.profile_ids = ids
    app.state.default_profile = default
    for module in (jobs, queue, video, system, config, presets):
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
        # Asked for again each time (the assets it names are hashed), so a new build shows on the next load
        # instead of a cached page naming the last build's.
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
