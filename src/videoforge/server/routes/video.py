"""A job's video in the browser: clip info, frames (source = uncropped, output = processed),
auto-crop, the generated script, and a check that runs it (the script editor's Run).

Clips come from the same script generator the encode uses and are loaded and cached per job
and stage in the preview worker (core/video/preview.py, a child process). The first request for a
source builds its index in the job's work folder (minutes for a large remux; later requests are instant).
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request, Response

from videoforge.core.job import JobSpec
from videoforge.core.plan_io import to_json
from videoforge.core.video.preview import FrameError, Preview, PreviewError
from videoforge.core.video.script import build_script, script_parts
from videoforge.core.video.settings import Crop
from videoforge.core.video.vs import ScriptError
from videoforge.server.queue import Entry, JobQueue

router = APIRouter(prefix="/api/jobs/{job_id}/video")
Stage = Literal["source", "output"]


def _entry(request: Request, job_id: str) -> Entry:
    q: JobQueue = request.app.state.queue
    try:
        return q.get(job_id)
    except KeyError:
        raise HTTPException(404, f"No job {job_id}") from None


def _clip_entry(request: Request, job_id: str) -> Entry:
    """The job, once the index lane is done with it: two processes never build one index at once,
    and the preview reads the finished index (as long as the index takes; the editor shows its spinner)."""
    e = _entry(request, job_id)
    e.index_idle.wait()
    return e


def script_for(e: Entry, stage: Stage) -> str:
    return _script(e.spec, stage)


def _script(spec: JobSpec, stage: Stage) -> str:
    spec.work_dir.mkdir(parents=True, exist_ok=True)  # the index lives there
    return build_script(spec.video, spec.inputs.source, spec.work_dir, depth=spec.encoder.depth, stage=stage)


def _slot(spec: JobSpec, stage: Stage) -> str:
    return f"{spec.id}:{stage}"


def source_crop(preview: Preview, spec: JobSpec, samples: int = 20) -> Crop:
    """Auto-crop's suggestion for a job's source (a template's auto crop; indexes the source first)."""
    return preview.autocrop(_script(spec, "source"), samples=samples, slot=_slot(spec, "source"))


def _preview(request: Request) -> Preview:
    return request.app.state.preview


def _failed(ex: Exception) -> HTTPException:
    """A script that fails (422, the editor shows it) or a preview that stopped (503)."""
    return HTTPException(503 if isinstance(ex, PreviewError) else 422, str(ex))


@router.get("/script")
def script(request: Request, job_id: str, stage: Stage = "output") -> dict[str, Any]:
    """The script, and its parts: head and tail are generated, body is what the user edits
    (the custom body, or the lines crop/resize/filters make). Line numbers count from the head."""
    spec = _entry(request, job_id).spec
    head, body, tail = script_parts(spec.video, spec.inputs.source, spec.work_dir, depth=spec.encoder.depth, stage=stage)
    return {"script": "\n".join(head + body + tail) + "\n", "head": head, "body": body, "tail": tail,
            "custom": spec.video.custom is not None}


@router.get("/check")
def check(request: Request, job_id: str, stage: Stage = "output") -> dict[str, Any]:
    """Run the script and render its first frame: the clip's info, or the error and its script line."""
    e = _clip_entry(request, job_id)
    try:
        i = _preview(request).check(script_for(e, stage), slot=_slot(e.spec, stage))
    except ScriptError as ex:
        message = ex.message
        spec = e.spec
        head, body, _ = script_parts(spec.video, spec.inputs.source, spec.work_dir, depth=spec.encoder.depth, stage=stage)
        if ex.line and ex.line > len(head) + len(body):
            message += " (in the generated end of the script: the body must leave a video clip in `clip`)"
        return {"ok": False, "error": message, "line": ex.line}
    except (FrameError, PreviewError) as ex:  # a filter failing on frame 0, or the preview stopped
        return {"ok": False, "error": str(ex), "line": None}
    return {"ok": True, "info": to_json(i) | {"fps": i.fps}}


@router.get("/info")
def info(request: Request, job_id: str, stage: Stage = "output") -> dict[str, Any]:
    try:
        e = _clip_entry(request, job_id)
        i = _preview(request).info(script_for(e, stage), slot=_slot(e.spec, stage))
    except (ScriptError, FrameError, PreviewError) as ex:
        raise _failed(ex) from None
    return to_json(i) | {"fps": i.fps}


@router.get("/frame")
def frame(request: Request, job_id: str, n: int = 0, stage: Stage = "output",
          fmt: Literal["jpeg", "png"] = "jpeg", quality: int = 90) -> Response:
    try:
        e = _clip_entry(request, job_id)
        data, pict, frames = _preview(request).frame(script_for(e, stage), n, fmt, quality, slot=_slot(e.spec, stage))
    except (ScriptError, FrameError, PreviewError) as ex:
        raise _failed(ex) from None
    return Response(data, media_type=f"image/{fmt}",
                    headers={"Cache-Control": "no-store", "X-Frame-Type": pict, "X-Frame-Count": str(frames)})


@router.post("/autocrop")
def detect_crop(request: Request, job_id: str, samples: int = 20) -> dict[str, Any]:
    """Suggest a crop from the uncropped source (the job isn't changed)."""
    try:
        crop = source_crop(_preview(request), _clip_entry(request, job_id).spec, max(3, min(samples, 60)))
    except (ScriptError, FrameError, PreviewError) as ex:
        raise _failed(ex) from None
    return to_json(crop)
