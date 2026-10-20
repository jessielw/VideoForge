"""Pipeline steps and the loop that runs them, skipping the ones already done.

A step is either external command(s) (two are piped, e.g. vspipe | x264) or a
Python call. Its fingerprint covers the commands, an extra key (e.g. the script
text) and the size and mtime of its input files. A rerun skips a step whose
fingerprint matches the last finished run and whose outputs still exist: that is
how a job resumes after a crash or a cancel, and why changing a subtitle flag
only redoes the mux.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import subprocess
import threading
import time

from videoforge.core.execute import process
from videoforge.core.execute.process import CancelToken, LogFn, ToolError
from videoforge.core.job import StepRecord, StepRun, StepStatus
from videoforge.core.video.encoders import (
    progress as encoder_progress,
    progress_line as encoder_progress_line,
    rate as encoder_rate,
)

Runner = Callable[[Sequence[Sequence[str]], LogFn, CancelToken | None], None]
_MKV_PROGRESS = re.compile(r"Progress:\s*(\d+)%")
# Source filters indexing: L-SMASH "Creating lwi index file 45%", BestSource "track #0 index progress 45%"
_INDEX_PROGRESS = re.compile(r"index (?:file|progress) (\d+)%")
# Lines that only say how far a step is (indexers, mkvmerge): logged at every 10% (the progress bar sees them all).
# The encoders', vspipe's and qaac's (one every frame or two) are logged at every 1% of the step: a long encode's
# would push the job's first lines out of its log.
_THIN_PROGRESS = re.compile(r"(?:index (?:file|progress)|(?:^|\] )Progress:)\s*(\d+)%")


@dataclass(frozen=True, slots=True)
class Step:
    id: str  # unique in a job: "index", "video.pass1", "audio.2", "mux"
    label: str
    argvs: tuple[tuple[str, ...], ...] = ()
    call: Callable[[LogFn], None] | None = None  # instead of argvs
    outputs: tuple[Path, ...] = ()  # the finished files; reuse needs them
    writes: tuple[Path, ...] | None = None  # what the commands write, if not the outputs (e.g. a .partial)
    inputs: tuple[Path, ...] = ()  # their size and mtime go into the fingerprint
    key: str = ""  # anything else the result depends on
    weight: float = 1.0  # share of the job's progress bar
    finalize: Callable[[], object] | None = None  # after success, e.g. move a .partial into place
    present: Callable[[], bool] | None = None  # reuse needs it true too: a result whose file name the tool picks
    background: bool = False  # may run alongside the steps after it (run_steps' parallel)
    # The step as it stands when its turn comes: a command built from an earlier step's output (a FEL encode's
    # HDR10 values come from the RPU the job extracts first). run_steps calls it before the reuse check.
    refresh: Callable[[], Step] | None = None

    @property
    def written(self) -> tuple[Path, ...]:
        return self.outputs if self.writes is None else self.writes

    @property
    def command_line(self) -> str:
        """The command(s) as one line a shell would take; "" for a Python step."""
        return " | ".join(subprocess.list2cmdline(a) for a in self.argvs)

    def to_run(self) -> StepRun:
        return StepRun(self.id, self.label, self.command_line)

    def fingerprint(self) -> str:
        stats = []
        for p in self.inputs:
            try:
                st = p.stat()
                stats.append([str(p), st.st_size, st.st_mtime_ns])
            except OSError:
                stats.append([str(p), None, None])
        doc = json.dumps([self.id, self.argvs, self.key, stats], default=str)
        return hashlib.sha1(doc.encode("utf-8"), usedforsecurity=False).hexdigest()


@dataclass(frozen=True, slots=True)
class StepProgress:
    index: int  # 0-based
    total: int
    step: Step
    fraction: float  # of this step, 0..1
    overall: float  # of the job, 0..1
    reused: bool = False
    fps: float | None = None  # this step's encoder (or vspipe), when it prints one
    eta: int | None = None  # seconds left in this step, by the encoder's own count


ProgressFn = Callable[[StepProgress], None]


def line_progress(line: str) -> float | None:
    """Fraction done from one tool output line: encoders, vspipe, mkvmerge, qaac."""
    frac = encoder_progress(line)
    if frac is None and (m := _MKV_PROGRESS.search(line) or _INDEX_PROGRESS.search(line)):
        frac = int(m.group(1)) / 100
    return frac


def _present(step: Step) -> bool:
    return all(p.exists() for p in step.outputs) and (step.present is None or step.present())


def _reusable(step: Step, record: StepRecord | None) -> bool:
    return record is not None and record.fingerprint == step.fingerprint() and _present(step)


def run_steps(
    steps: Sequence[Step],
    records: dict[str, StepRecord],
    *,
    log: LogFn,
    cancel: CancelToken | None = None,
    progress: ProgressFn | None = None,
    on_record: Callable[[StepRecord], None] | None = None,
    runner: Runner = process.run,
    runs: list[StepRun] | None = None,
    on_step: Callable[[StepRun], None] | None = None,
    step_log: Callable[[StepRun, str], None] | None = None,
    parallel: int = 0,
    keep: Collection[str] = (),
) -> None:
    """Run the steps in order. records: the job's last finished steps, updated in place.
    runs: one StepRun per step (default: fresh ones), updated as each step starts, ends or fails;
    on_step hears every change. A step's output lines go to step_log (default: log).

    With parallel > 0, background steps (the audio encodes) run on up to that many threads while the
    steps after them go on; a step that reads a background step's outputs waits for it, and all are done
    before this returns. A step that fails stops the others. Callbacks may then come from several threads,
    one at a time. keep: step ids the user chose to reuse whatever their fingerprint (their outputs must be
    there); they get a record with today's fingerprint. Raises ToolError (a step failed or didn't write its
    outputs) or Cancelled."""
    steps = list(steps)  # refresh() replaces a step
    total_weight = sum(s.weight for s in steps) or 1.0
    runs = runs if runs is not None else [s.to_run() for s in steps]
    lock = threading.RLock()  # the records, the runs and the callbacks, between a step and the background
    stop = CancelToken(cancel)  # also set when a step fails, so the others end
    done_weight = 0.0
    partial: dict[int, float] = {}  # the running steps' fractions
    rates: dict[int, tuple[float | None, int | None]] = {}  # the running steps' last fps and eta
    lead: int | None = None  # the running foreground step: progress names it while background steps run too

    def note_rate(i: int, line: str) -> None:
        fps, eta = encoder_rate(line)
        if fps is not None or eta is not None:
            with lock:
                old = rates.get(i, (None, None))
                rates[i] = (old[0] if fps is None else fps, old[1] if eta is None else eta)

    def report(i: int, frac: float, reused: bool = False) -> None:
        if not progress:
            return
        with lock:
            partial[i] = frac
            overall = (done_weight + sum(steps[j].weight * f for j, f in partial.items())) / total_weight
            shown = i if lead is None else lead
            # the lead may not have reported yet (it is set just before its step starts)
            shown_frac = partial.get(shown, 0.0)
            fps, eta = rates.get(shown, (None, None))
            progress(
                StepProgress(shown, len(steps), steps[shown], shown_frac, overall, reused and shown == i, fps, eta)
            )

    def finished(i: int) -> None:
        nonlocal done_weight
        with lock:
            partial.pop(i, None)
            rates.pop(i, None)
            done_weight += steps[i].weight

    def changed(run: StepRun) -> None:
        if on_step:
            with lock:
                on_step(run)

    def execute(i: int) -> None:
        step, run = steps[i], runs[i]
        with lock:
            run.status, run.exit_code, run.error, run.tail = StepStatus.RUNNING, None, "", []
            records.pop(step.id, None)
        changed(run)
        log(f"== {i + 1}/{len(steps)} {step.label}")
        report(i, 0.0)
        started = time.monotonic() - stop.paused_seconds

        def spent() -> float:  # a pause is no time spent
            return time.monotonic() - stop.paused_seconds - started

        def out(line: str) -> None:
            run.log(line)
            if step_log is not None:
                step_log(run, line)
            else:
                log(line)

        try:
            for path in step.written:  # a stale file from an earlier run must not pass for this one's
                path.unlink(missing_ok=True)
            if step.call is not None:
                step.call(out)
            else:
                last = -1.0
                latest = 0.0  # the step's last fraction read, for an x265 line that has none of its own
                shown: dict[str, int] = {}  # per tool: the last tenth (or hundredth) of a progress line logged

                def tool_log(line: str) -> None:
                    nonlocal last, latest
                    frac = line_progress(line)
                    if frac is not None:
                        latest = frac
                    mark = None
                    if m := _THIN_PROGRESS.search(line):
                        mark = int(m.group(1)) // 10
                    elif encoder_progress_line(line):
                        mark = int(latest * 100)
                    tool = line.partition("]")[0]
                    if mark is None or mark > shown.get(tool, -1):
                        out(line)
                        if mark is not None:
                            shown[tool] = mark
                    if frac is not None or mark is not None:
                        # every progress line's: vspipe reads ahead, so the encoder's lines rarely move the
                        # fraction (ffmpeg's never do: "frame= 123 fps= 24")
                        note_rate(i, line)
                    if frac is not None and frac - last >= 0.002:  # throttle progress events
                        last = frac
                        report(i, min(frac, 1.0))

                runner(step.argvs, tool_log, stop)
            for path in step.written:
                if not path.exists():
                    raise ToolError(f"{step.label}: {path.name} was not written")
            if step.finalize is not None:
                step.finalize()
            for path in step.outputs:
                if not path.exists():
                    raise ToolError(f"{step.label}: {path.name} is missing")
        except process.Cancelled:
            run.status, run.seconds = StepStatus.CANCELLED, round(spent(), 1)
            changed(run)
            raise
        except Exception as e:
            run.status, run.seconds = StepStatus.FAILED, round(spent(), 1)
            run.error, run.exit_code = str(e) or type(e).__name__, getattr(e, "returncode", None)
            changed(run)
            raise
        record = StepRecord(step.id, step.fingerprint(), list(step.outputs), round(spent(), 1))
        with lock:
            records[step.id] = record
            if on_record:
                on_record(record)
            run.status, run.seconds = StepStatus.DONE, record.seconds
            run.exit_code = 0 if step.argvs else None
        changed(run)
        report(i, 1.0)
        finished(i)

    def reused(i: int) -> bool:
        """Refresh step i, then reuse it if an earlier run did it: True when it did."""
        step, run = steps[i], runs[i]
        if step.refresh is not None:
            step = step.refresh()
            with lock:
                steps[i] = step
            if run.command != step.command_line:
                run.command = step.command_line
                changed(run)
        with lock:
            prior = records.get(step.id)
            if step.id in keep and not _reusable(step, prior) and _present(step):
                prior = StepRecord(step.id, step.fingerprint(), list(step.outputs), prior.seconds if prior else 0.0)
                records[step.id] = prior
                if on_record:
                    on_record(prior)
        if prior is None or not _reusable(step, prior):
            return False
        log(f"== {i + 1}/{len(steps)} {step.label}: done in an earlier run, reused")
        run.status, run.seconds = StepStatus.REUSED, prior.seconds
        changed(run)
        report(i, 1.0, reused=True)
        finished(i)
        return True

    def background(i: int, after: list[Future[None]]) -> None:
        if stop.cancelled:  # never started: it stays pending
            return
        try:
            # The background steps it reads: submitted before it, so they hold a thread or are done (no deadlock).
            for f in after:
                f.result()
            if not stop.cancelled and not reused(i):
                execute(i)
        except BaseException:
            stop.cancel()
            raise

    pool = ThreadPoolExecutor(parallel, "step") if parallel > 0 and any(s.background for s in steps) else None
    pending: dict[int, Future[None]] = {}  # background steps started (or waiting for a thread)
    try:
        for i, step in enumerate(steps):
            reads = [j for j in pending if set(steps[j].outputs) & set(step.inputs)]
            if pool is not None and step.background:
                # Refreshed and checked for reuse on its thread, once what it reads is done: a measure step
                # beside the video doesn't hold up the video.
                pending[i] = pool.submit(background, i, [pending[j] for j in reads])
                continue
            for j in reads:
                pending.pop(j).result()  # raises what stopped it
            if reused(i):
                continue
            if stop.cancelled:
                raise process.Cancelled()
            lead = i
            try:
                execute(i)
            finally:
                lead = None
        for j in list(pending):
            pending.pop(j).result()
    except BaseException as e:
        stop.cancel()
        if pool is not None:
            pool.shutdown(wait=True, cancel_futures=True)
        # A step stopped because another one failed: the job failed with that one's error.
        errors = [f.exception() for f in pending.values() if not f.cancelled()]
        failure = next((x for x in errors if x is not None and not isinstance(x, process.Cancelled)), None)
        if isinstance(e, process.Cancelled) and failure is not None:
            raise failure from None
        raise
    finally:
        if pool is not None:
            pool.shutdown(wait=True)
