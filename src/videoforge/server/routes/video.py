"""A job's video in the browser: clip info, frames (source = uncropped, crop = the crop editor's view,
output = processed), auto-crop, the generated script, and a check that runs it (the script editor's Run).

To compare the encoder's input with its output, two pairs of stages give the same frames: `output` and `encode`
(the output file a done run wrote), and `sample-in` and `sample` (a test encode's script, as it ran, and its MKV;
core/pipeline/sample.py). The encodes open through FFMS2, their indexes in the job's folder.

Clips come from the same script generator the encode uses and are loaded and cached per job
and stage in the preview worker (core/video/preview.py, a child process). Only an indexed source is
opened (409 otherwise): indexing goes through the queue's index lane, one job at a time, so opening
a job never starts reading a whole remux.
"""

from __future__ import annotations

from contextlib import AbstractContextManager, nullcontext
from fractions import Fraction
from pathlib import Path
from typing import Any, Literal, cast

from fastapi import APIRouter, HTTPException, Request, Response

from videoforge.core.job import JobSpec
from videoforge.core.models import SubTrack
from videoforge.core.pipeline.build import auto_crop, baked_el, indexed
from videoforge.core.pipeline.sample import MKV, SCRIPT, read_result, sample_dir
from videoforge.core.plan_io import to_json
from videoforge.core.video.info import length_warning
from videoforge.core.video.preview import FrameError, Preview, PreviewError
from videoforge.core.video.script import build_script, encoded_script, script_parts
from videoforge.core.video.settings import Crop
from videoforge.core.video.vs import ClipInfo, ScriptError
from videoforge.server.queue import Entry, JobQueue
from videoforge.server.views import encode_compare

router = APIRouter(prefix="/api/jobs/{job_id}/video")
ScriptStage = Literal["source", "crop", "output"]  # the job's own script's
Stage = Literal[ScriptStage, "sample-in", "sample", "encode"]
_ENCODED = ("sample-in", "sample", "encode")  # the compare's stages (_slot)


def _entry(request: Request, job_id: str) -> Entry:
    q: JobQueue = request.app.state.queue
    try:
        return q.get(job_id)
    except KeyError:
        raise HTTPException(404, f"No job {job_id}") from None


def _loading(e: Entry, preview: Preview, script: str, slot: str) -> AbstractContextManager[object]:
    """For a clip the preview has to load: 409 while the source isn't indexed, else the job's source lock
    (the index lane may be checking the index: it reads the finished one after)."""
    if preview.has(script, slot):
        return nullcontext()
    _indexed(e)
    return e.source_lock


def _indexed(e: Entry) -> None:
    if e.indexing or not indexed(e.spec, e.source_video, e.burn):
        raise HTTPException(409, "The source isn't indexed yet: index it first (Video tab, or Index in the queue)")


def _info_json(e: Entry, i: ClipInfo, stage: Stage) -> dict[str, Any]:
    """The clip's info for the page; the output's carries length_warning when its length isn't the source's."""
    warning = length_warning(e.source_video, i.frames, Fraction(i.fps_num, i.fps_den) if i.fps_num else None)
    return to_json(i) | {"fps": i.fps, "length_warning": warning if stage == "output" else ""}


def script_for(e: Entry, stage: Stage) -> str:
    if stage == "encode":
        if (out := encode_compare(e)) is None:
            raise HTTPException(409, "The job has no finished output to compare with")
        return encoded_script(out, e.spec.job_dir)
    if stage in ("sample-in", "sample"):
        home = sample_dir(e.spec)
        if read_result(e.spec) is None:
            raise HTTPException(409, "The job has no test encode to compare with")
        try:
            return (
                (home / SCRIPT).read_text(encoding="utf-8")
                if stage == "sample-in"
                else encoded_script(home / MKV, home)
            )
        except OSError as ex:
            raise HTTPException(409, f"The test encode's script can't be read: {ex}") from None
    return _script(e.spec, cast(ScriptStage, stage), baked_el(e.spec, e.source_video), e.burn)


def _script(spec: JobSpec, stage: ScriptStage, el: Path | None = None, burn: SubTrack | None = None) -> str:
    """The job's script at stage; el is a FEL's enhancement layer it bakes in (stage "source" leaves it out:
    auto crop reads the base layer, the same size), burn a subtitle track it burns in (not at stage "source")."""
    spec.work_dir.mkdir(parents=True, exist_ok=True)  # the index lives there
    return build_script(
        spec.video, spec.inputs.source, spec.work_dir, depth=spec.encoder.depth, stage=stage, el=el, burn=burn
    )


def _slot(spec: JobSpec, stage: Stage) -> str:
    """The preview's clip slot. The compare's are `<id>:sample:...` and `<id>:encode:...`, so the queue can free
    them alone (Preview.release) before a run writes their files again."""
    if stage in _ENCODED:
        group, _, part = stage.partition("-")
        return f"{spec.id}:{group}:{part or 'out'}"
    return f"{spec.id}:{stage}"


def source_crop(preview: Preview, spec: JobSpec, samples: int = 20) -> Crop:
    """Auto-crop's suggestion for a job's source (a template's auto crop runs it on the index lane, after the index)."""
    return preview.autocrop(_script(spec, "source"), samples=samples, slot=_slot(spec, "source"))


def _preview(request: Request) -> Preview:
    return request.app.state.preview


def _failed(ex: Exception) -> HTTPException:
    """A script that fails (422, the editor shows it) or a preview that stopped (503)."""
    return HTTPException(503 if isinstance(ex, PreviewError) else 422, str(ex))


@router.get("/script")
def script(request: Request, job_id: str, stage: ScriptStage = "output") -> dict[str, Any]:
    """The script, and its parts: head and tail are generated, body is what the user edits
    (the custom body, or the lines crop/resize/filters make). Line numbers count from the head."""
    e = _entry(request, job_id)
    spec = e.spec
    head, body, tail = script_parts(
        spec.video,
        spec.inputs.source,
        spec.work_dir,
        depth=spec.encoder.depth,
        stage=stage,
        el=baked_el(spec, e.source_video),
        burn=e.burn,
    )
    return {
        "script": "\n".join(head + body + tail) + "\n",
        "head": head,
        "body": body,
        "tail": tail,
        "custom": spec.video.custom is not None,
    }


@router.get("/check")
def check(request: Request, job_id: str, stage: ScriptStage = "output") -> dict[str, Any]:
    """Run the script and render its first frame: the clip's info, or the error and its script line."""
    e = _entry(request, job_id)
    preview, script, slot = _preview(request), script_for(e, stage), _slot(e.spec, stage)
    try:
        with _loading(e, preview, script, slot):
            i = preview.check(script, slot=slot)
    except ScriptError as ex:
        message = ex.message
        spec = e.spec
        head, body, _ = script_parts(
            spec.video,
            spec.inputs.source,
            spec.work_dir,
            depth=spec.encoder.depth,
            stage=stage,
            el=baked_el(spec, e.source_video),
            burn=e.burn,
        )
        if ex.line and ex.line > len(head) + len(body):
            message += " (in the generated end of the script: the body must leave a video clip in `clip`)"
        return {"ok": False, "error": message, "line": ex.line}
    except (FrameError, PreviewError) as ex:  # a filter failing on frame 0, or the preview stopped
        return {"ok": False, "error": str(ex), "line": None}
    return {"ok": True, "info": _info_json(e, i, stage)}


@router.get("/info")
def info(request: Request, job_id: str, stage: Stage = "output") -> dict[str, Any]:
    try:
        e = _entry(request, job_id)
        preview, script, slot = _preview(request), script_for(e, stage), _slot(e.spec, stage)
        with _loading(e, preview, script, slot):
            i = preview.info(script, slot=slot)
    except (ScriptError, FrameError, PreviewError) as ex:
        raise _failed(ex) from None
    return _info_json(e, i, stage)


@router.get("/frame")
def frame(
    request: Request,
    job_id: str,
    n: int = 0,
    stage: Stage = "output",
    fmt: Literal["jpeg", "png"] = "jpeg",
    quality: int = 90,
) -> Response:
    try:
        e = _entry(request, job_id)
        preview, script, slot = _preview(request), script_for(e, stage), _slot(e.spec, stage)
        with _loading(e, preview, script, slot):
            data, pict, frames, crop_view = preview.frame(script, n, fmt, quality, slot=slot)
    except (ScriptError, FrameError, PreviewError) as ex:
        raise _failed(ex) from None
    return Response(
        data,
        media_type=f"image/{fmt}",
        headers={
            "Cache-Control": "no-store",
            "X-Frame-Type": pict,
            "X-Frame-Count": str(frames),
            "X-Crop-View": "1" if crop_view else "0",
        },
    )


@router.post("/autocrop")
def detect_crop(request: Request, job_id: str, samples: int = 20) -> dict[str, Any]:
    """Suggest a crop from the uncropped source (the job isn't changed): a Dolby Vision source's from its RPU's L5
    (checked against the detected borders), else the detected borders. origin says which."""
    try:
        e = _entry(request, job_id)
        _indexed(e)
        with e.source_lock:
            detected = source_crop(_preview(request), e.spec, max(3, min(samples, 60)))
    except (ScriptError, FrameError, PreviewError) as ex:
        raise _failed(ex) from None
    q: JobQueue = request.app.state.queue
    crop, origin = auto_crop(e.spec, e.source_video, q.app.tools.dovi_tool, detected)
    return to_json(crop) | {"origin": origin}
