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


@router.post("/start")
def start(request: Request, body: dict[str, Any] | None = Body(None)) -> dict[str, Any]:  # noqa: B008
    """Queue the given jobs (or every runnable one when none are given) and start the worker."""
    q = queue_of(request)
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
