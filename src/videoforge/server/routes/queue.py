"""Queue control: queue jobs, start the worker, stop after the current job, cancel it."""

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
    q = queue_of(request)
    return {"queued": q.enqueue(body.get("ids")), **q.queue_state()}


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
