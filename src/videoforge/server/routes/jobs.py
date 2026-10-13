"""Jobs: match inputs, add, list, inspect, edit (one or many), remove, reorder, re-probe, logs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request

from videoforge.core.execute.process import ToolError
from videoforge.core.models import Overrides
from videoforge.core.pairing import match_files, slot_files
from videoforge.core.pipeline.build import build_steps, output_path
from videoforge.core.plan_io import from_json, to_json
from videoforge.core.video.settings import EncoderSettings, VideoSettings
from videoforge.server.queue import Busy, JobQueue
from videoforge.server.views import detail, summary

router = APIRouter(prefix="/api")


def queue_of(request: Request) -> JobQueue:
    return request.app.state.queue


def _entry(q: JobQueue, job_id: str):
    try:
        return q.get(job_id)
    except KeyError:
        raise HTTPException(404, f"No job {job_id}") from None


def _paths(body: dict[str, Any], key: str) -> list[Path]:
    return [Path(p) for p in body.get(key) or []]


def _match(request: Request, body: dict[str, Any]):
    q = queue_of(request)
    profile = q.profiles(body.get("profile") or request.app.state.default_profile)
    rules = q.app.matching
    sets = slot_files(_paths(body, "sources"), _paths(body, "encodes"),
                      _paths(body, "subtitles") if profile.external_subtitles else [], _paths(body, "chapters"), rules)
    return match_files(sets, rules)


@router.post("/match")
def match(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    """Preview what Add would create from the given files and folders."""
    result = _match(request, body)
    left = result.unmatched
    return {
        "jobs": [to_json(j) for j in result.jobs],
        "unmatched": [str(p) for p in left.encodes + left.subtitles + left.chapters],
    }


@router.post("/jobs")
def add_jobs(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    q = queue_of(request)
    result = _match(request, body)
    if not result.jobs:
        raise HTTPException(422, "No source matched")
    out_dir = Path(body["output_dir"]) if body.get("output_dir") else None
    if out_dir is not None:
        request.app.state.store.set_setting("output_dir", str(out_dir))
    added, skipped = q.add(
        result.jobs,
        body.get("profile") or request.app.state.default_profile,
        original_language=body.get("original_language") or None,
        output_dir=out_dir,
        video=from_json(VideoSettings, body["video"]) if body.get("video") else None,
        encoder=from_json(EncoderSettings, body["encoder"]) if body.get("encoder") else None,
    )
    left = result.unmatched
    return {"added": [e.id for e in added], "skipped": skipped,
            "unmatched": [str(p) for p in left.encodes + left.subtitles + left.chapters]}


@router.get("/jobs")
def list_jobs(request: Request) -> list[dict[str, Any]]:
    return [summary(e) for e in queue_of(request).entries()]


@router.get("/jobs/{job_id}")
def get_job(request: Request, job_id: str) -> dict[str, Any]:
    q = queue_of(request)
    return detail(_entry(q, job_id), q)


def _changes(body: dict[str, Any]) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    if "video" in body:
        changes["video"] = from_json(VideoSettings, body["video"])
    if "encoder" in body:
        changes["encoder"] = from_json(EncoderSettings, body["encoder"])
    if "overrides" in body:
        changes["overrides"] = from_json(Overrides, body["overrides"])
    if body.get("output_dir"):
        changes["output_dir"] = Path(body["output_dir"])
    if "qpf" in body:
        changes["qpf"] = bool(body["qpf"])
    if body.get("profile"):
        changes["profile"] = body["profile"]
    return changes


@router.patch("/jobs/{job_id}")
def update_job(request: Request, job_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    q = queue_of(request)
    _entry(q, job_id)
    try:
        e = q.update(job_id, **_changes(body))
    except Busy as ex:
        raise HTTPException(409, str(ex)) from None
    except (KeyError, ValueError, TypeError) as ex:
        raise HTTPException(422, f"{type(ex).__name__}: {ex}") from None
    return detail(e, q)


@router.post("/jobs/apply")
def apply_to_jobs(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    """The same settings on several jobs (a batch): {ids, video?, encoder?, output_dir?, qpf?}."""
    q = queue_of(request)
    body = {k: v for k, v in body.items() if k != "overrides"}  # track overrides are per job
    updated, skipped = [], []
    for job_id in body.get("ids") or []:
        try:
            q.update(job_id, **_changes(body))
            updated.append(job_id)
        except (Busy, KeyError):
            skipped.append(job_id)
    return {"updated": updated, "skipped": skipped}


@router.post("/jobs/remove")
def remove_jobs(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    return {"removed": queue_of(request).remove(body.get("ids") or [])}


@router.delete("/jobs/{job_id}")
def delete_job(request: Request, job_id: str) -> dict[str, Any]:
    q = queue_of(request)
    if not q.remove([job_id]):
        e = _entry(q, job_id)
        raise HTTPException(409, f"{e.spec.name} is queued or running")
    return {"removed": [job_id]}


@router.post("/jobs/reorder")
def reorder_jobs(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    q = queue_of(request)
    q.reorder(body.get("ids") or [])
    return {"ids": [e.id for e in q.entries()]}


@router.post("/jobs/reprobe")
def reprobe_jobs(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    q = queue_of(request)
    ids = body.get("ids") or [e.id for e in q.entries()]
    q.probe([i for i in ids if not q.get(i).running])
    return {"ids": ids}


@router.get("/jobs/{job_id}/commands")
def job_commands(request: Request, job_id: str) -> list[dict[str, Any]]:
    """The command line of every step the job would run (a preview; nothing is started)."""
    q = queue_of(request)
    e = _entry(q, job_id)
    if e.plan is None:
        raise HTTPException(409, "The job hasn't been probed yet")
    profile = q.profile(e)
    out_dir = e.spec.output_dir or Path("<output folder>")
    try:
        built = build_steps(e.spec, e.plan, profile, q.app, output_path(e.plan, out_dir, profile))
    except (ToolError, ValueError) as ex:
        raise HTTPException(422, str(ex)) from None
    return [{"id": s.id, "label": s.label, "command": s.command_line or "(runs in VideoForge)"} for s in built.steps]


@router.get("/jobs/{job_id}/log")
def job_log(request: Request, job_id: str, tail: int = 2000) -> dict[str, Any]:
    e = _entry(queue_of(request), job_id)
    return {"lines": list(e.log)[-tail:]}


@router.get("/jobs/{job_id}/steps")
def job_steps(request: Request, job_id: str) -> list[dict[str, Any]]:
    """The last run's steps: command line, status, exit code, time, error and output lines."""
    q = queue_of(request)
    return q.step_output(_entry(q, job_id))
