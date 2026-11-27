"""JSON shapes the API returns for jobs (the queue row, and the full job for the editor)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from videoforge.core import naming
from videoforge.core.job import JobStatus, track_defaults
from videoforge.core.models import AudioTrack, Issue, Severity, SubTrack, track_key, with_copies
from videoforge.core.pipeline import crfsearch
from videoforge.core.pipeline.build import indexed, output_path
from videoforge.core.pipeline.sample import MKV, read_result, sample_dir, sample_key
from videoforge.core.plan_io import to_json
from videoforge.core.video import hdr, info, target
from videoforge.core.video.color import color_args
from videoforge.core.video.script import compares_filters
from videoforge.core.video.settings import EncoderSettings, RateControl
from videoforge.server.queue import Entry, JobQueue


def encoder_label(enc: EncoderSettings) -> str:
    if enc.rate_control is RateControl.CRF:
        rc = f"CRF {enc.crf:g}"
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


def made(e: Entry) -> dict[str, Any] | None:
    """What the last run that wrote the output made, for a done job's summary: its size against the
    source's, the run's time and the output's overall bitrate; None until a run wrote it."""
    m = e.state.made
    if m is None or e.state.status not in (JobStatus.DONE, JobStatus.INVALID):
        return None
    video = e.plan.source.video if e.plan else None
    ms = 0.0
    if video is not None:
        ms = video.duration_ms or (video.frames * (video.default_duration_ns or 0) / 1e6)
    return to_json(m) | {"kbps": round(m.output_bytes * 8 / ms) if ms else None}


# Where each issue is fixed, for the Issues tab's link: a job tab, or "tools" (Settings › Tools). The first entry a
# code is or starts with wins; a code none matches gets no link (the source's probe, an output check, a plugin's own).
ISSUE_TABS: tuple[tuple[str, str], ...] = (
    ("tools.dee_split", "audio"),
    ("tools.missing", "tools"),
    ("hdr.dv_second_track", "tools"),
    ("hdr.dv_el", "tools"),
    ("hdr.svt_build", "tools"),
    ("hdr.dv_bake_bs", "video"),
    ("hdr.dv_custom", "video"),
    ("video.interlaced", "video"),
    ("video.pulldown", "video"),
    ("video.", "encoder"),
    ("hdr.", "encoder"),
    ("audio.", "audio"),
    ("subs.", "subs"),
    ("mux.", "output"),
    ("name.", "output"),
    ("outfile.", "output"),
    ("run.", "log"),
)


def issue_tab(code: str) -> str | None:
    return next((tab for prefix, tab in ISSUE_TABS if code == prefix or code.startswith(prefix)), None)


def issues(e: Entry) -> list[Issue]:
    out: list[Issue] = []
    if e.probe_error:
        out.append(Issue(Severity.BLOCK, "probe", e.probe_error))
    checks = [Issue(i.severity, "output." + i.code, i.message) for i in e.state.issues]
    run = None
    if e.state.error:
        run = Issue(Severity.BLOCK, f"run.{e.state.status.value if e.state.status else 'interrupted'}", e.state.error)
    if e.state.status is JobStatus.INVALID:
        # The failed checks first (the queue row shows the first), then where the file went. A job that ran before
        # the summary has the checks joined as its error: nothing more than the checks.
        if run is not None and run.message == "; ".join(i.message for i in checks if i.severity is Severity.BLOCK):
            run = None
        out += checks + ([run] if run else [])
    else:
        out += ([run] if run else []) + checks
    if e.plan is not None:
        out += e.plan.issues
    order = {Severity.BLOCK: 0, Severity.WARN: 1, Severity.INFO: 2}
    return sorted(out, key=lambda i: order[i.severity])


def summary(e: Entry, groups: Mapping[str, str] | None = None) -> dict[str, Any]:
    """groups: queue group names by id (JobQueue.group_names)."""
    found = [i for i in issues(e) if i.severity is not Severity.INFO]
    first = found[0] if found else None
    s = e.spec
    return {
        "id": e.id,
        "name": s.name,
        "label": s.label,  # tells jobs on one source apart
        "group": e.group or None,  # the queue group it's shown in
        "group_name": (groups or {}).get(e.group, "") if e.group else "",
        "source": str(s.inputs.source),
        "rule_set": s.rule_set,
        "status": e.status.value,
        "pause_after_pass1": e.state.pause_after_pass1,
        "two_pass": s.encodes_video and s.encoder.passes == 2,
        "progress": e.progress,
        "issue": first.message if first else "",
        # the queue row's counts: errors and warnings (the job's Issues tab lists them)
        "issue_counts": {
            "block": sum(i.severity is Severity.BLOCK for i in found),
            "warn": sum(i.severity is Severity.WARN for i in found),
        },
        "output": str(e.state.output) if e.state.output else None,
        "encoder": encoder_label(s.encoder) if s.encodes_video else "reuses encode",
        # A custom script body ignores the crop fields; a reused encode has no script at all.
        "crop": to_json(s.video.crop) if s.encodes_video and s.video.custom is None else None,
        "custom_script": s.encodes_video and s.video.custom is not None,
        # The source index is in the work folder (the video opens at once); a failed batch index says why.
        "indexed": s.encodes_video and not e.indexing and indexed(s, e.source_video, e.burn),
        "index_error": e.index_error,
        "index_wait_reason": e.index_wait_reason if e.index_held else "",
        "index_held": e.index_held,  # waiting in the lane while an encode reads its disk
        "sample_waiting": e.sample_percent is not None and not e.sampling,  # in the lane for a test encode
        "sample_error": e.sample_error,
        "searching": e.search is not None,  # the lane's test encode is a CRF search
        "search_error": e.search_error,
        "audio": [f"{a.title} ({a.language})" for a in e.plan.audio] if e.plan else [],
        "subs": len(e.plan.subs) if e.plan else 0,
        "source_facts": source_facts(e),
    }


def source_facts(e: Entry) -> dict[str, Any] | None:
    """What the source is, at a glance (the queue row): its size class, length, HDR formats, and interlacing."""
    v = e.source_video
    if v is None:
        return None
    return {
        "resolution": e.plan.resolution if e.plan else f"{v.width}x{v.height}",
        "duration_ms": v.duration_ms or None,
        "hdr": hdr.formats(v),
        "interlaced": v.interlaced,
    }


def detail(e: Entry, queue: JobQueue) -> dict[str, Any]:
    rule_set = queue.rule_set(e)
    out = summary(e, queue.group_names())
    out["spec"] = to_json(e.spec)
    out["issues"] = [to_json(i) | {"tab": issue_tab(i.code)} for i in issues(e)]
    out["steps"] = to_json(e.state.steps)
    out["made"] = made(e)  # the last run that wrote the output: sizes, time, bitrate
    out["plan"] = None
    out["output_name"] = None
    out["output_title"] = None  # the MKV segment title the name template gives it, when it gives one
    out["tracks"] = None
    out["color_args"] = None  # the source's colour flags for this encoder (added unless source_color is off)
    out["target"] = None  # where a 2-pass target size goes, and the bitrate it leaves the video
    out["sample"] = None  # the last test encode (core/pipeline/sample.py)
    out["search"] = None  # the last CRF search, or the one running (core/pipeline/crfsearch.py)
    # What the Video tab can compare the script's frames with: the encoded output (a done run's), the sample, or
    # the script without its filters.
    out["compare"] = {
        "encode": encode_compare(e) is not None,
        "sample": False,
        "filters": compares_filters(e.spec.video),
    }
    if e.plan is not None:
        plan = to_json(e.plan)
        for key in ("source", "inputs", "overrides"):  # sent elsewhere
            plan.pop(key, None)
        out["plan"] = plan
        out["output_name"] = output_path(e.spec, e.plan, rule_set, Path()).name
        out["output_title"] = naming.title(e.spec, e.plan) or None
        enc = e.spec.encoder
        if e.spec.encodes_video and target.applies(enc) and enc.target_mb is not None:
            found = target.budget(
                enc.target_mb, e.plan, e.spec.container(rule_set), info.read(e.spec.job_dir / info.SCRIPT_INFO)
            )
            out["target"] = to_json(found) | {"video": found.video, "kbps": found.kbps} if found else None
        app = queue.app
        if e.spec.encodes_video and (result := read_result(e.spec)) is not None:
            out["sample"] = asdict(result) | {
                "kbps": result.kbps,
                "estimate_mb": result.estimate_mb,
                "estimate_seconds": result.estimate_seconds,
                "encode_fps": result.encode_fps,
                "current": result.key == sample_key(e.spec, e.plan, app),
                "file": str(sample_dir(e.spec) / MKV),
            }
            out["compare"]["sample"] = True
        if e.spec.encodes_video and (found := crfsearch.read_result(e.spec)) is not None:
            out["search"] = found.to_json() | {"current": found.key == crfsearch.search_key(e.spec, e.plan, app)}
    if e.probed is not None:
        src = e.probed.source
        tracks = [*src.audio, *e.probed.external_audio, *src.subs, *e.probed.external_subs]
        audio = [*src.audio, *(e.probed.external_audio if rule_set.external_audio else [])]
        # The track editor shows each track as the rule set has it with no hand edit (auto), and saves
        # only what differs from that.
        auto: dict[str, dict[str, Any]] | None = None
        if rule_set.track_editor:
            audio = with_copies(audio, e.spec.overrides.copies)
            if e.plan is not None:
                auto = track_defaults(e.spec, e.probed, rule_set)

        def track(t: AudioTrack | SubTrack) -> dict[str, Any]:
            key = track_key(t)
            detected = rule_set.detected(t, e.plan.original_language if e.plan else None)
            row = to_json(t) | {"key": key, "detected": detected}
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
