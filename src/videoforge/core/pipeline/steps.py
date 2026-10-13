"""Pipeline steps and the loop that runs them, skipping the ones already done.

A step is either external command(s) (two are piped, e.g. vspipe | x264) or a
Python call. Its fingerprint covers the commands, an extra key (e.g. the script
text) and the size and mtime of its input files. A rerun skips a step whose
fingerprint matches the last finished run and whose outputs still exist: that is
how a job resumes after a crash or a cancel, and why changing a subtitle flag
only redoes the mux.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from videoforge.core.execute import process
from videoforge.core.execute.process import CancelToken, LogFn, ToolError
from videoforge.core.job import StepRecord
from videoforge.core.video.encoders import progress as encoder_progress

Runner = Callable[[Sequence[Sequence[str]], LogFn, CancelToken | None], None]
_MKV_PROGRESS = re.compile(r"Progress:\s*(\d+)%")


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
    finalize: Callable[[], None] | None = None  # after success, e.g. move a .partial into place

    @property
    def written(self) -> tuple[Path, ...]:
        return self.outputs if self.writes is None else self.writes

    def fingerprint(self) -> str:
        stats = []
        for p in self.inputs:
            try:
                st = p.stat()
                stats.append([str(p), st.st_size, st.st_mtime_ns])
            except OSError:
                stats.append([str(p), None, None])
        doc = json.dumps([self.id, self.argvs, self.key, stats], default=str)
        return hashlib.sha1(doc.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class StepProgress:
    index: int  # 0-based
    total: int
    step: Step
    fraction: float  # of this step, 0..1
    overall: float  # of the job, 0..1
    reused: bool = False


ProgressFn = Callable[[StepProgress], None]


def line_progress(line: str) -> float | None:
    """Fraction done from one tool output line: encoders, vspipe, mkvmerge, qaac."""
    frac = encoder_progress(line)
    if frac is None and (m := _MKV_PROGRESS.search(line)):
        frac = int(m.group(1)) / 100
    return frac


def _reusable(step: Step, record: StepRecord | None) -> bool:
    return (
        record is not None
        and record.fingerprint == step.fingerprint()
        and all(p.exists() for p in step.outputs)
    )


def run_steps(
    steps: Sequence[Step],
    records: dict[str, StepRecord],
    *,
    log: LogFn,
    cancel: CancelToken | None = None,
    progress: ProgressFn | None = None,
    on_record: Callable[[StepRecord], None] | None = None,
    runner: Runner = process.run,
) -> None:
    """Run the steps in order. records: the job's last finished steps, updated in place.
    Raises ToolError (a step failed or didn't write its outputs) or Cancelled."""
    total_weight = sum(s.weight for s in steps) or 1.0
    done_weight = 0.0

    def report(i: int, step: Step, frac: float, reused: bool = False) -> None:
        if progress:
            overall = (done_weight + step.weight * frac) / total_weight
            progress(StepProgress(i, len(steps), step, frac, overall, reused))

    for i, step in enumerate(steps):
        if _reusable(step, records.get(step.id)):
            log(f"== {i + 1}/{len(steps)} {step.label}: done in an earlier run, reused")
            report(i, step, 1.0, reused=True)
            done_weight += step.weight
            continue
        if cancel is not None and cancel.cancelled:
            raise process.Cancelled()
        log(f"== {i + 1}/{len(steps)} {step.label}")
        report(i, step, 0.0)
        records.pop(step.id, None)
        for out in step.written:  # a stale file from an earlier run must not pass for this one's
            out.unlink(missing_ok=True)
        started = time.monotonic()
        if step.call is not None:
            step.call(log)
        else:
            last = [-1.0]

            def tool_log(line: str, i: int = i, step: Step = step, last: list[float] = last) -> None:
                log(line)
                frac = line_progress(line)
                if frac is not None and frac - last[0] >= 0.002:  # throttle progress events
                    last[0] = frac
                    report(i, step, min(frac, 1.0))

            runner(step.argvs, tool_log, cancel)
        for out in step.written:
            if not out.exists():
                raise ToolError(f"{step.label}: {out.name} was not written")
        if step.finalize is not None:
            step.finalize()
        for out in step.outputs:
            if not out.exists():
                raise ToolError(f"{step.label}: {out.name} is missing")
        record = StepRecord(step.id, step.fingerprint(), list(step.outputs), round(time.monotonic() - started, 1))
        records[step.id] = record
        if on_record:
            on_record(record)
        report(i, step, 1.0)
        done_weight += step.weight
