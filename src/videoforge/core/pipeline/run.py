"""Run one job end to end: its steps (resuming past finished ones), then the profile's checks.

UI-free: progress, log lines and cancel come in as callables/tokens, so the
server's queue worker and the CLI drive the same code.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
import os
from pathlib import Path
import time
from typing import TYPE_CHECKING
import uuid

from videoforge.core.config import AppConfig
from videoforge.core.execute import process
from videoforge.core.execute.process import Cancelled, CancelToken, LogFn, ToolError
from videoforge.core.job import JobResult, JobSpec, JobState, JobStatus, OutputPolicy, StepRecord, StepRun, StepStatus
from videoforge.core.models import JobInputs, Plan, Severity, SourceInfo
from videoforge.core.pipeline.build import build_steps, output_path
from videoforge.core.pipeline.steps import ProgressFn, Runner, run_steps
from videoforge.core.probe import probe
from videoforge.core.tools import tool_issues
from videoforge.core.video import hdr, info
from videoforge.core.workdir import note_finished

if TYPE_CHECKING:
    from videoforge.core.profile import Profile

Prober = Callable[[Path, str], SourceInfo]


class _InvalidOutput(Exception):
    pass


def _identity(path: Path) -> tuple[int, int, int] | None:
    try:
        stat = path.stat()
        return stat.st_size, stat.st_mtime_ns, stat.st_ino
    except FileNotFoundError:
        return None


def missing_inputs(spec: JobSpec) -> list[Path]:
    """The user's input files that aren't there (generated files are the steps' business)."""
    i = spec.inputs
    paths = [i.source, i.encode, i.chapters, *i.subtitles]
    return [p for p in paths if p is not None and not p.exists()]


def run_job(
    spec: JobSpec,
    plan: Plan,
    profile: Profile,
    app: AppConfig,
    *,
    state: JobState | None = None,
    log: LogFn | None = None,
    cancel: CancelToken | None = None,
    progress: ProgressFn | None = None,
    on_record: Callable[[StepRecord], None] | None = None,
    on_step: Callable[[StepRun], None] | None = None,
    step_log: Callable[[StepRun, str], None] | None = None,
    runner: Runner = process.run,
    prober: Prober = probe,
) -> JobResult:
    """state.steps (the finished steps of earlier runs) is read and updated; state.run is this
    run's steps (the pipeline's, then Validate), and on_step hears each change to one of them
    (first every step as pending). A step's output lines go to step_log (default: log); with
    app.parallel_audio, audio encodes run alongside the video, so callbacks come from more than
    one thread (one at a time). state.keep (steps to reuse whatever their fingerprint) is used up. Each
    finished step's files are noted in the work folder (note_finished), for other jobs on the source.
    The rest of state is set from the result."""
    state = state if state is not None else JobState()
    state.run = []
    log = log or (lambda _line: None)
    on_step = on_step or (lambda _run: None)
    result = _run(spec, plan, profile, app, state, log, cancel, progress, on_record, on_step, step_log, runner, prober)
    state.status, state.output, state.issues, state.error = result.status, result.output, result.issues, result.error
    return result


def _failed_step(state: JobState, error: str) -> str:
    """The error, led by the step it happened in (1-based, of all steps)."""
    ordered = list(enumerate(state.run, 1))
    if state.run and state.run[-1].id == "validate" and state.run[-1].status is StepStatus.FAILED:
        ordered.reverse()
    for n, r in ordered:
        if r.status in (StepStatus.FAILED, StepStatus.RUNNING):
            where = f"Step {n}/{len(state.run)} · {r.label}"
            return f"{where}: {error.removeprefix(r.label + ': ')}"
    return error


def _run(
    spec, plan, profile, app, state, log, cancel, progress, on_record, on_step, step_log, runner, prober
) -> JobResult:
    if plan.blocked:
        reasons = "; ".join(i.message for i in plan.issues if i.severity is Severity.BLOCK)
        return JobResult(plan, JobStatus.SKIPPED, error=reasons)
    missing = missing_inputs(spec)
    if missing:
        return JobResult(plan, JobStatus.FAILED, error="Missing input: " + ", ".join(str(p) for p in missing))
    if no_tools := tool_issues(plan, app.tools, spec.container(profile)):  # a plan made before a tool went missing
        return JobResult(plan, JobStatus.FAILED, error="; ".join(i.message for i in no_tools))
    if spec.output_dir is None:
        return JobResult(plan, JobStatus.FAILED, error="No output folder set")
    output = output_path(spec, plan, profile, spec.output_dir)
    if output.resolve() == spec.inputs.source.resolve():
        return JobResult(plan, JobStatus.FAILED, error=f"Output would overwrite the source: {output}")

    work = spec.work_dir
    encoded: dict[int, Path] = {}
    rejected: Path | None = None
    validate = StepRun("validate", "Validate")
    issues = []

    def result(status: JobStatus, **kw) -> JobResult:
        return JobResult(plan, status, work_dir=work, encoded_audio=encoded, **kw)

    try:
        original = _identity(output)
        own = state.steps.get("mux")
        owned = own is not None and own.outputs_match([output])
        if original is not None and not owned:
            if spec.output_policy is OutputPolicy.STOP:
                return result(
                    JobStatus.FAILED,
                    error=f"Output already exists: {output}. Choose Skip, Rename or Replace in Output.",
                )
            if spec.output_policy is OutputPolicy.SKIP:
                return result(JobStatus.SKIPPED, error=f"Kept existing output: {output}")
            if spec.output_policy is OutputPolicy.RENAME:
                base = output
                number = 2
                while output.exists():
                    output = base.with_name(f"{base.stem}.{number}{base.suffix}")
                    number += 1
                original = None

        def validate_output(path: Path) -> None:
            nonlocal issues
            validate.status = StepStatus.RUNNING
            on_step(validate)
            log("== Validate")
            started = time.monotonic()
            # Probe temporary bytes, but validate the intended container/name (e.g. MP4, not .partial).
            found = replace(prober(path, app.tools.mkvmerge), path=output, name=output.name)
            issues = profile.validate_output(plan, found)
            if spec.encodes_video:
                issues += hdr.output_issues(plan.source.video, spec.encoder, found)
                issues += info.length_issues(plan.source.video, info.read(work / info.SCRIPT_INFO))
            blocking = [i.message for i in issues if i.severity is Severity.BLOCK]
            for issue in issues:
                validate.log(f"{issue.severity.value}: {issue.message}")
            validate.status = StepStatus.FAILED if blocking else StepStatus.DONE
            validate.error, validate.seconds = "; ".join(blocking), round(time.monotonic() - started, 1)
            on_step(validate)
            if blocking:
                raise _InvalidOutput(validate.error)

        def publish(candidate: Path, target: Path) -> None:
            nonlocal rejected
            try:
                validate_output(candidate)
                if _identity(target) != original:
                    raise OSError(f"Output changed during the run; kept the existing file: {target}")
                if original is None:
                    # An exclusive publication: even a file appearing after the check cannot be overwritten.
                    if os.name == "nt":
                        candidate.rename(target)  # Windows rename refuses an existing target
                    else:
                        os.link(candidate, target)
                        candidate.unlink()
                else:
                    candidate.replace(target)
            except Exception:
                if candidate.exists():
                    rejected = target.with_name(f"{target.stem}.unpublished-{uuid.uuid4().hex[:8]}{target.suffix}")
                    candidate.rename(rejected)
                    log(f"Unpublished output kept for inspection: {rejected}")
                raise

        built = build_steps(spec, plan, profile, app, output, publish=publish)
        encoded = built.encoded_audio
        state.run = [s.to_run() for s in built.steps] + [validate]
        for r in state.run:
            on_step(r)
        work.mkdir(parents=True, exist_ok=True)
        output.parent.mkdir(parents=True, exist_ok=True)

        def finished(record: StepRecord) -> None:
            note_finished(work, record.id, record.fingerprint, record.outputs, record.seconds)
            if on_record:
                on_record(record)

        keep, state.keep = state.keep, []
        run_steps(
            built.steps,
            state.steps,
            log=log,
            cancel=cancel,
            progress=progress,
            on_record=finished,
            runner=runner,
            runs=state.run[:-1],
            on_step=on_step,
            step_log=step_log,
            parallel=app.parallel_audio,
            keep=keep,
        )
        if validate.status is StepStatus.PENDING:  # the final file itself was reused
            validate_output(output)
        return result(JobStatus.DONE, output=output, issues=issues)
    except _InvalidOutput:
        return result(JobStatus.INVALID, output=rejected or output, issues=issues, error=validate.error)
    except Cancelled:
        return result(JobStatus.CANCELLED, error="Cancelled")
    except (ToolError, OSError, ValueError) as e:
        for r in state.run:  # a step that raised outside run_steps (Validate's probe)
            if r.status is StepStatus.RUNNING:
                r.status, r.error = StepStatus.FAILED, str(e)
                on_step(r)
        return result(JobStatus.FAILED, output=rejected, error=_failed_step(state, str(e)))
    finally:
        output.with_name(output.name + ".partial").unlink(missing_ok=True)


def spec_from_plan(plan: Plan, out_dir: Path) -> JobSpec:
    """A job for a plan.json entry: it reuses the plan's encode (no video steps)."""
    inputs = plan.inputs
    if inputs is None:
        if plan.source.path is None:
            raise ValueError("The plan has no source file")
        inputs = JobInputs(
            plan.source.path,
            plan.encode_path,
            [s.source.external_path for s in plan.subs if s.source.external_path],
            plan.chapters_path,
        )
    return JobSpec(inputs=inputs, profile=plan.profile, overrides=plan.overrides, output_dir=out_dir)


def run_plan(
    plan: Plan,
    out_dir: Path,
    profile: Profile,
    app: AppConfig,
    *,
    output_policy: OutputPolicy = OutputPolicy.STOP,
    **kwargs,
) -> JobResult:
    """Run a ready-made plan (plan.json; the encode already exists)."""
    spec = spec_from_plan(plan, out_dir)
    spec.output_policy = output_policy
    return run_job(spec, plan, profile, app, **kwargs)
