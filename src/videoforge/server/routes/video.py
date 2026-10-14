"""A job's video in the browser: clip info, frames (source = uncropped, output = processed),
auto-crop, the generated script, and a check that runs it (the script editor's Run).

Clips come from the same script generator the encode uses and are cached by
script text. The first request for a source builds its index in the job's work
folder (minutes for a large remux; later requests are instant).
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request, Response

from videoforge.core.job import JobSpec
from videoforge.core.plan_io import to_json
from videoforge.core.video import crop as autocrop
from videoforge.core.video import vs as vsx
from videoforge.core.video.script import build_script, script_parts
from videoforge.core.video.settings import Crop
from videoforge.server.queue import Entry, JobQueue

router = APIRouter(prefix="/api/jobs/{job_id}/video")
Stage = Literal["source", "output"]


def _entry(request: Request, job_id: str) -> Entry:
    q: JobQueue = request.app.state.queue
    try:
        return q.get(job_id)
    except KeyError:
        raise HTTPException(404, f"No job {job_id}") from None


def script_for(e: Entry, stage: Stage) -> str:
    return _script(e.spec, stage)


def _script(spec: JobSpec, stage: Stage) -> str:
    spec.work_dir.mkdir(parents=True, exist_ok=True)  # the index lives there
    return build_script(spec.video, spec.inputs.source, spec.work_dir, depth=spec.encoder.depth, stage=stage)


def source_crop(clips: vsx.ClipCache, spec: JobSpec, samples: int = 20) -> Crop:
    """Auto-crop's suggestion for a job's source (a template's auto crop; indexes the source first)."""
    return autocrop.detect(clips.get(_script(spec, "source")), samples=samples)


def _clip(request: Request, e: Entry, stage: Stage):
    cache: vsx.ClipCache = request.app.state.clips
    try:
        return cache.get(script_for(e, stage))
    except vsx.ScriptError as ex:
        raise HTTPException(422, str(ex)) from None


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
    e = _entry(request, job_id)
    cache: vsx.ClipCache = request.app.state.clips
    try:
        clip = cache.get(script_for(e, stage))
    except vsx.ScriptError as ex:
        message = ex.message
        spec = e.spec
        head, body, _ = script_parts(spec.video, spec.inputs.source, spec.work_dir, depth=spec.encoder.depth, stage=stage)
        if ex.line and ex.line > len(head) + len(body):
            message += " (in the generated end of the script: the body must leave a video clip in `clip`)"
        return {"ok": False, "error": message, "line": ex.line}
    try:
        clip.get_frame(0)
    except Exception as ex:  # noqa: BLE001 - a filter failing on a frame; report it, don't 500
        return {"ok": False, "error": f"Frame 0: {type(ex).__name__}: {ex}", "line": None}
    i = vsx.clip_info(clip)
    return {"ok": True, "info": to_json(i) | {"fps": i.fps}}


@router.get("/info")
def info(request: Request, job_id: str, stage: Stage = "output") -> dict[str, Any]:
    clip = _clip(request, _entry(request, job_id), stage)
    i = vsx.clip_info(clip)
    return to_json(i) | {"fps": i.fps}


@router.get("/frame")
def frame(request: Request, job_id: str, n: int = 0, stage: Stage = "output",
          fmt: Literal["jpeg", "png"] = "jpeg", quality: int = 90) -> Response:
    clip = _clip(request, _entry(request, job_id), stage)
    try:
        data = vsx.frame_image(clip, n, fmt, quality)
        props = vsx.frame_props(clip, n)
    except Exception as ex:  # noqa: BLE001 - a filter failing on this frame
        raise HTTPException(422, f"Frame {n}: {type(ex).__name__}: {ex}") from None
    pict = props.get("_PictType", "")
    return Response(data, media_type=f"image/{fmt}",
                    headers={"Cache-Control": "no-store", "X-Frame-Type": str(pict), "X-Frame-Count": str(clip.num_frames)})


@router.post("/autocrop")
def detect_crop(request: Request, job_id: str, samples: int = 20) -> dict[str, Any]:
    """Suggest a crop from the uncropped source (the job isn't changed)."""
    clip = _clip(request, _entry(request, job_id), "source")
    return to_json(autocrop.detect(clip, samples=max(3, min(samples, 60))))
