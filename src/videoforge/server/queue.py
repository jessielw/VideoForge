"""The job queue: jobs in memory (spec, state, cached probe and plan), persisted in the
store, probed in a small thread pool, and run one at a time by a worker thread.

Next to it, the index lane: jobs asked to be indexed get their work folder, script and source
index, one at a time by a thread of its own (alongside a running encode), and nothing else. The
steps are recorded like a run's, so the encode reuses them. Nothing else indexes: the preview opens
only indexed sources, and a template's auto crop waits in the lane and runs after the index. A job
can't be edited while it is being indexed. The lane is kept across restarts, and (a setting) a job
waits while an encode reads its disk, unless it was asked for by itself (Index now).

Pause suspends the running job's tools and the index lane's together, and resume lets them go on (a tool
started meanwhile starts paused; Start resumes too). The Queue's priority choice is the running ones' for the
rest of their run; the next ones get the Settings' again.

Every change is saved and announced on the event hub. An edit replans from the
cached probe (no file access) and clears the last run's outcome, but keeps the
finished steps, so a rerun only redoes what the edit touched.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
import logging
import os
from pathlib import Path
import sqlite3
import threading
from typing import Any

from videoforge.core.config import AppConfig, Tools
from videoforge.core.disks import disks
from videoforge.core.events import EventBus, IndexFinished, JobFinished, JobStarted, QueueFinished
from videoforge.core.execute import process
from videoforge.core.execute.control import Priority
from videoforge.core.execute.mux import MuxSettings
from videoforge.core.execute.process import Cancelled, CancelToken, ToolError
from videoforge.core.job import (
    STEP_TAIL,
    JobResult,
    JobSpec,
    JobState,
    JobStatus,
    StepRecord,
    StepRun,
    StepStatus,
    clean_label,
    clean_output_name,
    plan_spec,
    probe_spec,
)
from videoforge.core.jobs import ProbedInputs, external_tracks
from videoforge.core.models import (
    AudioMatch,
    Issue,
    JobInputs,
    Overrides,
    Plan,
    Severity,
    SubTrack,
    VideoInfo,
    track_key,
)
from videoforge.core.notify import Sender, send as notify_send
from videoforge.core.pipeline.build import index_steps, job_output
from videoforge.core.pipeline.reuse import ReuseOffer, reuse_offers
from videoforge.core.pipeline.run import missing_inputs, run_job
from videoforge.core.pipeline.steps import ProgressFn, StepProgress, run_steps
from videoforge.core.plan_io import to_json
from videoforge.core.profile import Profile
from videoforge.core.record import JsonLines, RunRecorder, event
from videoforge.core.template import Template, apply_audio, apply_subs, template_choice
from videoforge.core.tools import versions as tool_versions
from videoforge.core.video.settings import Crop, EncoderSettings, VideoSettings
from videoforge.core.workdir import clean_work_dir, work_dir
from videoforge.server.events import EventHub
from videoforge.server.store import Store

LOG_LINES = 5000
STEP_LINES = 3000  # per step, in memory
_PROGRESS_INTERVAL = 0.25  # seconds between progress events per job
_ETA_AFTER = (0.01, 5.0)  # a job's time left is guessed once this run moved overall this far, for this long
logger = logging.getLogger(__name__)
LANE_SETTING = "index_lane"  # the store's record of the lane: job ids in order, the one being indexed first


_OUTFILE = ("outfile.shared", "outfile.exists")  # JobQueue._refresh_outputs' issue codes


def _same_file(path: Path | None) -> str:
    """A path as the file system compares it (Windows: case-insensitive), without touching the disk."""
    return os.path.normcase(os.path.abspath(path)) if path is not None else ""


def _exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:  # an unreachable share
        return False


class JobView(StrEnum):
    """What the queue shows for a job."""

    PROBING = "probing"
    ERROR = "error"  # the probe failed
    CROPPING = "cropping"  # detecting the crop (a template's auto crop)
    INDEXING = "indexing"  # the index lane is on it
    INDEX_QUEUED = "index-queued"  # waiting in the index lane
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
    index_queued: bool = False
    indexing: bool = False
    crop_pending: bool = False  # the lane detects the crop after indexing (a template's auto crop)
    index_now: bool = False  # asked for by itself (Index now): doesn't wait for an encode on its disk
    index_held: bool = False  # waiting in the lane while an encode reads its disk
    index_error: str = ""
    # Held by whatever may build the source's index: the index lane, auto-crop, and a preview request
    # for a clip the preview worker doesn't hold yet. Two processes never index one source at once.
    source_lock: threading.Lock = field(default_factory=threading.Lock)
    progress: dict[str, Any] | None = None
    log: deque[str] = field(default_factory=lambda: deque(maxlen=LOG_LINES))
    # The last run's output per step (in memory; state.run keeps only each step's tail).
    step_lines: dict[str, deque[str]] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.spec.id

    @property
    def source_video(self) -> VideoInfo | None:
        """The source's video as probed (None before the probe)."""
        if self.plan is not None:
            return self.plan.source.video
        return self.probed.source.video if self.probed is not None else None

    @property
    def burn(self) -> SubTrack | None:
        """The subtitle track the job burns into its video (None before the plan)."""
        return self.plan.burn if self.plan is not None else None

    @property
    def busy(self) -> bool:
        return self.queued or self.running

    @property
    def runnable(self) -> bool:
        return (
            self.plan is not None
            and not self.plan.blocked
            and not self.busy
            and not self.cropping
            and not self.indexing
            and not self.crop_pending
        )

    @property
    def status(self) -> JobView:
        if self.running:
            return JobView.RUNNING
        if self.queued:
            return JobView.QUEUED
        if self.indexing:
            return JobView.INDEXING
        if self.index_queued:
            return JobView.INDEX_QUEUED
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
    detect_crop: Callable[[JobSpec], Crop] | None = None  # reads the source (VapourSynth)
    release_preview: Callable[[list[str]], None] | None = None  # frees the jobs' preview clips (their open files)
    runner: Callable[..., None] = process.run  # the index lane's tool runner
    versions: Callable[[Tools, Sequence[str]], dict[str, str]] | None = tool_versions  # for job records
    send_notification: Sender = notify_send  # one message to one Apprise URL


class JobQueue:
    def __init__(
        self,
        app: AppConfig,
        profiles: Callable[[str], Profile],
        store: Store,
        events: EventHub,
        services: Services | None = None,
        probe_workers: int = 2,
        queue_events: JsonLines | None = None,
        bus: EventBus | None = None,
        records_dir: Path | None = None,
    ) -> None:
        self.app, self.profiles, self.store, self.events = app, profiles, store, events
        self.services = services or Services()
        self.queue_events = queue_events  # every job's events in one stream (core/record.py)
        self.records_dir = records_dir  # where a deleted work folder's records go (app.delete_work_dir)
        # What a run did, for notifications, actions and plugins (core/events.py); the hub above is the browser's.
        self.bus = bus or EventBus()
        self._entries: dict[str, Entry] = {}
        self._removed: dict[str, tuple[Entry, int]] = {}  # last 100 removals, undo until server restart
        self._order: list[str] = []
        self._lock = threading.RLock()
        self._probes = ThreadPoolExecutor(max_workers=probe_workers, thread_name_prefix="probe")
        self._worker: threading.Thread | None = None
        self._active = False  # a worker owns the queue; cleared (under the lock) when it decides to stop
        self._cancel: CancelToken | None = None
        self._stop_after_current = False
        self._closing = False  # shutdown() began: a job starting now is cancelled at once
        self._paused = False  # pause(): the running job's and the index lane's tools are suspended
        self._indexer: threading.Thread | None = None
        self._index_active = False  # the lane's thread is working; cleared (under the lock) when it decides to stop
        self._index_order: list[str] = []  # the lane's jobs, in the order they're indexed
        self._index_cancel: CancelToken | None = None
        self._index_wake = threading.Event()
        self.index_waits_for_disk = True  # the lane holds a job back while an encode reads its disk

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
        return {
            "running": self.running,
            "current": current,
            "stop_after_current": self._stop_after_current,
            "paused": self._paused,
            "priority": next((t.priority for t in self._tokens()), None),  # the Queue's choice, while running
            "queued": sum(e.queued for e in self.entries()),
            "indexing": next((e.id for e in self.entries() if e.indexing), None),
            "index_queued": sum(e.index_queued for e in self.entries()),
        }

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
        """Jobs from the store; a job the server stopped in the middle of is queued again, and the index
        lane goes on where it stopped (a job stopped mid-index is indexed again)."""
        for stored in self.store.load_jobs():
            e = Entry(stored.spec, stored.state, queued=stored.queued or stored.running)
            if stored.running:
                e.state.status = None
                e.state.error = (
                    "Interrupted: the server stopped during this job; it resumes after its last finished step"
                )
            with self._lock:
                self._entries[e.id] = e
                self._order.append(e.id)
            self._save(e)
        lane = [i for i in self.store.get_setting(LANE_SETTING) or [] if i in self._entries]
        logger.info(
            "%d job(s) loaded, %d queued, %d to index",
            len(self._entries),
            sum(e.queued for e in self._entries.values()),
            len(lane),
        )
        with self._lock:  # every job is probing until this returns, so the lane takes none before its order is set
            self.probe([e.id for e in self.entries()])
            if lane:
                self.index(lane)
                self._index_order = [i for i in lane if i in self._index_order] + [
                    i for i in self._index_order if i not in lane
                ]
                self._save_lane()

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
        try:
            probed = self.services.probe(e.spec, self.app)
        except Exception as ex:  # shown on the job
            with self._lock:
                e.probing, e.probe_error = False, f"{type(ex).__name__}: {ex}"
            self._log(e, f"Probe failed: {e.probe_error}")
            logger.warning("%s: probe failed: %s", e.spec.name, e.probe_error)
        else:
            with self._lock:
                e.probing, e.probed = False, probed
                if self._apply_tracks(e):
                    self._save(e)
                self._replan(e)
                if self._claim_crop(e):
                    self.index([e.id])  # under the lock: the job never shows ready in between
        self._changed(e)
        self._index_wake.set()

    def _apply_tracks(self, e: Entry) -> bool:
        """Under the lock: a template's pending audio and subtitles become the job's overrides once its
        tracks are known. A profile without a track editor chooses tracks by its own rules, so there
        they're dropped."""
        s = e.spec
        if (s.audio_template is None and s.subs_template is None) or e.probed is None:
            return False
        if self.profile(e).track_editor:
            if s.audio_template is not None:
                if s.audio_template.mode is AudioMatch.RULES and s.overrides.original_language is None:
                    self._replan(e)  # rules can ask for the original language: pin the profile's guess first
                audio = e.probed.source.audio
                s.overrides = apply_audio(s.overrides, s.audio_template, audio, s.overrides.original_language)
                s.audio_from_template = template_choice(s.overrides, [track_key(t) for t in audio])
            if s.subs_template is not None:
                subs = e.probed.source.subs + e.probed.external_subs
                s.overrides = apply_subs(s.overrides, s.subs_template, subs)
                s.subs_from_template = template_choice(s.overrides, [track_key(t) for t in subs])
        s.audio_template = s.subs_template = None
        return True

    def _claim_crop(self, e: Entry) -> bool:
        """Under the lock: once the job is probed, a pending auto crop waits for the index lane (it reads
        the source, so it's indexed first, one job at a time). The caller then puts the job in the lane."""
        if (
            not e.spec.autocrop
            or e.cropping
            or e.crop_pending
            or e.probed is None
            or e.busy
            or self.services.detect_crop is None
        ):
            return False
        e.crop_pending = True
        return True

    def _detect_crop(self, e: Entry) -> None:
        """On the index lane, holding the job's source lock, after its index."""
        with self._lock:
            e.cropping = True
        self._changed(e)
        try:
            detect = self.services.detect_crop
            if detect is None:  # _crop_due checked it
                raise RuntimeError("No crop detection")
            crop = detect(e.spec)
        except Exception as ex:  # shown in the job's log; the crop stays as it was
            self._log(e, f"Auto-crop failed: {type(ex).__name__}: {ex}")
            logger.warning("%s: auto-crop failed: %s: %s", e.spec.name, type(ex).__name__, ex)
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
        self._index_wake.set()

    def _replan(self, e: Entry) -> None:
        if e.probed is None:
            return
        # A keep-AR resize follows the source and crop (a new probe, an auto-crop, a template's width).
        v = e.probed.source.video
        if v is not None and e.spec.video.fit_resize(v.width, v.height, v.sar):
            self._save(e)
        try:
            e.plan = plan_spec(e.spec, e.probed, self.profile(e), self.app.tools)
            if e.spec.overrides.original_language is None:  # pin the guess so it survives edits
                e.spec.overrides.original_language = e.plan.original_language
        except Exception as ex:  # a profile bug shouldn't take the queue down
            e.plan, e.probe_error = None, f"Planning failed: {type(ex).__name__}: {ex}"
        self._refresh_outputs([e])

    def _refresh_outputs(self, fresh: Iterable[Entry] = ()) -> None:
        """Under the lock: each planned job's issues about the file it writes, as StaxRip's assistant warns of
        them. Two jobs writing one file block (the idle ones: a queued or running job keeps its file), and a file
        that is already there, and isn't the job's own last output, warns. The fresh jobs (just planned) have
        their file looked at again; the others keep what their last look found."""
        fresh_ids = {e.id for e in fresh}
        outputs: dict[str, Path] = {}
        for e in self.entries():
            if e.plan is None:
                continue
            try:
                path = job_output(e.spec, e.plan, self.profile(e))
            except Exception as ex:  # a profile's naming bug shows when the job runs
                logger.debug("%s: no output path (%s)", e.spec.name, ex)
                continue
            if path is not None:
                outputs[e.id] = path
        sharing: dict[str, list[Entry]] = defaultdict(list)
        for e in self.entries():
            if e.id in outputs:
                sharing[_same_file(outputs[e.id])].append(e)
        for e in self.entries():
            if e.plan is None or e.running:
                continue
            old = [i for i in e.plan.issues if i.code in _OUTFILE]
            new: list[Issue] = []
            path = outputs.get(e.id)
            others = [o for o in sharing[_same_file(path)] if o is not e] if path is not None else []
            if others and not e.busy:
                names = ", ".join(dict.fromkeys(o.spec.name for o in others))
                new.append(
                    Issue(
                        Severity.BLOCK,
                        "outfile.shared",
                        f"Another job ({names}) writes the same file, {path.name if path else ''}: give one a "
                        "label (Output tab), or another output name or folder",
                    )
                )
            if e.id not in fresh_ids:
                new += [i for i in old if i.code == "outfile.exists"]
            elif (
                path is not None
                and _exists(path)
                and not (e.state.output is not None and _same_file(e.state.output) == _same_file(path))
            ):
                new.append(Issue(Severity.WARN, "outfile.exists", f"{path} already exists: the run replaces it"))
            if new != old:
                e.plan.issues = [i for i in e.plan.issues if i.code not in _OUTFILE] + new
                if e.id not in fresh_ids:  # the caller announces its own
                    self._changed(e)

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
        label: str | None = None,
        output_name: str | None = None,
    ) -> Entry:
        """Change a job's settings and replan: the template first, then the given settings (container
        alone keeps the job's extra muxer arguments). New inputs (added subtitle files, chapters) are
        read at once; a different encode means probing again."""
        e = self.get(job_id)
        reprobe = False
        with self._lock:
            if e.busy:
                raise Busy(f"{e.spec.name} is queued or running")
            if e.indexing:
                raise Busy(f"{e.spec.name} is being indexed")
            s = e.spec
            if inputs is not None and inputs != s.inputs:
                if inputs.source != s.inputs.source:
                    raise ValueError("A job's source can't change")
                reprobe = e.probed is None or inputs.encode != s.inputs.encode or inputs.audio != s.inputs.audio
                s.inputs = inputs
                if not reprobe and e.probed is not None:
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
            if label is not None:
                s.label = clean_label(label)
            if output_name is not None:
                s.output_name = clean_output_name(output_name)
            e.state.status, e.state.error, e.state.issues = None, "", []
            if not reprobe:
                self._apply_tracks(e)
            self._replan(e)
            self._save(e)
            if not reprobe and self._claim_crop(e):
                self.index([e.id])
        self._changed(e)
        if reprobe:
            self.probe([e.id])
        return e

    def remove(self, ids: Iterable[str]) -> list[str]:
        removed = []
        with self._lock:
            for job_id in ids:
                e = self._entries.get(job_id)
                if e is None or e.busy or e.indexing:
                    continue
                self._removed[job_id] = (e, self._order.index(job_id))
                while len(self._removed) > 100:
                    del self._removed[next(iter(self._removed))]
                del self._entries[job_id]
                self._order.remove(job_id)
                self.store.delete_job(job_id)
                removed.append(job_id)
            if removed:
                self._refresh_outputs()
        if removed and self.services.release_preview is not None:
            self.services.release_preview(removed)  # their work folders may be deleted next
        for job_id in removed:
            self.events.publish("job.removed", id=job_id)
        return removed

    def restore(self, ids: Iterable[str]) -> list[str]:
        """Undo queue removal without replacing another job on the same source."""
        restored = []
        with self._lock:
            for job_id in reversed(list(ids)):
                found = self._removed.get(job_id)
                if found is None or self._find_source(found[0].spec.inputs.source) is not None:
                    continue
                e, position = self._removed.pop(job_id)
                e.queued = e.index_queued = e.index_now = e.index_held = False
                self._entries[job_id] = e
                self._order.insert(min(position, len(self._order)), job_id)
                self._replan(e)
                self._save(e)
                restored.append(job_id)
            self.store.reorder(self._order)
        for job_id in restored:
            self.events.publish("job.added", id=job_id)
        return restored

    def reorder(self, ids: list[str]) -> None:
        with self._lock:
            known = [i for i in ids if i in self._entries]
            self._order = known + [i for i in self._order if i not in known]
            self.store.reorder(self._order)
        self.events.publish("order", ids=list(self._order))

    # --- running -----------------------------------------------------------------------

    def enqueue(self, ids: Iterable[str] | None = None) -> list[str]:
        """Queue explicit runnable jobs, or only pending work by default. Retries/reruns are explicit."""
        wanted = set(ids) if ids is not None else None
        queued = []
        with self._lock:
            for e in self.entries():
                if (e.state.status is None if wanted is None else e.id in wanted) and e.runnable:
                    e.queued = True
                    e.index_queued = e.index_now = e.index_held = False  # the run indexes it first anyway
                    e.state.status, e.state.error = None, ""
                    self._save(e)
                    queued.append(e.id)
            self._save_lane()
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

    def start_targets(self, ids: Iterable[str] | None = None) -> list[Entry]:
        """The jobs a start would run: the given ones that are runnable or queued; with none given, the
        queued ones, or every runnable one when none is queued (as the start route queues them)."""
        with self._lock:
            entries = self.entries()
            if ids is not None:
                wanted = set(ids)
                return [e for e in entries if e.id in wanted and (e.runnable or e.queued)]
            queued = [e for e in entries if e.queued]
            return queued or [e for e in entries if e.runnable and e.state.status is None]

    def reuse_offers(self, e: Entry) -> list[ReuseOffer]:
        """The finished files e's next run could reuse (core/pipeline/reuse.py); [] when it can't be built."""
        if e.plan is None or e.running:
            return []
        try:
            return reuse_offers(e.spec, e.plan, self.profile(e), self.app, e.state.steps)
        except (ToolError, OSError, ValueError) as ex:
            logger.warning("%s: no reuse offers (%s)", e.spec.name, ex)
            return []

    def choose_reuse(self, choices: dict[str, Iterable[str]]) -> None:
        """The user's answer to the reuse question, per job: the sections to reuse (offer ids). Those are
        kept on the next run whatever their settings; the other offered sections are made again."""
        for job_id, chosen in choices.items():
            e = self._entries.get(job_id)
            if e is None or e.running:
                continue
            offers, wanted = self.reuse_offers(e), set(chosen)
            with self._lock:
                e.state.keep = [s for o in offers if o.id in wanted for s in o.steps]
                for o in offers:
                    if o.id not in wanted:
                        for s in o.steps:
                            e.state.steps.pop(s, None)
                self._save(e)
            logger.info(
                "%s: reuse %s, redo %s",
                e.spec.name,
                [o.id for o in offers if o.id in wanted] or "nothing",
                [o.id for o in offers if o.id not in wanted] or "nothing",
            )

    def start(self) -> None:
        self.resume()
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

    def _token(self) -> CancelToken:
        """Under the lock: a new run's token, with the Settings' priorities, paused if the queue is."""
        token = CancelToken(encoder_priority=self.app.encoder_priority, tool_priority=self.app.tool_priority)
        if self._paused:
            token.pause()
        if self._closing:  # taken just before shutdown() cancelled (it saw no token yet)
            token.cancel()
        return token

    def _tokens(self) -> list[CancelToken]:
        return [t for t in (self._cancel, self._index_cancel) if t is not None]

    def pause(self) -> None:
        """Suspend the running job's tools and the index lane's (nothing running: nothing to pause)."""
        with self._lock:
            tokens = self._tokens()
            self._paused = bool(tokens) or self._paused
            for token in tokens:
                token.pause()
        self._queue_changed()

    def resume(self) -> None:
        with self._lock:
            was, self._paused = self._paused, False
            for token in self._tokens():
                token.resume()
        if was:
            self._queue_changed()

    def set_priority(self, priority: Priority | None) -> None:
        """The running job's and the index lane's tools get this priority, for the rest of their run (None: the
        Settings' again)."""
        with self._lock:
            for token in self._tokens():
                token.set_priority(priority)
        self._queue_changed()

    def _settle(self) -> None:
        """Under the lock: with nothing left running, the queue isn't paused."""
        if not self._active and not self._index_active:
            self._paused = False

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
        self.stop_indexing()
        self.wait(timeout)
        if self._indexer is not None:
            self._indexer.join(timeout)
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
        ran: list[JobStatus] = []
        started = _now()
        try:
            while (e := self._take_next()) is not None:
                ran.append(self._run(e))
        finally:
            with self._lock:
                if self._worker is threading.current_thread():
                    self._active = False
                self._cancel = None
                self._settle()
            self._queue_changed()
            if ran and not self._closing:
                left = sum(e.queued for e in self.entries()) if self._stop_after_current else 0
                self.bus.emit(QueueFinished(tuple(ran), _now() - started, left))

    def _run(self, e: Entry) -> JobStatus:
        if e.plan is None:
            raise RuntimeError(f"{e.spec.name}: run without a plan")
        started = _now()
        with self._lock:
            e.queued, e.running, e.progress = False, True, None
            self._cancel = self._token()
            self._save(e)
        self._changed(e)
        self._queue_changed()
        log_file = _open_log(e)
        logger.info("Job %s started (%s)", e.spec.name, e.id)
        recorder = RunRecorder(
            e.spec,
            e.plan,
            self.profile(e),
            job_output(e.spec, e.plan, self.profile(e)),
            queue_events=self.queue_events,
            versions=self._versions,
        )
        recorder.started_run()
        self.bus.emit(JobStarted(_copy(e.spec), recorder.output))

        def log(line: str) -> None:
            self._log(e, line, log_file)

        progress = self._progress(e, self._cancel)

        def on_record(_r: StepRecord) -> None:
            self._save(e)  # a crash after this step resumes after it

        def on_step(run: StepRun) -> None:
            if run.status is StepStatus.RUNNING:
                e.step_lines[run.id] = deque(maxlen=STEP_LINES)
            if run.status is not StepStatus.PENDING:
                self._save(e)
            index = next((i for i, r in enumerate(e.state.run) if r is run), -1)
            recorder.step(run, index, len(e.state.run))
            # index 0 pending = a new run's list starts (the browser drops the last run's)
            self.events.publish(
                "step", id=e.id, index=index, total=len(e.state.run), step=step_json(run, with_tail=False)
            )

        def step_log(run: StepRun, line: str) -> None:
            self._log(e, line, log_file, step=run.id)

        with self._lock:
            e.step_lines = {}
        log(f"### {e.spec.name} ({datetime.now().isoformat(timespec='seconds')})")
        try:
            result = self.services.run(
                e.spec,
                e.plan,
                self.profile(e),
                self.app,
                state=e.state,
                log=log,
                cancel=self._cancel,
                progress=progress,
                on_record=on_record,
                on_step=on_step,
                step_log=step_log,
            )
        except Exception as ex:  # a bug must not kill the queue
            logger.exception("%s: the run raised", e.spec.name)
            result = JobResult(e.plan, JobStatus.FAILED, error=f"{type(ex).__name__}: {ex}")
            e.state.status, e.state.error = result.status, result.error
        if record := recorder.finished(result, e.state):
            log(f"Job record: {record}")
        if result.status is JobStatus.DONE:
            log(f"Job complete: {result.output}")
        else:
            log(
                f"{e.spec.name}: {result.status.value}"
                + (f" -> {result.output}" if result.output else "")
                + (f" ({result.error})" if result.error else "")
            )
        logger.log(
            logging.INFO if result.status is JobStatus.DONE else logging.WARNING,
            "Job %s: %s%s%s",
            e.spec.name,
            result.status.value,
            f" -> {result.output}" if result.output else "",
            f" ({result.error})" if result.error else "",
        )
        if log_file is not None:
            log_file.close()
        if result.status is JobStatus.DONE and self.app.delete_work_dir:
            record = self._clean_up(e, record)
        with self._lock:
            e.running, e.progress = False, None
            self._save(e)
            self._refresh_outputs([e])  # its output is its own now; jobs it held back may run
        self._changed(e)
        self._index_wake.set()  # a job held back for this one's disk may go
        if not self._closing:  # a shutdown's cancel isn't news: the job resumes on the next start
            self.bus.emit(JobFinished(_copy(e.spec), result, _now() - started, record))
        return result.status

    def _progress(self, e: Entry, token: CancelToken | None) -> ProgressFn:
        """A run's progress callback (a job's or the index lane's): sets e.progress, with the step's fps and eta
        when its encoder prints them, the seconds since the run started, and the job's time left (from how fast
        overall moved since this run's own work began: steps reused from an earlier run don't count), and
        publishes it at most every _PROGRESS_INTERVAL (a step's start and end always). Time paused (the token's)
        doesn't count."""

        def clock() -> float:
            return _now() - (token.paused_seconds if token is not None else 0.0)

        started = clock()
        last = 0.0
        base: tuple[float, float] | None = None  # (time, overall) at the first step this run does itself

        def progress(p: StepProgress) -> None:
            nonlocal last, base
            now = clock()
            if base is None and not p.reused:
                base = (now, p.overall)
            left = None
            if base is not None and p.overall - base[1] >= _ETA_AFTER[0] and now - base[0] >= _ETA_AFTER[1]:
                left = round((now - base[0]) * (1 - p.overall) / (p.overall - base[1]))
            e.progress = {
                "step": p.step.label,
                "index": p.index,
                "total": p.total,
                "fraction": round(p.fraction, 4),
                "overall": round(p.overall, 4),
                "reused": p.reused,
                "fps": None if p.fps is None else round(p.fps, 2),
                "eta": p.eta,
                "elapsed": round(now - started),
                "left": left,
            }
            if p.fraction in (0.0, 1.0) or now - last >= _PROGRESS_INTERVAL:
                last = now
                self.events.publish("progress", id=e.id, **e.progress)

        return progress

    def _clean_up(self, e: Entry, record: Path | None) -> Path | None:
        """A done job's work folder, deleted (AppConfig.delete_work_dir) once its records and log are copied
        to records_dir; kept while a preview is indexing the source. Returns where the job record is now."""
        if not e.source_lock.acquire(blocking=False):
            self._log(e, "Work folder kept: a preview is reading it")
            return record
        source = e.spec.inputs.source
        try:
            kept = clean_work_dir(source, self.records_dir)
        except OSError as ex:
            self._log(e, f"Work folder not deleted: {ex}")
            return record
        finally:
            e.source_lock.release()
        self._log(e, f"Work folder deleted: {e.spec.work_dir}")
        logger.info("%s: work folder deleted (records kept in %s)", e.spec.name, self.records_dir)
        return kept.get(record.name) if record is not None else None

    def delete_work_dirs(self, sources: Iterable[Path]) -> tuple[list[str], dict[str, str]]:
        """Delete the work folders of removed jobs' sources, unless the source is back in the queue (added
        again meanwhile). Returns (deleted folders, {folder: why it was kept}); a source without one is left out."""
        deleted, kept = [], {}
        for source in dict.fromkeys(sources):
            folder = work_dir(source)
            if not folder.is_dir():
                continue
            with self._lock:
                shared = self._find_source(source)
                if shared is not None:
                    kept[str(folder)] = f"{shared.spec.name} uses it too"
                    continue
                try:
                    clean_work_dir(source, self.records_dir)
                except OSError as ex:
                    kept[str(folder)] = str(ex)
                    continue
            deleted.append(str(folder))
            logger.info("Work folder deleted: %s", folder)
        return deleted, kept

    # --- the index lane ------------------------------------------------------------------

    def index(self, ids: Iterable[str], *, first: bool = False) -> list[str]:
        """Put jobs in the index lane, in queue order, after the ones there (`first`: before them, e.g. the
        job open in the editor; one already waiting moves up, and neither waits for an encode on its disk).
        Jobs that reuse an encode, are queued, running or being indexed are left out. Returns the ids it took."""
        wanted = set(ids)
        taken = []
        with self._lock:
            for e in self.entries():
                if e.id not in wanted or not e.spec.encodes_video or e.busy or e.indexing:
                    continue
                if not e.index_queued or first:
                    e.index_queued, e.index_error = True, ""
                    e.index_now = e.index_now or first
                    taken.append(e.id)
            rest = [i for i in self._index_order if i not in taken]
            self._index_order = taken + rest if first else rest + taken
            self._save_lane()
            if taken and not self._index_active and not self._closing:
                self._index_active = True
                self._indexer = threading.Thread(target=self._index_work, name="indexer", daemon=True)
                self._indexer.start()
        self._index_wake.set()
        for job_id in taken:
            self._changed(self.get(job_id))
        self._queue_changed()
        return taken

    def set_index_waits_for_disk(self, on: bool) -> None:
        self.index_waits_for_disk = on
        self._index_wake.set()  # jobs held back go now (or wait from now)

    def stop_indexing(self, ids: Iterable[str] | None = None) -> None:
        """Take jobs (default: all) out of the index lane; the one being indexed is cancelled."""
        wanted = set(ids) if ids is not None else None
        with self._lock:
            dropped = [e for e in self.entries() if e.index_queued and (wanted is None or e.id in wanted)]
            for e in dropped:
                e.index_queued = e.index_now = e.index_held = False
            current = next((e for e in self.entries() if e.indexing), None)
            if current is not None and (wanted is None or current.id in wanted) and self._index_cancel is not None:
                self._index_cancel.cancel()
            self._save_lane()
        self._index_wake.set()
        for e in dropped:
            self._changed(e)
        self._queue_changed()

    def _save_lane(self) -> None:
        """Under the lock: the lane's order in the store, so a restart goes on with it. Not once shutting
        down: stopping the lane then keeps it for the next start."""
        if self._closing:
            return
        ids = [e.id for e in self.entries() if e.indexing] + [
            i for i in self._index_order if i in self._entries and self._entries[i].index_queued
        ]
        self.store.set_setting(LANE_SETTING, ids)

    def _encode_disks(self) -> frozenset[str]:
        """Under the lock: the disks the encode queue reads now, or is about to (between two jobs)."""
        e = next((x for x in self.entries() if x.running), None)
        if e is None and self._active and not self._stop_after_current:
            e = self._next()
        if e is None:
            return frozenset()
        s = e.spec
        paths = [
            s.inputs.source,
            s.work_dir,
            *([s.output_dir] if s.output_dir else []),
            *([s.inputs.encode] if s.inputs.encode else []),
        ]
        return frozenset().union(*(disks(p) for p in paths))

    def _take_index(self) -> tuple[Entry | None, bool, list[Entry]]:
        """(the next job to index, whether any are left, jobs held back or let go). A job still probing
        waits; so does one on a disk an encode reads (`index_waits_for_disk`) unless it was asked for by
        itself, and a job on another disk goes ahead of it."""
        with self._lock:
            waiting = [
                self._entries[i] for i in self._index_order if i in self._entries and self._entries[i].index_queued
            ]
            self._index_order = [e.id for e in waiting]
            busy = self._encode_disks() if self.index_waits_for_disk else frozenset()
            taken, changed = None, []
            for e in waiting:
                held = not e.probing and not e.index_now and bool(busy and busy & disks(e.spec.inputs.source))
                if held != e.index_held:
                    e.index_held = held
                    changed.append(e)
                if taken is None and not e.probing and not held:
                    taken = e
            if taken is not None:
                self._index_order.remove(taken.id)
                taken.index_queued, taken.index_now, taken.indexing, taken.progress = False, False, True, None
                self._index_cancel = self._token()
                return taken, True, changed
            if not waiting or self._closing:
                self._index_active = False
                self._settle()
                return None, False, changed
            return None, True, changed

    def _index_work(self) -> None:
        while True:
            self._index_wake.clear()
            e, left, changed = self._take_index()
            for c in changed:
                if c is not e:
                    self._changed(c)
            if e is not None:
                self._changed(e)
                self._queue_changed()
                self._index(e)
            elif left:
                self._index_wake.wait(1.0)
            else:
                break
        self._queue_changed()

    def _index(self, e: Entry) -> None:
        log_file = _open_log(e)  # makes the work folder too

        def log(line: str) -> None:
            self._log(e, line, log_file)

        progress = self._progress(e, self._index_cancel)

        def on_record(_r: StepRecord) -> None:
            with self._lock:
                self._save(e)

        error = ""
        self._queue_event("index.started", e)
        log(f"### {e.spec.name}: index ({datetime.now().isoformat(timespec='seconds')})")
        try:
            if e.probe_error:
                raise ToolError(f"The job couldn't be probed: {e.probe_error}")
            if missing := missing_inputs(e.spec):
                raise ToolError("Missing input: " + ", ".join(str(p) for p in missing))
            with self._lock:
                steps = index_steps(e.spec, self.app, e.source_video, e.burn)
                cancel = self._index_cancel
                sharing = [o.id for o in self._entries.values() if o.spec.work_dir == e.spec.work_dir]
            if self.services.release_preview is not None:
                self.services.release_preview(sharing)  # a step may write a file a preview clip holds open
            if cancel is None:
                raise RuntimeError("index lane: no cancel event")
            if not e.source_lock.acquire(blocking=False):
                log("Waiting for the preview, which is indexing this source")
                while not e.source_lock.acquire(timeout=0.2):
                    if cancel.cancelled:
                        raise Cancelled()
            try:
                # The job's records (no run of it can start while it's in the lane), so its encode reuses these steps.
                run_steps(
                    steps,
                    e.state.steps,
                    log=log,
                    cancel=cancel,
                    progress=progress,
                    on_record=on_record,
                    runner=self.services.runner,
                )
                if e.spec.autocrop and self.services.detect_crop is not None:  # a template's auto crop
                    with self._lock:
                        e.indexing, e.progress = False, None  # it can be edited again (a hand crop wins)
                    self._detect_crop(e)
            finally:
                e.source_lock.release()
        except Cancelled:
            error = "Cancelled"
        except (ToolError, OSError, ValueError) as ex:
            error = str(ex)
        except Exception as ex:  # a bug must not stop the lane
            logger.exception("%s: indexing raised", e.spec.name)
            error = f"{type(ex).__name__}: {ex}"
        log(f"{e.spec.name}: index " + (f"failed ({error})" if error else "done"))
        if error and error != "Cancelled":
            logger.warning("%s: index failed: %s", e.spec.name, error)
        else:
            logger.info("%s: index %s", e.spec.name, "cancelled" if error else "done")
        self._queue_event("index.finished", e, error=error or None)
        if not self._closing:
            self.bus.emit(IndexFinished(_copy(e.spec), error or None))
        if log_file is not None:
            log_file.close()
        with self._lock:
            e.indexing, e.progress, e.index_error = False, None, "" if error == "Cancelled" else error
            e.crop_pending = False
            self._index_cancel = None
            self._save(e)
            self._save_lane()
        self._changed(e)
        self._queue_changed()

    def _versions(self, names: Sequence[str]) -> dict[str, str]:
        return self.services.versions(self.app.tools, names) if self.services.versions else {}

    def job_log(self, job_id: str, line: str) -> None:
        """A line in a job's log from outside a run (an action or a plugin, after the job ended): shown in
        the browser and appended to <source>_tmp/videoforge.log (when there still is one: a done job's may
        be deleted). A job no longer in the queue is skipped."""
        with self._lock:
            e = self._entries.get(job_id)
        if e is None:
            return
        log_file = _open_log(e) if e.spec.work_dir.is_dir() else None
        try:
            self._log(e, line, log_file)
        finally:
            if log_file is not None:
                log_file.close()

    def _queue_event(self, kind: str, e: Entry, **fields: Any) -> None:
        if self.queue_events is not None:
            self.queue_events.write(event(kind, job=e.id, name=e.spec.name, **fields))

    def _log(self, e: Entry, line: str, file=None, step: str | None = None) -> None:
        """step: the step whose output it is (several run at once while audio encodes run beside the video)."""
        e.log.append(line)
        if file is not None:
            try:
                file.write(f"{datetime.now():%H:%M:%S} {line}\n")
            except OSError:
                pass
        if step is not None:
            e.step_lines.setdefault(step, deque(maxlen=STEP_LINES)).append(line)
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
