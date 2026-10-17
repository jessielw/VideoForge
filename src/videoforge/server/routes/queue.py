"""Queue control: queue jobs, start the worker, stop after the current job, cancel it; the index lane."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Request

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
    with its offers (`id` "video" / "audio.N", label, file, size, seconds, finished, current)."""
    q = queue_of(request)
    jobs = []
    for e in q.start_targets((body or {}).get("ids")):
        if offers := q.reuse_offers(e):
            jobs.append(
                {
                    "id": e.id,
                    "name": e.spec.name,
                    "offers": [
                        {
                            "id": o.id,
                            "label": o.label,
                            "file": str(o.file),
                            "size": o.size,
                            "seconds": o.seconds,
                            "finished": o.finished,
                            "current": o.current,
                        }
                        for o in offers
                    ],
                }
            )
    return {"jobs": jobs}


@router.post("/start")
def start(request: Request, body: dict[str, Any] | None = Body(None)) -> dict[str, Any]:  # noqa: B008
    """Queue the given jobs (or every runnable one when none are given) and start the worker. `reuse`
    ({job id: [offer ids]}, the answer to /reuse) says which finished files each job keeps; the others
    it was offered are made again. A job left out of it reuses what matches its settings, as always."""
    q = queue_of(request)
    if reuse := (body or {}).get("reuse"):
        q.choose_reuse(reuse)
    ids = (body or {}).get("ids")
    if ids or not any(e.queued for e in q.entries()):
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
