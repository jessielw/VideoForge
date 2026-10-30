"""Queue control: queue jobs, start the worker, stop after the current job, cancel it, pause and resume it,
change its tools' priority; the index lane, and a job's test encode in it."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request

from videoforge.core.execute.control import Priority
from videoforge.core.pipeline.sample import DEFAULT_PERCENT
from videoforge.server.queue import JobQueue

router = APIRouter(prefix="/api/queue")


def queue_of(request: Request) -> JobQueue:
    return request.app.state.queue


@router.get("")
def state(request: Request) -> dict[str, Any]:
    return queue_of(request).queue_state()


@router.post("/reuse")
def reuse(request: Request, body: dict[str, Any] | None = Body(None)) -> dict[str, Any]:  # noqa: B008
    """What a start of the given jobs (as /start picks them) could reuse: the jobs with finished files, each
    with its offers (`id` "video" / "audio.N", label, file, size, seconds, finished, current, origin: the other
    job's folder a run links it from, or "")."""
    q = queue_of(request)
    jobs = []
    for e in q.start_targets((body or {}).get("ids")):
        if offers := q.reuse_offers(e):
            jobs.append(
                {
                    "id": e.id,
                    "name": e.spec.name,
                    "label": e.spec.label,
                    "offers": [
                        {
                            "id": o.id,
                            "label": o.label,
                            "file": str(o.file),
                            "size": o.size,
                            "seconds": o.seconds,
                            "finished": o.finished,
                            "current": o.current,
                            "origin": o.origin,
                        }
                        for o in offers
                    ],
                }
            )
    return {"jobs": jobs}


@router.post("/start")
def start(request: Request, body: dict[str, Any] | None = Body(None)) -> dict[str, Any]:  # noqa: B008
    """Queue the given jobs (none given: run the queued ones) and start the worker. `reuse`
    ({job id: [offer ids]}, the answer to /reuse) says which finished files each job keeps; the others
    it was offered are made again. A job left out of it reuses what matches its settings, as always."""
    q = queue_of(request)
    if reuse := (body or {}).get("reuse"):
        q.choose_reuse(reuse)
    if (ids := (body or {}).get("ids")) is not None:
        q.enqueue(ids)
    q.start()
    return q.queue_state()


@router.post("/enqueue")
def enqueue(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    """Queue the given jobs: the queue's state, plus the ids it queued (`enqueued`; `queued` is the count)."""
    q = queue_of(request)
    enqueued = q.enqueue(body.get("ids"))
    return {**q.queue_state(), "enqueued": enqueued}


@router.post("/dequeue")
def dequeue(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    q = queue_of(request)
    q.dequeue(body.get("ids") or [])
    return q.queue_state()


@router.post("/stop")
def stop(request: Request) -> dict[str, Any]:
    q = queue_of(request)
    q.stop_after_current()
    return q.queue_state()


@router.post("/cancel")
def cancel(request: Request) -> dict[str, Any]:
    q = queue_of(request)
    q.stop_after_current()
    q.cancel_current()
    return q.queue_state()


@router.post("/pause")
def pause(request: Request) -> dict[str, Any]:
    """Suspend the running job's tools and the index lane's."""
    q = queue_of(request)
    q.pause()
    return q.queue_state()


@router.post("/resume")
def resume(request: Request) -> dict[str, Any]:
    q = queue_of(request)
    q.resume()
    return q.queue_state()


@router.post("/priority")
def priority(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    """`priority` (a Priority, or null for the Settings') for the running job's and the index lane's tools, for
    the rest of their run."""
    value = body.get("priority")
    if value is not None and value not in tuple(Priority):
        raise HTTPException(422, f"priority: one of {', '.join(Priority)}, or null")
    q = queue_of(request)
    q.set_priority(None if value is None else Priority(value))
    return q.queue_state()


@router.post("/index")
def index(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    """Index the given jobs one at a time (work folder, script, source index; nothing else): the queue's
    state, plus the ids taken (`taken`; jobs that are queued, running or reuse an encode are left out).
    `first`: ahead of the jobs waiting (the job open in the editor)."""
    q = queue_of(request)
    taken = q.index(body.get("ids") or [], first=bool(body.get("first")))
    return {**q.queue_state(), "taken": taken}


@router.post("/index/stop")
def stop_index(request: Request, body: dict[str, Any] | None = Body(None)) -> dict[str, Any]:  # noqa: B008
    """Take the given jobs (default: all) out of the index lane, cancelling the one being indexed."""
    q = queue_of(request)
    q.stop_indexing((body or {}).get("ids"))
    return q.queue_state()


@router.post("/sample")
def sample(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    """A test encode of job `id`: `percent` (1, 2, 5 or 10) of its video, first in the index lane (Index stop
    cancels it). The queue's state, plus `taken` (false: the job reuses an encode, isn't probed yet, or is queued,
    running or being indexed)."""
    q = queue_of(request)
    try:
        taken = q.sample(str(body.get("id")), int(body.get("percent", DEFAULT_PERCENT)))
    except KeyError:
        raise HTTPException(404, f"No job {body.get('id')}") from None
    except (TypeError, ValueError) as ex:
        raise HTTPException(422, str(ex)) from None
    return {**q.queue_state(), "taken": taken}
