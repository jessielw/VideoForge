"""What a job's run did, for other tools (NFO generators, uploaders): an event stream and a record.

Both go in the job's work folder (`<source>_tmp/`), named after the output file, so runs of one
source that make different outputs (another label or container) keep their own:

- `<output name>.videoforge.jsonl`: one JSON object per line, appended and flushed as things
  happen (run started, each step started and finished, run finished); every run appends. Tail it to
  follow a run live.
- `<output name>.videoforge.json`: the record, written (atomically) when a run makes the output:
  where everything came from and went, how the video was made, each output track with the source
  track it came from, the steps, the issues. A later run to the same output replaces it, so it
  describes the file that is there. "Completed" is this file with `run.status` "done".

The same events also go to one queue-wide stream in the data folder (`logs/events.jsonl`), so a tool
can watch VideoForge as a whole. The format is documented in docs/job-record.md; `v` is its version.
Writing these never fails a job: a file that can't be written is logged and left out.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import threading
import time
from typing import TYPE_CHECKING, Any
import uuid

from videoforge import version
from videoforge.core.execute.audio import ENCODES
from videoforge.core.execute.mux import MUXERS
from videoforge.core.job import JobResult, JobSpec, JobState, StepRun, StepStatus, planned_encode
from videoforge.core.models import AudioAction, Issue, Plan
from videoforge.core.pairing import episode_token
from videoforge.core.plan_io import to_json
from videoforge.core.video.qpf import qpf_paths
from videoforge.core.video.settings import Encoder

if TYPE_CHECKING:
    from videoforge.core.profile import Profile

logger = logging.getLogger(__name__)

SCHEMA = 1
RECORD_SUFFIX = ".videoforge.json"
EVENTS_SUFFIX = ".videoforge.jsonl"
QUEUE_EVENTS = "events.jsonl"  # in <data dir>/logs/
QUEUE_EVENTS_MAX = 10 * 1024 * 1024  # then it rolls over to events.jsonl.1 (3 kept)

VersionsFn = Callable[[Sequence[str]], dict[str, str]]  # Tools field names -> version line


def now() -> str:
    """Local time with its UTC offset, to the millisecond."""
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def record_path(work_dir: Path, output: Path) -> Path:
    return work_dir / (output.name + RECORD_SUFFIX)


def events_path(work_dir: Path, output: Path) -> Path:
    return work_dir / (output.name + EVENTS_SUFFIX)


def read_record(path: Path) -> dict[str, Any] | None:
    """A record, or None (missing, unreadable, or another schema version)."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) and doc.get("v") == SCHEMA else None


class JsonLines:
    """Appends JSON objects to a file, one per line, flushed at once; thread-safe. A file that can't be
    written is given up on (logged once). `max_bytes` rolls the file over to `<name>.1`, `.2`, ..."""

    def __init__(self, path: Path, *, max_bytes: int = 0, backups: int = 3) -> None:
        self.path, self.max_bytes, self.backups = path, max_bytes, backups
        self._lock = threading.Lock()
        self._file = None
        self._broken = False

    def write(self, doc: dict[str, Any]) -> None:
        line = json.dumps(doc, ensure_ascii=False, default=str) + "\n"
        with self._lock:
            if self._broken:
                return
            try:
                if self._file is None:
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    self._file = open(self.path, "a", encoding="utf-8")  # kept open: one line at a time
                if self.max_bytes and self._file.tell() + len(line) > self.max_bytes and self._file.tell():
                    self._roll()
                self._file.write(line)
                self._file.flush()
            except OSError as ex:
                self._broken = True
                logger.warning("Can't write %s (%s); its events are left out", self.path, ex)

    def _roll(self) -> None:
        if self._file is not None:
            self._file.close()
        for n in range(self.backups - 1, 0, -1):
            older = self.path.with_name(f"{self.path.name}.{n}")
            if older.exists():
                os.replace(older, self.path.with_name(f"{self.path.name}.{n + 1}"))
        os.replace(self.path, self.path.with_name(f"{self.path.name}.1"))
        self._file = open(self.path, "a", encoding="utf-8")

    def close(self) -> None:
        with self._lock:
            if self._file is not None:
                try:
                    self._file.close()
                except OSError:
                    pass
                self._file = None


def event(kind: str, **fields: Any) -> dict[str, Any]:
    return {"v": SCHEMA, "time": now(), "event": kind, **fields}


def write_json(path: Path, doc: dict[str, Any]) -> None:
    """Atomically: a reader never sees half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".partial")
    tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    os.replace(tmp, path)


# --- the record ---------------------------------------------------------------------


def _file(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    out: dict[str, Any] = {"path": str(path), "name": path.name, "size": None, "modified": None}
    try:
        st = path.stat()
        out["size"] = st.st_size
        out["modified"] = datetime.fromtimestamp(st.st_mtime).astimezone().isoformat(timespec="seconds")
    except OSError:
        pass
    return out


def _flags(t: Any) -> dict[str, bool]:
    keys = ("default", "forced", "hearing_impaired", "commentary", "original", "visual_impaired")
    return {k: bool(getattr(t, k)) for k in keys}


def _issue(stage: str, i: Issue) -> dict[str, str]:
    return {"stage": stage, "severity": i.severity.value, "code": i.code, "message": i.message}


def _commands(state: JobState) -> dict[str, str]:
    return {r.id: r.command for r in state.run}


def _video(spec: JobSpec, plan: Plan, commands: dict[str, str]) -> dict[str, Any]:
    if not spec.encodes_video:
        return {"encoded": False, "encode": str(spec.inputs.encode), "language": _video_language(plan)}
    script = spec.work_dir / "video.vpy"
    try:
        text = script.read_text(encoding="utf-8")
    except OSError:
        text = None
    planned = planned_encode(spec, plan.source).video
    v, enc = spec.video, spec.encoder
    return {
        "encoded": True,
        "encode": str(spec.video_output),
        "width": planned.width if planned else None,
        "height": planned.height if planned else None,
        "language": _video_language(plan),
        "script": {"path": str(script), "text": text},
        "source_filter": v.source_filter.value,
        "crop": to_json(v.crop),
        "resize": to_json(v.resize) if v.resize else None,
        "filters": v.filters,
        "custom_script": v.custom is not None,
        "encoder": {
            "name": enc.encoder.value,
            "rate_control": enc.rate_control.value,
            "crf": enc.crf,
            "bitrate_kbps": enc.bitrate_kbps,
            "preset": enc.preset,
            "tune": enc.tune,
            "depth": enc.depth,
            "options": dict(enc.options),
            "extra": enc.extra,
        },
        "commands": [c for sid, c in commands.items() if sid == "video" or sid.startswith("video.")],
    }


def _video_language(plan: Plan) -> str:
    return plan.source.video.language if plan.source.video else "und"


def _source_ref(track: Any, source: Path | None) -> dict[str, Any]:
    external = track.external_path
    return {
        "kind": "file" if external is not None else "source",
        "path": str(external or source),
        "id": track.id,  # mkvmerge's track id in that file (container-wide, 0-based)
        "index": track.index,  # among that file's tracks of this kind (0-based)
    }


def _audio(plan: Plan, result: JobResult, commands: dict[str, str]) -> list[dict[str, Any]]:
    out = []
    for pos, a in enumerate(plan.audio):
        src = a.source
        ref = _source_ref(src, plan.source.path) | {
            "copy": src.copy,  # 1, 2, ...: another output made from the same track
            "codec": src.codec.value,
            "layout": str(src.layout),
            "atmos": src.atmos,
            "language": src.language,
            "title": src.title,
        }
        copied = a.action is AudioAction.COPY
        enc = None if copied else ENCODES[a.action]
        encoded = result.encoded_audio.get(pos)
        out.append(
            {
                "index": pos,
                "track": 1 + pos,
                "source": ref,
                "action": a.action.value,
                "encoder": None if enc is None else {"label": enc.label, "tools": list(enc.tools)},
                "command": commands.get(f"audio.{pos + 1}") or None,
                "file": str(encoded) if encoded else None,
                "codec": a.out_codec.value,
                "layout": str(a.out_layout),
                "channels": a.out_layout.channels,
                "atmos": a.out_atmos,
                "bitrate_kbps": a.bitrate_kbps,
                "delay_ms": src.delay_ms,
                "language": a.language,
                "title": a.title,
                **_flags(a),
            }
        )
    return out


def _subs(plan: Plan, container: str) -> list[dict[str, Any]]:
    muxer = MUXERS[container]
    first = 1 + len(plan.audio)
    out = []
    for pos, s in enumerate(plan.subs):
        src = s.source
        ref = _source_ref(src, plan.source.path) | {
            "format": src.format.value,
            "language": src.language,
            "title": src.title,
        }
        out.append(
            {
                "index": pos,
                "track": first + pos,
                "source": ref,
                "format": muxer.written_format(src.format).value,  # as the output holds it (MP4: SRT -> tx3g)
                "language": s.language,
                "title": s.title,
                **_flags(s),
            }
        )
    return out


def _chapters(spec: JobSpec, plan: Plan) -> dict[str, Any]:
    if spec.makes_chapters:
        files = qpf_paths(spec.work_dir)
        return {"from": "autoqpf", "path": str(files.chapters), "qpfile": str(files.qpfile)}
    if plan.chapters_path is not None:
        return {"from": "file", "path": str(plan.chapters_path)}
    if plan.source.has_chapters:
        return {"from": "source", "path": None}
    return {"from": None, "path": None}


def _step(r: StepRun) -> dict[str, Any]:
    return {
        "id": r.id,
        "label": r.label,
        "status": r.status.value,
        "seconds": r.seconds,
        "exit_code": r.exit_code,
        "command": r.command or None,
        "error": r.error or None,
    }


def used_tools(spec: JobSpec, plan: Plan, container: str) -> list[str]:
    """The Tools fields a run uses (whose versions the record states)."""
    names: list[str] = []
    if spec.encodes_video:
        names += ["vspipe", "x265" if spec.encoder.encoder is Encoder.X265 else "x264"]
    for a in plan.audio:
        if a.action is not AudioAction.COPY:
            names += ENCODES[a.action].tools
    names.append(MUXERS[container].tool)
    return list(dict.fromkeys(names))


def build_record(
    spec: JobSpec,
    plan: Plan,
    profile: Profile,
    result: JobResult,
    state: JobState,
    *,
    run_id: str,
    started: str,
    finished: str,
    seconds: float,
    output: Path,
    versions: dict[str, str] | None = None,
) -> dict[str, Any]:
    container = spec.container(profile)
    commands = _commands(state)
    work = spec.work_dir
    return {
        "v": SCHEMA,
        "videoforge": version(),
        "run": {
            "id": run_id,
            "status": result.status.value,
            "started": started,
            "finished": finished,
            "seconds": round(seconds, 1),
            "error": result.error or None,
        },
        "job": {
            "id": spec.id,
            "name": spec.name,
            "label": spec.label,
            "profile": spec.profile,
            "episode": episode_token(spec.inputs.source.stem),
        },
        "source": _file(spec.inputs.source),
        "output": (_file(output) or {}) | {"container": container},
        "work_dir": str(work),
        "log": str(work / "videoforge.log"),
        "events": str(events_path(work, output)),
        "video": _video(spec, plan, commands),
        "audio": _audio(plan, result, commands),
        "subtitles": _subs(plan, container),
        "chapters": _chapters(spec, plan),
        "original_language": plan.original_language,
        "steps": [_step(r) for r in state.run],
        "issues": [_issue("plan", i) for i in plan.issues] + [_issue("output", i) for i in result.issues],
        "tools": dict(versions or {}),
    }


# --- one run ------------------------------------------------------------------------


class RunRecorder:
    """One run of a job: its events (the job's stream and the queue-wide one) and, when the run made
    its output, the record. Every method swallows its own failures: recording never fails a job."""

    def __init__(
        self,
        spec: JobSpec,
        plan: Plan,
        profile: Profile,
        output: Path | None,
        *,
        queue_events: JsonLines | None = None,
        versions: VersionsFn | None = None,
    ) -> None:
        self.spec, self.plan, self.profile, self.output = spec, plan, profile, output
        self.run_id = uuid.uuid4().hex[:12]
        self.versions = versions
        self.started = now()
        self._t0 = time.monotonic()
        self._job = JsonLines(events_path(spec.work_dir, output)) if output is not None else None
        self._queue = queue_events
        self.record_file: Path | None = None

    def emit(self, kind: str, **fields: Any) -> None:
        doc = event(kind, job=self.spec.id, run=self.run_id, **fields)
        for sink in (self._job, self._queue):
            if sink is not None:
                sink.write(doc)

    def started_run(self) -> None:
        self.emit(
            "run.started",
            name=self.spec.name,
            label=self.spec.label,
            profile=self.spec.profile,
            source=str(self.spec.inputs.source),
            output=str(self.output) if self.output else None,
            container=self.spec.container(self.profile),
            work_dir=str(self.spec.work_dir),
            issues=[_issue("plan", i) for i in self.plan.issues],
        )

    def step(self, run: StepRun, index: int, total: int) -> None:
        """on_step: a step started or ended (pending steps are left out)."""
        if run.status is StepStatus.PENDING:
            return
        if run.status is StepStatus.RUNNING:
            self.emit(
                "step.started", step=run.id, label=run.label, n=index + 1, total=total, command=run.command or None
            )
        else:
            self.emit("step.finished", **_step(run) | {"step": run.id, "n": index + 1, "total": total})

    def finished(self, result: JobResult, state: JobState) -> Path | None:
        """The record (when the run wrote the output), then run.finished. Returns the record's path."""
        seconds = time.monotonic() - self._t0
        finished = now()
        if result.output is not None:
            try:
                container = self.spec.container(self.profile)
                versions = self.versions(used_tools(self.spec, self.plan, container)) if self.versions else {}
                doc = build_record(
                    self.spec,
                    self.plan,
                    self.profile,
                    result,
                    state,
                    run_id=self.run_id,
                    started=self.started,
                    finished=finished,
                    seconds=seconds,
                    output=result.output,
                    versions=versions,
                )
                path = record_path(self.spec.work_dir, result.output)
                write_json(path, doc)
                self.record_file = path
            except Exception:  # a bug here must not fail the job
                logger.exception("%s: the job record could not be written", self.spec.name)
        self.emit(
            "run.finished",
            status=result.status.value,
            output=str(result.output) if result.output else None,
            error=result.error or None,
            seconds=round(seconds, 1),
            record=str(self.record_file) if self.record_file else None,
            issues=[_issue("output", i) for i in result.issues],
        )
        if self._job is not None:
            self._job.close()
        return self.record_file
