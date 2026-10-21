"""Jobs: match inputs, add, list, inspect, edit (one or many), remove, reorder, re-probe, logs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request

from videoforge.core.execute.mux import MuxSettings
from videoforge.core.execute.process import ToolError
from videoforge.core.job import OutputPolicy
from videoforge.core.models import JobInputs, Overrides
from videoforge.core.pairing import AUDIO_EXTENSIONS, SUB_FORMATS, match_files, slot_files
from videoforge.core.pipeline.build import build_steps, output_path
from videoforge.core.plan_io import from_json, to_json
from videoforge.core.template import Template
from videoforge.core.video.settings import Crop, EncoderSettings, VideoSettings
from videoforge.core.workdir import work_dir_size
from videoforge.server.queue import LOG_LINES, Busy, JobQueue
from videoforge.server.routes.presets import default_template
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
    sets = slot_files(
        _paths(body, "sources"),
        _paths(body, "encodes"),
        _paths(body, "subtitles") if profile.external_subtitles else [],
        _paths(body, "chapters"),
        rules,
    )
    return match_files(sets, rules)


@router.post("/match")
def match(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    """Preview what Add would create from the given files and folders."""
    result = _match(request, body)
    left = result.unmatched
    q = queue_of(request)
    return {
        "jobs": [
            to_json(j)
            | {
                "existing_id": existing.id if (existing := q._find_source(j.source)) else None,
                "existing_status": existing.status if existing else None,
            }
            for j in result.jobs
        ],
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
        template=_template(body) or _default_template(request, body),
        replace_existing=body.get("replace_existing") or [],
    )
    left = result.unmatched
    return {
        "added": [e.id for e in added],
        "skipped": skipped,
        "unmatched": [str(p) for p in left.encodes + left.subtitles + left.chapters],
    }


@router.get("/jobs")
def list_jobs(request: Request) -> list[dict[str, Any]]:
    return [summary(e) for e in queue_of(request).entries()]


@router.post("/jobs/apply-crop")
def apply_crop(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    return queue_of(request).apply_crop(body.get("ids") or [], from_json(Crop, body.get("crop") or {}))


@router.get("/jobs/{job_id}")
def get_job(request: Request, job_id: str) -> dict[str, Any]:
    q = queue_of(request)
    return detail(_entry(q, job_id), q)


def _template(body: dict[str, Any]) -> Template | None:
    """A template's settings, sent whole (the UI has the user's and each profile's defaults)."""
    return from_json(Template, body["template"]) if body.get("template") else None


def _default_template(request: Request, body: dict[str, Any]) -> Template | None:
    """Jobs added with no settings of their own get the profile's default template, if it has one."""
    if body.get("video") or body.get("encoder") or "template" in body:
        return None
    return default_template(request.app.state.store, body.get("profile") or request.app.state.default_profile)


def _changes(body: dict[str, Any]) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    if "output_policy" in body:
        changes["output_policy"] = OutputPolicy(body["output_policy"])
    if body.get("template"):
        changes["template"] = _template(body)
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
    if "mux" in body:
        changes["mux"] = from_json(MuxSettings, body["mux"])
    if body.get("container") is not None:
        changes["container"] = str(body["container"])
    if body.get("profile"):
        changes["profile"] = body["profile"]
    if body.get("label") is not None:
        changes["label"] = str(body["label"])
    if body.get("output_name") is not None:
        changes["output_name"] = str(body["output_name"])
    return changes


def _files(paths: list[str], suffixes: set[str]) -> list[Path]:
    """Files as given, a folder as its files with these suffixes (by name); each must exist."""
    out: list[Path] = []
    for p in map(Path, paths):
        if p.is_dir():
            out += sorted(
                (f for f in p.iterdir() if f.is_file() and f.suffix.lower() in suffixes), key=lambda f: f.name.lower()
            )
        elif p.is_file():
            out.append(p)
        else:
            raise HTTPException(422, f"No file {p}")
    return list(dict.fromkeys(out))


def _inputs(current: JobInputs, body: dict[str, Any]) -> JobInputs:
    """The job's inputs with any of subtitles (the whole list), chapters, encode (a path or null) replaced."""

    def one(key: str, old: Path | None) -> Path | None:
        if key not in body:
            return old
        if not body[key]:
            return None
        path = Path(body[key])
        if not path.is_file():
            raise HTTPException(422, f"No file {path}")
        return path

    subs = _files(body["subtitles"], set(SUB_FORMATS)) if "subtitles" in body else current.subtitles
    audio = _files(body["audio"], set(AUDIO_EXTENSIONS)) if "audio" in body else current.audio
    return JobInputs(
        current.source,
        encode=one("encode", current.encode),
        subtitles=subs,
        chapters=one("chapters", current.chapters),
        encode_state=current.encode_state,
        audio=audio,
    )


@router.patch("/jobs/{job_id}")
def update_job(request: Request, job_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    """Change a job: any of template, video, encoder, overrides, output_dir, output_name, label, qpf, profile, mux,
    container, and inputs
    ({subtitles?, audio?: [paths or folders], chapters?: path | null, encode?: path | null})."""
    q = queue_of(request)
    e = _entry(q, job_id)
    try:
        changes = _changes(body)
        if body.get("inputs") is not None:
            changes["inputs"] = _inputs(e.spec.inputs, body["inputs"])
        e = q.update(job_id, **changes)
    except Busy as ex:
        raise HTTPException(409, str(ex)) from None
    except (KeyError, ValueError, TypeError) as ex:
        raise HTTPException(422, f"{type(ex).__name__}: {ex}") from None
    return detail(e, q)


@router.post("/jobs/apply")
def apply_to_jobs(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    """The same settings on several jobs (a batch): {ids, template?, video?, encoder?, output_dir?, qpf?, mux?,
    container?}. A template's auto crop is detected per job afterwards."""
    q = queue_of(request)
    body = {k: v for k, v in body.items() if k not in ("overrides", "output_name")}  # these are per job
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
    """{ids, work_dirs}: remove jobs (queued, running or indexing ones stay); with work_dirs, also delete
    their work folders (queue.delete_work_dirs). Returns {removed, deleted, kept}."""
    q = queue_of(request)
    sources = {e.id: e.spec.inputs.source for e in q.entries()}
    removed = q.remove(body.get("ids") or [])
    deleted, kept = q.delete_work_dirs(sources[i] for i in removed) if body.get("work_dirs") else ([], {})
    return {"removed": removed, "deleted": deleted, "kept": kept}


@router.post("/jobs/removal-preview")
def removal_preview(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    q = queue_of(request)
    folders = []
    for job_id in dict.fromkeys(body.get("ids") or []):
        e = _entry(q, job_id)
        error = "Job is queued, running or indexing" if e.busy or e.indexing else ""
        size = None
        try:
            size = work_dir_size(e.spec.inputs.source)
        except OSError as ex:
            error = str(ex)
        folders.append({"id": e.id, "path": str(e.spec.work_dir), "bytes": size, "error": error})
    return {"folders": folders}


@router.post("/jobs/restore")
def restore_jobs(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    return {"restored": queue_of(request).restore(body.get("ids") or [])}


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
        built = build_steps(
            e.spec,
            e.plan,
            profile,
            q.app,
            output_path(e.spec, e.plan, profile, out_dir),
        )
    except (ToolError, ValueError) as ex:
        raise HTTPException(422, str(ex)) from None
    return [{"id": s.id, "label": s.label, "command": s.command_line or "(runs in VideoForge)"} for s in built.steps]


@router.get("/jobs/{job_id}/log")
def job_log(request: Request, job_id: str, tail: int = LOG_LINES) -> dict[str, Any]:
    e = _entry(queue_of(request), job_id)
    return {"lines": list(e.log)[-tail:]}


@router.get("/jobs/{job_id}/steps")
def job_steps(request: Request, job_id: str) -> list[dict[str, Any]]:
    """The last run's steps: command line, status, exit code, time, error and output lines."""
    q = queue_of(request)
    return q.step_output(_entry(q, job_id))


@router.get("/jobs/{job_id}/log-snapshot")
def log_snapshot(request: Request, job_id: str) -> dict[str, Any]:
    q = queue_of(request)
    return q.log_snapshot(_entry(q, job_id))
