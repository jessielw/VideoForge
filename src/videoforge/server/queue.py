"""The job queue: jobs in memory (spec, state, cached probe and plan), persisted in the
store, probed in a small thread pool, and run one at a time by a worker thread.

Every change is saved and announced on the event hub. An edit replans from the
cached probe (no file access) and clears the last run's outcome, but keeps the
finished steps, so a rerun only redoes what the edit touched.
"""

from __future__ import annotations

import sqlite3
import threading
from collections import deque
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from videoforge.core.config import AppConfig
from videoforge.core.execute.mux import MuxSettings
from videoforge.core.execute.process import CancelToken
from videoforge.core.job import (
    STEP_TAIL,
    JobResult,
    JobSpec,
    JobState,
    JobStatus,
    StepRecord,
    StepRun,
    StepStatus,
    plan_spec,
    probe_spec,
)
from videoforge.core.jobs import ProbedInputs, external_tracks
from videoforge.core.models import JobInputs, Overrides, Plan, Severity
from videoforge.core.pipeline.run import run_job
from videoforge.core.pipeline.steps import StepProgress
from videoforge.core.plan_io import to_json
from videoforge.core.profile import Profile
from videoforge.core.template import Template, apply_audio
from videoforge.core.video.settings import Crop, EncoderSettings, VideoSettings
from videoforge.server.events import EventHub
from videoforge.server.store import Store

LOG_LINES = 5000
STEP_LINES = 3000  # per step, in memory
_PROGRESS_INTERVAL = 0.25  # seconds between progress events per job


class JobView(StrEnum):
    """What the queue shows for a job."""

    PROBING = "probing"
    ERROR = "error"  # the probe failed
    CROPPING = "cropping"  # detecting the crop (a template's auto crop)
    READY = "ready"
    WARN = "warn"
    BLOCKED = "blocked"
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    INVALID = "invalid"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class Busy(RuntimeError):
    """The job is queued or running, so it can't be edited or removed."""


@dataclass(eq=False)
class Entry:
    spec: JobSpec
    state: JobState
    probed: ProbedInputs | None = None
    plan: Plan | None = None
    probe_error: str = ""
    probing: bool = False
    cropping: bool = False
    queued: bool = False
    running: bool = False
    progress: dict[str, Any] | None = None
    log: deque[str] = field(default_factory=lambda: deque(maxlen=LOG_LINES))
    # The last run's output per step (in memory; state.run keeps only each step's tail).
    step_lines: dict[str, deque[str]] = field(default_factory=dict)
    current_step: str | None = None

    @property
    def id(self) -> str:
        return self.spec.id

    @property
    def busy(self) -> bool:
        return self.queued or self.running

    @property
    def runnable(self) -> bool:
        return self.plan is not None and not self.plan.blocked and not self.busy and not self.cropping

    @property
    def status(self) -> JobView:
        if self.running:
            return JobView.RUNNING
        if self.queued:
            return JobView.QUEUED
        if self.state.status is not None:
            return JobView(self.state.status.value)
        if self.probe_error:
            return JobView.ERROR
        if self.cropping:
            return JobView.CROPPING
        if self.plan is None:
            return JobView.PROBING
        if self.plan.blocked:
            return JobView.BLOCKED
        if any(i.severity is Severity.WARN for i in self.plan.issues):
            return JobView.WARN
        return JobView.READY


@dataclass
class Services:
    """The slow core calls the queue makes; tests swap in fakes."""

    probe: Callable[[JobSpec, AppConfig], ProbedInputs] = probe_spec
    run: Callable[..., JobResult] = run_job
    record: Callable[[JobResult], object] | None = None  # JobHistory.record
    detect_crop: Callable[[JobSpec], Crop] | None = None  # reads the source (VapourSynth)


class JobQueue:
    def __init__(
        self,
        app: AppConfig,
        profiles: Callable[[str], Profile],
        store: Store,
        events: EventHub,
        services: Services | None = None,
        probe_workers: int = 2,
    ) -> None:
        self.app, self.profiles, self.store, self.events = app, profiles, store, events
        self.services = services or Services()
        self._entries: dict[str, Entry] = {}
        self._order: list[str] = []
        self._lock = threading.RLock()
        self._probes = ThreadPoolExecutor(max_workers=probe_workers, thread_name_prefix="probe")
        self._worker: threading.Thread | None = None
        self._active = False  # a worker owns the queue; cleared (under the lock) when it decides to stop
        self._cancel: CancelToken | None = None
        self._stop_after_current = False
        self._closing = False  # shutdown() began: a job starting now is cancelled at once

    # --- state ---------------------------------------------------------------------

    def entries(self) -> list[Entry]:
        with self._lock:
            return [self._entries[i] for i in self._order]

    def get(self, job_id: str) -> Entry:
        with self._lock:
            return self._entries[job_id]

    @property
    def running(self) -> bool:
        return self._active

    def queue_state(self) -> dict[str, Any]:
        current = next((e.id for e in self.entries() if e.running), None)
        return {"running": self.running, "current": current, "stop_after_current": self._stop_after_current,
                "queued": sum(e.queued for e in self.entries())}

    def _save(self, e: Entry) -> None:
        try:
            self.store.save_job(e.spec, e.state, queued=e.queued, running=e.running)
        except sqlite3.ProgrammingError:
            # The store closed after a shutdown that stopped waiting for this job: the store keeps it as
            # running, so the next start queues it again, as after a crash.
            if not self._closing:
                raise

    def _changed(self, e: Entry) -> None:
        self.events.publish("job", id=e.id, status=e.status.value)

    def _queue_changed(self) -> None:
        self.events.publish("queue", **self.queue_state())

    def profile(self, e: Entry) -> Profile:
        return self.profiles(e.spec.profile)

    # --- loading and adding ----------------------------------------------------------

    def load(self) -> None:
        """Jobs from the store; a job the server stopped in the middle of is queued again."""
        for stored in self.store.load_jobs():
            e = Entry(stored.spec, stored.state, queued=stored.queued or stored.running)
            if stored.running:
                e.state.status = None
                e.state.error = "Interrupted: the server stopped during this job; it resumes after its last finished step"
            with self._lock:
                self._entries[e.id] = e
                self._order.append(e.id)
            self._save(e)
        self.probe([e.id for e in self.entries()])

    def add(
        self,
        found: Iterable[JobInputs],
        profile_id: str,
        *,
        original_language: str | None = None,
        output_dir: Path | None = None,
        video: VideoSettings | None = None,
        encoder: EncoderSettings | None = None,
        template: Template | None = None,
    ) -> tuple[list[Entry], list[str]]:
        """One job per matched source, starting from the profile's video defaults, or the template,
        then the given settings. A source already in the queue is set up again unless it is queued or running.
        Returns (new jobs, names skipped because they are busy)."""
        profile = self.profiles(profile_id)
        added, skipped = [], []
        for inputs in found:
            existing = self._find_source(inputs.source)
            if existing is not None:
                if existing.busy:
                    skipped.append(existing.spec.name)
                    continue
                self.remove([existing.id])
            v, enc = profile.video_defaults()
            spec = JobSpec(
                inputs=inputs,
                profile=profile_id,
                overrides=Overrides(original_language=original_language),
                video=v,
                encoder=enc,
                output_dir=output_dir,
            )
            if template is not None:
                template.apply(spec)
            if video:
                spec.video = _copy(video)
            if encoder:
                spec.encoder = _copy(encoder)
            e = Entry(spec, JobState())
            with self._lock:
                self._entries[e.id] = e
                self._order.append(e.id)
            self._save(e)
            added.append(e)
            self.events.publish("job.added", id=e.id)
        self.probe([e.id for e in added])
        return added, skipped

    def _find_source(self, source: Path) -> Entry | None:
        key = str(source.resolve()).lower()
        return next((e for e in self.entries() if str(e.spec.inputs.source.resolve()).lower() == key), None)

    # --- probing and planning --------------------------------------------------------

    def probe(self, ids: Iterable[str]) -> None:
        for job_id in ids:
            e = self.get(job_id)
            if e.running:
                continue
            e.probing, e.probe_error, e.probed, e.plan = True, "", None, None
            self._changed(e)
            self._probes.submit(self._probe, e)

    def _probe(self, e: Entry) -> None:
        crop = False
        try:
            probed = self.services.probe(e.spec, self.app)
        except Exception as ex:  # noqa: BLE001 - shown on the job
            with self._lock:
                e.probing, e.probe_error = False, f"{type(ex).__name__}: {ex}"
            self._log(e, f"Probe failed: {e.probe_error}")
        else:
            with self._lock:
                e.probing, e.probed = False, probed
                if self._apply_audio(e):
                    self._save(e)
                self._replan(e)
                crop = self._claim_crop(e)
        self._changed(e)
        if crop:
            self._probes.submit(self._detect_crop, e)

    def _apply_audio(self, e: Entry) -> bool:
        """Under the lock: a template's pending audio becomes the job's overrides once its tracks are known."""
        s = e.spec
        if s.audio_template is None or e.probed is None:
            return False
        s.overrides = apply_audio(s.overrides, s.audio_template, e.probed.source.audio)
        s.audio_template = None
        return True

    def _claim_crop(self, e: Entry) -> bool:
        """Under the lock: mark a pending auto crop as started, once the job is probed. The caller then
        submits _detect_crop (to the probe pool: indexing the source takes a while)."""
        if (not e.spec.autocrop or e.cropping or e.probed is None or e.busy
                or self.services.detect_crop is None):
            return False
        e.cropping = True
        return True

    def _detect_crop(self, e: Entry) -> None:
        try:
            crop = self.services.detect_crop(e.spec)
        except Exception as ex:  # noqa: BLE001 - shown in the job's log; the crop stays as it was
            self._log(e, f"Auto-crop failed: {type(ex).__name__}: {ex}")
            crop = None
        with self._lock:
            e.cropping = False
            if self._entries.get(e.id) is not e:  # removed meanwhile
                return
            if e.spec.autocrop:  # an edit since didn't set a crop or another template
                e.spec.autocrop = False
                if crop is not None:
                    e.spec.video.crop = crop
                    self._replan(e)
                self._save(e)
        if crop is not None:
            self._log(e, f"Auto-crop: left {crop.left}, top {crop.top}, right {crop.right}, bottom {crop.bottom}")
        self._changed(e)

    def _replan(self, e: Entry) -> None:
        if e.probed is None:
            return
        try:
            e.plan = plan_spec(e.spec, e.probed, self.profile(e), self.app.tools)
            if e.spec.overrides.original_language is None:  # pin the guess so it survives edits
                e.spec.overrides.original_language = e.plan.original_language
        except Exception as ex:  # noqa: BLE001 - a profile bug shouldn't take the queue down
            e.plan, e.probe_error = None, f"Planning failed: {type(ex).__name__}: {ex}"

    def replan_all(self) -> None:
        """Plan every probed, idle job again (e.g. a tool path changed: missing tools block)."""
        for e in self.entries():
            with self._lock:
                if e.busy or e.probed is None:
                    continue
                self._replan(e)
            self._changed(e)

    # --- editing -----------------------------------------------------------------------

    def update(
        self,
        job_id: str,
        *,
        video: VideoSettings | None = None,
        encoder: EncoderSettings | None = None,
        overrides: Overrides | None = None,
        output_dir: Path | None = None,
        qpf: bool | None = None,
        profile: str | None = None,
        inputs: JobInputs | None = None,
        mux: MuxSettings | None = None,
        container: str | None = None,
        template: Template | None = None,
    ) -> Entry:
        """Change a job's settings and replan: the template first, then the given settings (container
        alone keeps the job's extra muxer arguments). New inputs (added subtitle files, chapters) are
        read at once; a different encode means probing again."""
        e = self.get(job_id)
        reprobe = False
        with self._lock:
            if e.busy:
                raise Busy(f"{e.spec.name} is queued or running")
            s = e.spec
            if inputs is not None and inputs != s.inputs:
                if inputs.source != s.inputs.source:
                    raise ValueError("A job's source can't change")
                reprobe = e.probed is None or inputs.encode != s.inputs.encode or inputs.audio != s.inputs.audio
                s.inputs = inputs
                if not reprobe:
                    ext, issues = external_tracks(e.probed.source, inputs.subtitles)
                    e.probed = replace(e.probed, external_subs=ext, issues=issues)
            if profile is not None and profile != s.profile:
                self.profiles(profile)  # unknown -> KeyError
                s.profile = profile
            if template is not None:
                template.apply(s)
            if video is not None:
                if video.crop != s.video.crop:
                    s.autocrop = False  # a crop set by hand wins over a pending detection
                s.video = video
            if encoder is not None:
                s.encoder = encoder
            if overrides is not None:
                s.overrides = overrides
            if output_dir is not None:
                s.output_dir = output_dir
            if qpf is not None:
                s.qpf = qpf
            if mux is not None:
                s.mux = mux
            if container is not None:
                s.mux = replace(s.mux, container=container)
            e.state.status, e.state.error, e.state.issues = None, "", []
            if not reprobe:
                self._apply_audio(e)
            self._replan(e)
            self._save(e)
            crop = not reprobe and self._claim_crop(e)
        self._changed(e)
        if reprobe:
            self.probe([e.id])
        if crop:
            self._probes.submit(self._detect_crop, e)
        return e

    def remove(self, ids: Iterable[str]) -> list[str]:
        removed = []
        with self._lock:
            for job_id in ids:
                e = self._entries.get(job_id)
                if e is None or e.busy:
                    continue
                del self._entries[job_id]
                self._order.remove(job_id)
                self.store.delete_job(job_id)
                removed.append(job_id)
        for job_id in removed:
            self.events.publish("job.removed", id=job_id)
        return removed

    def reorder(self, ids: list[str]) -> None:
        with self._lock:
            known = [i for i in ids if i in self._entries]
            self._order = known + [i for i in self._order if i not in known]
            self.store.reorder(self._order)
        self.events.publish("order", ids=list(self._order))

    # --- running -----------------------------------------------------------------------

    def enqueue(self, ids: Iterable[str] | None = None) -> list[str]:
        """Queue the given jobs (default: every runnable one), in queue order."""
        wanted = set(ids) if ids is not None else None
        queued = []
        with self._lock:
            for e in self.entries():
                if (wanted is None or e.id in wanted) and e.runnable:
                    e.queued = True
                    e.state.status, e.state.error = None, ""
                    self._save(e)
                    queued.append(e.id)
        for job_id in queued:
            self._changed(self.get(job_id))
        self._queue_changed()
        return queued

    def dequeue(self, ids: Iterable[str]) -> None:
        with self._lock:
            for job_id in ids:
                e = self._entries.get(job_id)
                if e is not None and e.queued:
                    e.queued = False
                    self._save(e)
                    self._changed(e)
        self._queue_changed()

    def start(self) -> None:
        with self._lock:
            self._stop_after_current = False
            if not self._active:
                self._active = True
                self._worker = threading.Thread(target=self._work, name="queue-worker", daemon=True)
                self._worker.start()
        self._queue_changed()

    def stop_after_current(self) -> None:
        self._stop_after_current = True
        self._queue_changed()

    def cancel_current(self) -> None:
        if self._cancel is not None:
            self._cancel.cancel()

    def wait(self, timeout: float | None = None) -> None:
        if self._worker is not None:
            self._worker.join(timeout)

    def shutdown(self, timeout: float = 10) -> None:
        """Stop for good: the running job is cancelled and waited for (it ends cancelled). One that doesn't
        stop in time is left as the store has it, running, so the next start queues it again."""
        with self._lock:
            self._closing = True
            self._stop_after_current = True
        self.cancel_current()
        self.wait(timeout)
        self._probes.shutdown(wait=False, cancel_futures=True)

    def _next(self) -> Entry | None:
        with self._lock:
            return next((e for e in self.entries() if e.queued and e.plan is not None), None)

    def _take_next(self) -> Entry | None:
        """The next job to run, or None after giving up the queue (so the last event says not running, and a
        start() from then on starts a new worker instead of relying on this one)."""
        with self._lock:
            e = None if self._stop_after_current else self._next()
            if e is None:
                self._active = False
            return e

    def _work(self) -> None:
        try:
            while (e := self._take_next()) is not None:
                self._run(e)
        finally:
            with self._lock:
                if self._worker is threading.current_thread():
                    self._active = False
            self._cancel = None
            self._queue_changed()

    def _run(self, e: Entry) -> None:
        assert e.plan is not None
        with self._lock:
            e.queued, e.running, e.progress = False, True, None
            self._cancel = CancelToken()
            if self._closing:  # taken just before shutdown() cancelled (it saw no token yet)
                self._cancel.cancel()
            self._save(e)
        self._changed(e)
        self._queue_changed()
        log_file = _open_log(e)
        last = [0.0]

        def log(line: str) -> None:
            self._log(e, line, log_file)

        def progress(p: StepProgress) -> None:
            e.progress = {"step": p.step.label, "index": p.index, "total": p.total, "fraction": round(p.fraction, 4),
                          "overall": round(p.overall, 4), "reused": p.reused}
            now = _now()
            if p.fraction in (0.0, 1.0) or now - last[0] >= _PROGRESS_INTERVAL:
                last[0] = now
                self.events.publish("progress", id=e.id, **e.progress)

        def on_record(_r: StepRecord) -> None:
            self._save(e)  # a crash after this step resumes after it

        def on_step(run: StepRun) -> None:
            if run.status is StepStatus.RUNNING:
                e.current_step = run.id
                e.step_lines[run.id] = deque(maxlen=STEP_LINES)
            elif e.current_step == run.id:
                e.current_step = None
            if run.status is not StepStatus.PENDING:
                self._save(e)
            index = next((i for i, r in enumerate(e.state.run) if r is run), -1)
            # index 0 pending = a new run's list starts (the browser drops the last run's)
            self.events.publish("step", id=e.id, index=index, total=len(e.state.run),
                                step=step_json(run, with_tail=False))

        with self._lock:
            e.step_lines, e.current_step = {}, None
        log(f"### {e.spec.name} ({datetime.now().isoformat(timespec='seconds')})")
        try:
            result = self.services.run(e.spec, e.plan, self.profile(e), self.app, state=e.state, log=log,
                                       cancel=self._cancel, progress=progress, on_record=on_record, on_step=on_step)
        except Exception as ex:  # noqa: BLE001 - a bug must not kill the queue
            result = JobResult(e.plan, JobStatus.FAILED, error=f"{type(ex).__name__}: {ex}")
            e.state.status, e.state.error = result.status, result.error
        log(f"{e.spec.name}: {result.status.value}" + (f" -> {result.output}" if result.output else "")
            + (f" ({result.error})" if result.error else ""))
        if self.services.record is not None:
            try:
                self.services.record(result)
            except OSError as ex:
                log(f"Could not save the job history: {ex}")
        if log_file is not None:
            log_file.close()
        with self._lock:
            e.running, e.progress, e.current_step = False, None, None
            self._save(e)
        self._changed(e)

    def _log(self, e: Entry, line: str, file=None) -> None:
        e.log.append(line)
        if file is not None:
            try:
                file.write(line + "\n")
            except OSError:
                pass
        step = e.current_step
        if step is not None and not line.startswith("== "):  # the step header is the step's panel
            e.step_lines[step].append(line)
        else:
            step = None
        self.events.publish("log", id=e.id, line=line, step=step)

    def step_output(self, e: Entry) -> list[dict[str, Any]]:
        """The last run's steps with their output: all of it while it's in memory, else the saved tail."""
        out = []
        for run in e.state.run:
            lines = e.step_lines.get(run.id)
            item = step_json(run, with_tail=False)
            item["lines"] = list(lines) if lines is not None else list(run.tail)
            item["partial"] = lines is None and len(run.tail) >= STEP_TAIL
            out.append(item)
        return out


def step_json(run: StepRun, *, with_tail: bool = True) -> dict[str, Any]:
    data = to_json(run)
    if not with_tail:
        data.pop("tail")
    return data


def _copy(obj):
    from copy import deepcopy

    return deepcopy(obj)


def _now() -> float:
    import time

    return time.monotonic()


def _open_log(e: Entry):
    """<source>_tmp/videoforge.log, appended to on every run."""
    try:
        e.spec.work_dir.mkdir(parents=True, exist_ok=True)
        return open(e.spec.work_dir / "videoforge.log", "a", encoding="utf-8", buffering=1)
    except OSError:
        return None
