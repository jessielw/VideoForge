"""JSON shapes the API returns for jobs (the queue row, and the full job for the editor)."""

from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from videoforge.core.job import JobStatus, track_defaults
from videoforge.core.models import AudioTrack, Issue, Severity, SubTrack, track_key, with_copies
from videoforge.core.pipeline.build import indexed, output_path
from videoforge.core.pipeline.sample import MKV, read_result, sample_dir, sample_key
from videoforge.core.plan_io import to_json
from videoforge.core.video import info, target
from videoforge.core.video.color import color_args
from videoforge.core.video.settings import EncoderSettings, RateControl
from videoforge.server.queue import Entry, JobQueue


def encoder_label(enc: EncoderSettings) -> str:
    if enc.rate_control is RateControl.CRF:
        rc = f"crf {enc.crf:g}"
    elif target.applies(enc):
        rc = f"2-pass {enc.target_mb} MB"
    else:
        rc = f"{'2-pass ' if enc.passes == 2 else ''}{enc.bitrate_kbps} kb/s"
    return f"{enc.encoder.label} {rc}" + (f" {enc.depth}-bit" if enc.depth != 8 else "")


def encode_compare(e: Entry) -> Path | None:
    """The output a done run wrote, for the Video tab to compare with the script's frames; None without one."""
    out = e.state.output
    if not e.spec.encodes_video or e.state.status is not JobStatus.DONE or out is None:
        return None
    return out if out.is_file() else None


def issues(e: Entry) -> list[Issue]:
    out: list[Issue] = []
    if e.probe_error:
        out.append(Issue(Severity.BLOCK, "probe", e.probe_error))
    if e.state.error:
        out.append(
            Issue(Severity.BLOCK, f"run.{e.state.status.value if e.state.status else 'interrupted'}", e.state.error)
        )
    out += [Issue(i.severity, "output." + i.code, i.message) for i in e.state.issues]
    if e.plan is not None:
        out += e.plan.issues
    order = {Severity.BLOCK: 0, Severity.WARN: 1, Severity.INFO: 2}
    return sorted(out, key=lambda i: order[i.severity])


def summary(e: Entry) -> dict[str, Any]:
    first = next((i for i in issues(e) if i.severity is not Severity.INFO), None)
    s = e.spec
    return {
        "id": e.id,
        "name": s.name,
        "label": s.label,  # tells jobs on one source apart
        "source": str(s.inputs.source),
        "profile": s.profile,
        "status": e.status.value,
        "progress": e.progress,
        "issue": first.message if first else "",
        "output": str(e.state.output) if e.state.output else None,
        "encoder": encoder_label(s.encoder) if s.encodes_video else "reuses encode",
        # A custom script body ignores the crop fields; a reused encode has no script at all.
        "crop": to_json(s.video.crop) if s.encodes_video and s.video.custom is None else None,
        "custom_script": s.encodes_video and s.video.custom is not None,
        # The source index is in the work folder (the video opens at once); a failed batch index says why.
        "indexed": s.encodes_video and not e.indexing and indexed(s, e.source_video, e.burn),
        "index_error": e.index_error,
        "index_held": e.index_held,  # waiting in the lane while an encode reads its disk
        "sample_waiting": e.sample_percent is not None and not e.sampling,  # in the lane for a test encode
        "sample_error": e.sample_error,
        "audio": [f"{a.title} ({a.language})" for a in e.plan.audio] if e.plan else [],
        "subs": len(e.plan.subs) if e.plan else 0,
    }


def detail(e: Entry, queue: JobQueue) -> dict[str, Any]:
    profile = queue.profile(e)
    out = summary(e)
    out["spec"] = to_json(e.spec)
    out["issues"] = [to_json(i) for i in issues(e)]
    out["steps"] = to_json(e.state.steps)
    out["plan"] = None
    out["output_name"] = None
    out["tracks"] = None
    out["color_args"] = None  # the source's colour flags for this encoder (added unless source_color is off)
    out["target"] = None  # where a 2-pass target size goes, and the bitrate it leaves the video
    out["sample"] = None  # the last test encode (core/pipeline/sample.py)
    # What the Video tab can compare the script's frames with: the encoded output (a done run's) or the sample.
    out["compare"] = {"encode": encode_compare(e) is not None, "sample": False}
    if e.plan is not None:
        plan = to_json(e.plan)
        for key in ("source", "inputs", "overrides"):  # sent elsewhere
            plan.pop(key, None)
        out["plan"] = plan
        out["output_name"] = output_path(e.spec, e.plan, profile, Path()).name
        enc = e.spec.encoder
        if e.spec.encodes_video and target.applies(enc) and enc.target_mb is not None:
            found = target.budget(
                enc.target_mb, e.plan, e.spec.container(profile), info.read(e.spec.job_dir / info.SCRIPT_INFO)
            )
            out["target"] = to_json(found) | {"video": found.video, "kbps": found.kbps} if found else None
        if e.spec.encodes_video and (result := read_result(e.spec)) is not None:
            out["sample"] = asdict(result) | {
                "kbps": result.kbps,
                "estimate_mb": result.estimate_mb,
                "estimate_seconds": result.estimate_seconds,
                "encode_fps": result.encode_fps,
                "current": result.key == sample_key(e.spec, e.plan),
                "file": str(sample_dir(e.spec) / MKV),
            }
            out["compare"]["sample"] = True
    if e.probed is not None:
        src = e.probed.source
        tracks = [*src.audio, *e.probed.external_audio, *src.subs, *e.probed.external_subs]
        audio = [*src.audio, *(e.probed.external_audio if profile.external_audio else [])]
        # The track editor shows each track as the profile has it with no hand edit (auto), and saves
        # only what differs from that.
        auto: dict[str, dict[str, Any]] | None = None
        if profile.track_editor:
            audio = with_copies(audio, e.spec.overrides.copies)
            if e.plan is not None:
                auto = track_defaults(e.spec, e.probed, profile)

        def track(t: AudioTrack | SubTrack) -> dict[str, Any]:
            key = track_key(t)
            row = to_json(t) | {"key": key, "detected": profile.detected_flags(t)}
            return row if auto is None else row | {"auto": auto.get(key, {"kept": False})}

        out["tracks"] = {
            "video": to_json(src.video) if src.video else None,
            "audio": [track(t) for t in audio],
            "subs": [track(t) for t in [*src.subs, *e.probed.external_subs]],
            "has_chapters": src.has_chapters,
            "count": len(tracks),
        }
        if src.video is not None:
            out["color_args"] = color_args(src.video.color, replace(e.spec.encoder, source_color=True))
    return out
