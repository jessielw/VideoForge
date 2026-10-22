"""Example plugin: ask Jellyfin to scan its libraries when a job's output is done.

Configure it in Settings -> Plugins, or in videoforge.toml (or videoforge.local.toml):

    [plugins.library_scan]
    url = "http://localhost:8096"
    api_key = "..."            # Jellyfin: Dashboard > API Keys
    when = "queue"             # "job": after each job; "queue": once, when the queue finishes (default)
"""

from __future__ import annotations

import niquests

from videoforge.plugins import JobFinished, JobStatus, Plugin, PluginContext, QueueFinished


def setup(ctx: PluginContext) -> None:
    if not ctx.settings.get("url") or not ctx.settings.get("api_key"):
        ctx.log.warning("Configure url and api_key in Settings -> Plugins, or [plugins.%s] in videoforge.toml", ctx.id)


def scan(ctx: PluginContext) -> str | None:
    """None when Jellyfin took the request, else why not."""
    url, key = ctx.settings.get("url"), ctx.settings.get("api_key")
    if not url or not key:
        return "not set up"
    try:
        r = niquests.post(f"{url.rstrip('/')}/Library/Refresh", headers={"X-Emby-Token": key}, timeout=30)
    except Exception as ex:
        return str(ex)
    return None if r.ok else f"HTTP {r.status_code}"


def job_finished(event: JobFinished, ctx: PluginContext) -> None:
    if ctx.settings.get("when", "queue") != "job" or event.status is not JobStatus.DONE:
        return
    error = scan(ctx)
    ctx.job_log(event.spec.id, "Jellyfin: scanning" if error is None else f"Jellyfin: no scan ({error})")


def queue_finished(event: QueueFinished, ctx: PluginContext) -> None:
    if ctx.settings.get("when", "queue") != "queue" or JobStatus.DONE not in event.statuses:
        return
    error = scan(ctx)
    if error:
        ctx.log.warning("Jellyfin: no scan (%s)", error)
    else:
        ctx.log.info("Jellyfin: scanning")


plugin = Plugin(
    name="Library scan",
    version="1.0",
    description="Asks Jellyfin to scan its libraries after jobs are done.",
    setup=setup,
    on_job_finished=job_finished,
    on_queue_finished=queue_finished,
)
