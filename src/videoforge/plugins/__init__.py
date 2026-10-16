"""The plugin API: what a VideoForge plugin imports. docs/plugins.md is the guide.

A plugin is a Python module exporting one `Plugin`: its name and the functions to call when things
happen. Each function gets the event (a snapshot: changing it changes nothing) and the plugin's
`PluginContext`:

    from videoforge.plugins import JobFinished, JobStatus, Plugin, PluginContext

    def finished(event: JobFinished, ctx: PluginContext) -> None:
        if event.status is JobStatus.DONE:
            ctx.job_log(event.spec.id, f"Sent {event.output} to the library")

    plugin = Plugin(name="Library", version="1.0", on_job_finished=finished)

It is found in a folder of its own under `<data dir>/plugins/` holding `videoforge-plugin.toml`
(`id`, `module`, and `object` when it isn't named `plugin`), or as an installed package's
`videoforge.plugins` entry point. A plugin's functions run on a thread of their own, one call at a
time, so a slow one holds up only itself; one that raises is logged, and the next event still comes.

Only what this module exports is the API (`API_VERSION` counts its breaking changes); the rest of
VideoForge may change under a plugin that reaches into it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import logging
from pathlib import Path
from typing import Any

from videoforge.core.events import IndexFinished, JobFinished, JobStarted, QueueFinished
from videoforge.core.job import JobResult, JobSpec, JobStatus

__all__ = [
    "API_VERSION",
    "IndexFinished",
    "JobFinished",
    "JobResult",
    "JobSpec",
    "JobStarted",
    "JobStatus",
    "Plugin",
    "PluginContext",
    "QueueFinished",
]

API_VERSION = 1


@dataclass(frozen=True, slots=True)
class PluginContext:
    """What VideoForge gives a plugin."""

    id: str
    data_dir: Path  # <data dir>/plugin-data/<id>: the plugin's own files (made when it loads)
    settings: Mapping[str, Any]  # videoforge.toml's [plugins.<id>] table ({} when there is none)
    log: logging.Logger  # the app log, under "videoforge.plugin.<id>"
    job_log: Callable[[str, str], None]  # (job id, line): a line in that job's log (shown in the browser)


Hook = Callable[[Any, PluginContext], object]


@dataclass(frozen=True, slots=True)
class Plugin:
    """The one object a plugin module exports."""

    name: str
    version: str = ""
    description: str = ""
    api_version: int = API_VERSION  # the API it was written for; a newer one than VideoForge's won't load
    setup: Callable[[PluginContext], object] | None = None  # once, before any event
    on_job_started: Callable[[JobStarted, PluginContext], object] | None = None
    on_job_finished: Callable[[JobFinished, PluginContext], object] | None = None
    on_queue_finished: Callable[[QueueFinished, PluginContext], object] | None = None
    on_index_finished: Callable[[IndexFinished, PluginContext], object] | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)  # free for the plugin's own use

    def hooks(self) -> dict[type, Hook]:
        """Event type -> the function for it, for the ones it has."""
        found = {
            JobStarted: self.on_job_started,
            JobFinished: self.on_job_finished,
            QueueFinished: self.on_queue_finished,
            IndexFinished: self.on_index_finished,
        }
        return {t: h for t, h in found.items() if h is not None}
