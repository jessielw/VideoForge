"""Queue control: queue jobs, start the worker, stop after the current job, cancel it, pause and resume it,
change its tools' priority; the index lane, and a job's test encode in it."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request

from videoforge.core.execute.control import Priority
from videoforge.core.pipeline import crfsearch
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
    job's folder a run links it from, or ""). A job whose question was answered when it was queued is left out."""
    q = queue_of(request)
    jobs = []
    for e in q.start_targets((body or {}).get("ids")):
        if q.reuse_answered(e):
            continue
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
    """Queue the given jobs: the queue's state, plus the ids it queued (`enqueued`; `queued` is the count).
    `reuse` is the answer to /reuse, as for /start: a running queue can take the job as soon as it's queued."""
    q = queue_of(request)
    if reuse := body.get("reuse"):
        q.choose_reuse(reuse)
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


@router.post("/pause-after-pass1")
def pause_after_pass1(request: Request, body: dict[str, Any] | None = Body(None)) -> dict[str, Any]:  # noqa: B008
    """Stop the given jobs (default: the running one) once their video's pass 1 is done, or (`on` false) take
    that back. The job ends `paused`: close the app, and Run it later to go on with pass 2. Jobs that don't
    encode in 2 passes are left out; the ids set are `set`."""
    q = queue_of(request)
    body = body or {}
    done = q.pause_after_pass1(body.get("ids"), bool(body.get("on", True)))
    return {**q.queue_state(), "set": done}


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


@router.post("/search")
def search(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    """A CRF search of job `id` (core/pipeline/crfsearch.py): its test encode at `percent` (1, 2, 5 or 10) at
    several CRFs, for the highest whose `metric` (ssimulacra2, ssimulacra2_p5 or xpsnr) reaches `target`, first in
    the index lane (Index stop cancels it). The queue's state, plus `taken` as for /sample; 422 for a job that
    doesn't encode at a CRF."""
    q = queue_of(request)
    try:
        goal = crfsearch.Target(crfsearch.Metric(str(body.get("metric"))), float(body.get("target", "")))
        taken = q.sample(str(body.get("id")), int(body.get("percent", DEFAULT_PERCENT)), goal)
    except KeyError:
        raise HTTPException(404, f"No job {body.get('id')}") from None
    except (TypeError, ValueError) as ex:
        raise HTTPException(422, str(ex)) from None
    return {**q.queue_state(), "taken": taken}
