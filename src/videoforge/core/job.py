"""A job: what to build (JobSpec, edited in the UI) and what its last run did (JobState).

Both are plain data persisted through plan_io's codec. The Plan (the profile's
audio/subtitle decisions) isn't stored with the spec: it is recomputed from the
probed inputs on every edit.

A job either encodes its own video (VapourSynth + x264/x265 into its work
folder) or reuses an existing encode given in its inputs (e.g. from StaxRip).
For the first kind the planner is handed a *planned* encode: the file the video
steps will write, with the size and frame rate it will have, so the profile's
rules don't need to know where the encode comes from.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from fractions import Fraction
from pathlib import Path
import re
from typing import TYPE_CHECKING
import uuid

from videoforge.core.config import AppConfig, Tools
from videoforge.core.execute.mux import MUXERS, MuxSettings, mux_issues
from videoforge.core.jobs import ProbedInputs, plan_job, probe_inputs
from videoforge.core.models import (
    Issue,
    JobInputs,
    Overrides,
    Plan,
    SourceInfo,
    TemplateAudio,
    TemplateChoice,
    TemplateSubs,
    VideoInfo,
)
from videoforge.core.tools import tool_issues
from videoforge.core.video import hdr
from videoforge.core.video.encoders import output_name
from videoforge.core.video.qpf import qpf_paths
from videoforge.core.video.settings import EncoderSettings, VideoSettings
from videoforge.core.workdir import work_dir

if TYPE_CHECKING:
    from videoforge.core.profile import Profile


class JobStatus(StrEnum):
    """How a run ended."""

    DONE = "done"  # muxed and passes validation
    INVALID = "invalid"  # muxed, but the output fails validation
    FAILED = "failed"  # a tool failed or an input is missing
    SKIPPED = "skipped"  # the plan is blocked
    CANCELLED = "cancelled"


@dataclass(slots=True)
class JobResult:
    plan: Plan
    status: JobStatus
    output: Path | None = None
    issues: list[Issue] = field(default_factory=list)  # validation of the output
    error: str = ""
    work_dir: Path | None = None  # the job's kept working folder
    encoded_audio: dict[int, Path] = field(default_factory=dict)  # plan.audio position -> encode in work_dir


@dataclass(slots=True)
class JobSpec:
    inputs: JobInputs  # inputs.encode set = reuse that encode instead of encoding the video
    profile: str
    overrides: Overrides = field(default_factory=Overrides)  # incl. the original language
    video: VideoSettings = field(default_factory=VideoSettings)
    encoder: EncoderSettings = field(default_factory=EncoderSettings)
    qpf: bool = True  # chapters from AutoQPF (keyframes on chapter starts) unless chapters are given
    output_dir: Path | None = None
    mux: MuxSettings = field(default_factory=MuxSettings)
    # Detect the crop once the source can be read, then clear (a template's auto crop).
    autocrop: bool = False
    # A template's audio, waiting for the source's tracks: then it becomes the job's audio overrides.
    audio_template: TemplateAudio | None = None
    # ... and its subtitle rules, waiting for the source's (and added files') subtitle tracks.
    subs_template: TemplateSubs | None = None
    # What the last template set for the audio / the subtitles (template.template_choice).
    audio_from_template: TemplateChoice | None = None
    subs_from_template: TemplateChoice | None = None
    # The output's file name without its extension; "" = the profile's name for it (the source's).
    output_name: str = ""
    # Tells runs of one source apart (e.g. "dubbed"): added to the output name, and in the job record.
    label: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    @property
    def name(self) -> str:
        return self.inputs.source.name

    @property
    def encodes_video(self) -> bool:
        return self.inputs.encode is None

    @property
    def work_dir(self) -> Path:
        return work_dir(self.inputs.source)

    @property
    def video_output(self) -> Path:
        return self.work_dir / output_name(self.encoder)

    @property
    def makes_chapters(self) -> bool:
        return self.encodes_video and self.qpf and self.inputs.chapters is None

    def container(self, profile: Profile) -> str:
        """The job's container: its own pick when the profile offers it, else the profile's."""
        return self.mux.container if self.mux.container in profile.containers else profile.container


def clean_label(text: str) -> str:
    """A label as it can go into a file name: characters Windows refuses dropped, no dots or spaces at the ends."""
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", text).strip(" .")


def clean_output_name(text: str) -> str:
    """An output name as typed, made a file name; a container's extension typed with it is dropped
    (the job's container adds its own)."""
    name = clean_label(text)
    for ext in {m.extension for m in MUXERS.values()}:
        if name.lower().endswith(ext):
            return clean_label(name[: -len(ext)])
    return name


@dataclass(slots=True)
class StepRecord:
    """A finished pipeline step: a rerun with the same fingerprint and outputs skips it."""

    id: str
    fingerprint: str
    outputs: list[Path] = field(default_factory=list)
    seconds: float = 0.0


class StepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    REUSED = "reused"  # done in an earlier run, skipped
    FAILED = "failed"
    CANCELLED = "cancelled"


STEP_TAIL = 30  # output lines a StepRun keeps (persisted with the job; the full log is videoforge.log)


@dataclass(slots=True)
class StepRun:
    """One step of the last run, as the job's Log tab shows it."""

    id: str
    label: str
    command: str = ""  # the command line; "" = runs inside VideoForge
    status: StepStatus = StepStatus.PENDING
    exit_code: int | None = None
    seconds: float = 0.0
    error: str = ""
    tail: list[str] = field(default_factory=list)  # its last output lines

    def log(self, line: str) -> None:
        self.tail.append(line)
        del self.tail[:-STEP_TAIL]


@dataclass(slots=True)
class JobState:
    steps: dict[str, StepRecord] = field(default_factory=dict)
    run: list[StepRun] = field(default_factory=list)  # the last run's steps, in order
    status: JobStatus | None = None  # of the last run
    output: Path | None = None
    issues: list[Issue] = field(default_factory=list)
    error: str = ""
    keep: list[str] = field(default_factory=list)  # steps the user chose to reuse on the next run (run_steps' keep)


def planned_encode(spec: JobSpec, source: SourceInfo) -> SourceInfo:
    """The encode the video steps will write: cropped/resized size, pixel aspect, the source's frame rate."""
    path = spec.video_output
    v = source.video
    if v is None:
        return SourceInfo(path=path, name=path.name, video=None)
    width, height = spec.video.output_size(v.width, v.height)
    sar = spec.video.output_sar(v.width, v.height, v.sar) or Fraction(1)
    return SourceInfo(
        path=path,
        name=path.name,
        video=VideoInfo(
            width=width,
            height=height,
            default_duration_ns=v.default_duration_ns,
            sar_num=sar.numerator,
            sar_den=sar.denominator,
        ),
    )


def spec_inputs(spec: JobSpec) -> JobInputs:
    """The inputs the planner sees: the user's, plus the chapter file AutoQPF will write."""
    if spec.makes_chapters:
        return replace(spec.inputs, chapters=qpf_paths(spec.work_dir).chapters)
    return spec.inputs


def probe_spec(spec: JobSpec, app: AppConfig) -> ProbedInputs:
    """Probe the source (and a reused encode). Slow on network shares: keep the result."""
    probed = probe_inputs(spec.inputs, app)
    if spec.encodes_video:
        probed = replace(probed, encode=planned_encode(spec, probed.source))
    return replace(probed, inputs=spec_inputs(spec))


def replan(spec: JobSpec, probed: ProbedInputs) -> ProbedInputs:
    """A cached probe brought up to date with the spec's video settings (crop, encoder, chapters)."""
    if spec.encodes_video:
        probed = replace(probed, encode=planned_encode(spec, probed.source))
    return replace(probed, inputs=spec_inputs(spec))


def plan_spec(spec: JobSpec, probed: ProbedInputs, profile: Profile, tools: Tools | None = None) -> Plan:
    """The profile's plan for the job. With tools, an audio encode whose tools are missing blocks it."""
    plan = plan_job(profile, replan(spec, probed), spec.overrides.original_language, spec.overrides)
    plan.inputs = spec.inputs  # what the user gave; generated files aren't inputs
    if tools is not None:
        plan.issues += tool_issues(plan, tools, spec.container(profile))
    plan.issues += mux_issues(plan, spec.container(profile))
    if spec.encodes_video:
        plan.issues += hdr.issues(probed.source.video, spec.encoder, tools)
    return plan
