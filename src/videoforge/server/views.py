"""JSON shapes the API returns for jobs (the queue row, and the full job for the editor)."""

from __future__ import annotations

from typing import Any

from videoforge.core.models import Issue, Severity, track_key, with_copies
from videoforge.core.plan_io import to_json
from videoforge.core.video.script import index_exists
from videoforge.core.video.settings import EncoderSettings, RateControl
from videoforge.server.queue import Entry, JobQueue


def encoder_label(enc: EncoderSettings) -> str:
    if enc.rate_control is RateControl.CRF:
        rc = f"crf {enc.crf:g}"
    else:
        rc = f"{'2-pass ' if enc.passes == 2 else ''}{enc.bitrate_kbps} kb/s"
    return f"{enc.encoder.value} {rc}" + (f" {enc.depth}-bit" if enc.depth != 8 else "")


def issues(e: Entry) -> list[Issue]:
    out: list[Issue] = []
    if e.probe_error:
        out.append(Issue(Severity.BLOCK, "probe", e.probe_error))
    if e.state.error:
        out.append(Issue(Severity.BLOCK, f"run.{e.state.status.value if e.state.status else 'interrupted'}",
                         e.state.error))
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
        "indexed": s.encodes_video and not e.indexing and index_exists(s.inputs.source, s.video.source_filter, s.work_dir),
        "index_error": e.index_error,
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
    out["tracks"] = None
    if e.plan is not None:
        plan = to_json(e.plan)
        for key in ("source", "inputs", "overrides"):  # sent elsewhere
            plan.pop(key, None)
        out["plan"] = plan
    if e.probed is not None:
        src = e.probed.source
        tracks = [*src.audio, *e.probed.external_audio, *src.subs, *e.probed.external_subs]
        audio = [*src.audio, *(e.probed.external_audio if profile.external_audio else [])]
        if profile.track_editor:
            audio = with_copies(audio, e.spec.overrides.copies)
        out["tracks"] = {
            "video": to_json(src.video) if src.video else None,
            "audio": [to_json(t) | {"key": track_key(t), "detected": profile.detected_flags(t)} for t in audio],
            "subs": [to_json(t) | {"key": track_key(t), "detected": profile.detected_flags(t)}
                     for t in [*src.subs, *e.probed.external_subs]],
            "has_chapters": src.has_chapters,
            "count": len(tracks),
        }
    return out
