"""Run one job end to end: its steps (resuming past finished ones), then the profile's checks.

UI-free: progress, log lines and cancel come in as callables/tokens, so the
server's queue worker and the CLI drive the same code.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from videoforge.core.config import AppConfig
from videoforge.core.execute import process
from videoforge.core.execute.process import Cancelled, CancelToken, LogFn, ToolError
from videoforge.core.job import JobResult, JobSpec, JobState, JobStatus, StepRecord, StepRun, StepStatus
from videoforge.core.models import JobInputs, Plan, Severity, SourceInfo
from videoforge.core.pipeline.build import build_steps, output_path
from videoforge.core.pipeline.steps import ProgressFn, Runner, run_steps
from videoforge.core.probe import probe
from videoforge.core.tools import tool_issues

if TYPE_CHECKING:
    from videoforge.core.profile import Profile

Prober = Callable[[Path, str], SourceInfo]


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
    runner: Runner = process.run,
    prober: Prober = probe,
) -> JobResult:
    """state.steps (the finished steps of earlier runs) is read and updated; state.run is this
    run's steps (the pipeline's, then Validate), and on_step hears each change to one of them
    (first every step as pending). The rest of state is set from the result."""
    state = state if state is not None else JobState()
    state.run = []
    log = log or (lambda _line: None)
    on_step = on_step or (lambda _run: None)
    result = _run(spec, plan, profile, app, state, log, cancel, progress, on_record, on_step, runner, prober)
    state.status, state.output, state.issues, state.error = result.status, result.output, result.issues, result.error
    return result


def _failed_step(state: JobState, error: str) -> str:
    """The error, led by the step it happened in (1-based, of all steps)."""
    for n, r in enumerate(state.run, 1):
        if r.status in (StepStatus.FAILED, StepStatus.RUNNING):
            where = f"Step {n}/{len(state.run)} · {r.label}"
            return f"{where}: {error.removeprefix(r.label + ': ')}"
    return error


def _run(spec, plan, profile, app, state, log, cancel, progress, on_record, on_step, runner, prober) -> JobResult:
    if plan.blocked:
        reasons = "; ".join(i.message for i in plan.issues if i.severity is Severity.BLOCK)
        return JobResult(plan, JobStatus.SKIPPED, error=reasons)
    missing = missing_inputs(spec)
    if missing:
        return JobResult(plan, JobStatus.FAILED, error="Missing input: " + ", ".join(str(p) for p in missing))
    if no_tools := tool_issues(plan, app.tools):  # a plan made before a tool went missing
        return JobResult(plan, JobStatus.FAILED, error="; ".join(i.message for i in no_tools))
    if spec.output_dir is None:
        return JobResult(plan, JobStatus.FAILED, error="No output folder set")
    output = output_path(plan, spec.output_dir, profile)
    if output.resolve() == spec.inputs.source.resolve():
        return JobResult(plan, JobStatus.FAILED, error=f"Output would overwrite the source: {output}")

    work = spec.work_dir
    encoded: dict[int, Path] = {}

    def result(status: JobStatus, **kw) -> JobResult:
        return JobResult(plan, status, work_dir=work, encoded_audio=encoded, **kw)

    try:
        built = build_steps(spec, plan, profile, app, output)
        encoded = built.encoded_audio
        validate = StepRun("validate", "Validate")
        state.run = [s.to_run() for s in built.steps] + [validate]
        for r in state.run:
            on_step(r)
        work.mkdir(parents=True, exist_ok=True)
        output.parent.mkdir(parents=True, exist_ok=True)
        run_steps(built.steps, state.steps, log=log, cancel=cancel, progress=progress, on_record=on_record,
                  runner=runner, runs=state.run[:-1], on_step=on_step)
        validate.status = StepStatus.RUNNING
        on_step(validate)
        log("== Validate")
        started = time.monotonic()
        issues = profile.validate_output(plan, prober(output, app.tools.mkvmerge))
        blocking = [i.message for i in issues if i.severity is Severity.BLOCK]
        for i in issues:
            validate.log(f"{i.severity.value}: {i.message}")
        validate.status = StepStatus.FAILED if blocking else StepStatus.DONE
        validate.error, validate.seconds = "; ".join(blocking), round(time.monotonic() - started, 1)
        on_step(validate)
        return result(JobStatus.INVALID if blocking else JobStatus.DONE, output=output, issues=issues)
    except Cancelled:
        return result(JobStatus.CANCELLED, error="Cancelled")
    except (ToolError, OSError, ValueError) as e:
        for r in state.run:  # a step that raised outside run_steps (Validate's probe)
            if r.status is StepStatus.RUNNING:
                r.status, r.error = StepStatus.FAILED, str(e)
                on_step(r)
        return result(JobStatus.FAILED, error=_failed_step(state, str(e)))
    finally:
        output.with_name(output.name + ".partial").unlink(missing_ok=True)


def spec_from_plan(plan: Plan, out_dir: Path) -> JobSpec:
    """A job for a plan.json entry: it reuses the plan's encode (no video steps)."""
    inputs = plan.inputs
    if inputs is None:
        if plan.source.path is None:
            raise ValueError("The plan has no source file")
        inputs = JobInputs(plan.source.path, plan.encode_path,
                           [s.source.external_path for s in plan.subs if s.source.external_path], plan.chapters_path)
    return JobSpec(inputs=inputs, profile=plan.profile, overrides=plan.overrides, output_dir=out_dir)


def run_plan(plan: Plan, out_dir: Path, profile: Profile, app: AppConfig, **kwargs) -> JobResult:
    """Run a ready-made plan (plan.json; the encode already exists)."""
    return run_job(spec_from_plan(plan, out_dir), plan, profile, app, **kwargs)
