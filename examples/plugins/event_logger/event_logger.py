"""Minimal plugin: observe each slot without changing job processing."""

from videoforge.plugins import IndexFinished, JobFinished, JobStarted, Plugin, PluginContext, QueueFinished


def started(event: JobStarted, ctx: PluginContext) -> None:
    ctx.job_log(event.spec.id, f"{ctx.settings['prefix']}: started {event.spec.name}")


def finished(event: JobFinished, ctx: PluginContext) -> None:
    ctx.job_log(event.spec.id, f"{ctx.settings['prefix']}: finished with {event.status.value}")


def indexed(event: IndexFinished, ctx: PluginContext) -> None:
    ctx.job_log(event.spec.id, f"{ctx.settings['prefix']}: index {event.error or 'finished'}")


def queue_finished(event: QueueFinished, ctx: PluginContext) -> None:
    ctx.log.info("%s: queue finished (%d jobs, %d left)", ctx.settings["prefix"], len(event.statuses), event.left)


plugin = Plugin(
    name="Event logger",
    version="1.0",
    on_job_started=started,
    on_job_finished=finished,
    on_index_finished=indexed,
    on_queue_finished=queue_finished,
)
