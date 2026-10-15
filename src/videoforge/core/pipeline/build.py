"""A job's steps from its spec and plan.

    script -> index -> chapters/qpf -> video (1 or 2 passes) -> audio encodes -> mux

Everything is written into the job's work folder except the mux, which writes
<output>.partial and moves it into place when it is complete. A job that reuses
an existing encode has no script/index/chapters/video steps.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import os
from pathlib import Path
import sys
from typing import TYPE_CHECKING

from videoforge.core.config import AppConfig
from videoforge.core.execute import chapters as ogm
from videoforge.core.execute.audio import audio_command
from videoforge.core.execute.mux import MUXERS, frame_rate, split_args
from videoforge.core.execute.process import LogFn, ToolError
from videoforge.core.job import JobSpec
from videoforge.core.models import Plan
from videoforge.core.pipeline.steps import Step
from videoforge.core.video.encoders import encoder_command, vspipe_command
from videoforge.core.video.qpf import make_qpf, qpf_paths
from videoforge.core.video.script import build_script, ffms2_index, index_exists
from videoforge.core.video.settings import Encoder, SourceFilter

if TYPE_CHECKING:
    from videoforge.core.profile import Profile


@dataclass(slots=True)
class JobSteps:
    steps: list[Step]
    output: Path
    encoded_audio: dict[int, Path] = field(default_factory=dict)  # plan.audio position -> file


def output_path(plan: Plan, out_dir: Path, profile: Profile, container: str | None = None, label: str = "") -> Path:
    """The profile's name for the output, with the job's label (if any) after it: `<stem>.<label>.mkv`."""
    stem = profile.output_stem(plan) + (f".{label}" if label else "")
    return out_dir / (stem + MUXERS[container or profile.container].extension)


def job_output(spec: JobSpec, plan: Plan, profile: Profile) -> Path | None:
    """The file a job writes; None without an output folder."""
    if spec.output_dir is None:
        return None
    return output_path(plan, spec.output_dir, profile, spec.container(profile), spec.label)


def mp4_chapters_step(plan: Plan, work: Path) -> Step | None:
    """MP4Box takes OGM text only: a chapter XML, or the source's own chapters (mkvmerge carries
    those by itself), become chapters_mp4.txt in the work folder. None when there's nothing to convert."""
    given = plan.chapters_path
    if given is not None and given.suffix.lower() != ".xml":
        return None
    if given is None and not plan.source.has_chapters:
        return None
    src = given or plan.source.path
    if src is None:  # has_chapters says the source has a path
        raise ValueError("No chapters to convert")
    out = work / "chapters_mp4.txt"

    def convert(log: LogFn) -> None:
        found = ogm.from_xml(src) if given is not None else ogm.from_source(src)
        if not found:
            raise ToolError(f"No chapters could be read from {src.name}")
        out.write_text(ogm.ogm_text(found), encoding="utf-8")
        log(f"{len(found)} chapters written for MP4Box")

    return Step("chapters.mp4", "Chapters for MP4", call=convert, outputs=(out,), inputs=(src,), weight=0.05)


def index_steps(spec: JobSpec, app: AppConfig) -> list[Step]:
    """Write the script and index the source: a job's first steps, and all a batch index runs."""
    work, source = spec.work_dir, spec.inputs.source
    text = build_script(spec.video, source, work, depth=spec.encoder.depth)
    script = work / "video.vpy"
    source_filter = spec.video.source_filter

    def write_script(_log: LogFn) -> None:
        script.write_text(text, encoding="utf-8")

    if source_filter is SourceFilter.FFMS2:
        # FFMS2's Source() indexes silently: build its index first, with progress (core/video/ffindex.py).
        # It depends on the source alone, so a crop edit doesn't index again.
        argv = (sys.executable, "-m", "videoforge.core.video.ffindex", str(source), str(ffms2_index(source, work)))
        inputs: tuple[Path, ...] = (source,)
    else:
        # Opening the script makes the source filter build its index (minutes on a big remux).
        argv, inputs = (app.tools.vspipe, "--info", str(script), "-"), (source, script)
    return [
        Step("script", "Write the VapourSynth script", call=write_script, outputs=(script,), key=text, weight=0.01),
        # Reused while the index is there (BestSource names its file after the track).
        Step(
            "index",
            "Index the source",
            argvs=(argv,),
            inputs=inputs,
            key=source_filter.value,
            weight=2,
            present=lambda: index_exists(source, source_filter, work),
        ),
    ]


def video_steps(spec: JobSpec, plan: Plan, app: AppConfig) -> list[Step]:
    work, source, enc = spec.work_dir, spec.inputs.source, spec.encoder
    script = work / "video.vpy"
    text = build_script(spec.video, source, work, depth=enc.depth)
    steps = index_steps(spec, app)
    qpfile = None
    if spec.makes_chapters:
        files = qpf_paths(work)
        video = plan.source.video
        if video is None or not video.default_duration_ns:
            raise ToolError("The source has no frame rate to place chapters by")
        fps = frame_rate(video.default_duration_ns)

        def make_chapters(log: LogFn) -> None:
            if make_qpf(source, work, fps) is None:
                raise ToolError("AutoQPF could not read or generate chapters for the source")
            log(f"Chapters and qpfile written ({fps} fps)")

        steps.append(
            Step(
                "chapters",
                "Chapters and qpfile (AutoQPF)",
                call=make_chapters,
                outputs=(files.qpfile, files.chapters),
                inputs=(source,),
                key=str(fps),
                weight=0.1,
            )
        )
        qpfile = files.qpfile

    exe = app.tools.x265 if enc.encoder is Encoder.X265 else app.tools.x264
    pipe = tuple(vspipe_command(app.tools.vspipe, script))
    shared = (script, source) + ((qpfile,) if qpfile else ())
    out = spec.video_output
    name = enc.encoder.value
    if enc.passes == 2:
        stats = work / "video.stats"
        first = encoder_command(exe, enc, output=Path(os.devnull), pass_number=1, stats=stats, qpfile=qpfile)
        second = encoder_command(exe, enc, output=out, pass_number=2, stats=stats, qpfile=qpfile)
        steps += [
            Step(
                "video.pass1",
                f"Video pass 1/2 ({name})",
                argvs=(pipe, tuple(first)),
                outputs=(stats,),
                inputs=shared,
                key=text,
                weight=40,
            ),
            Step(
                "video.pass2",
                f"Video pass 2/2 ({name})",
                argvs=(pipe, tuple(second)),
                outputs=(out,),
                inputs=(*shared, stats),
                key=text,
                weight=60,
            ),
        ]
    else:
        argv = encoder_command(exe, enc, output=out, qpfile=qpfile)
        steps.append(
            Step(
                "video",
                f"Video ({name})",
                argvs=(pipe, tuple(argv)),
                outputs=(out,),
                inputs=shared,
                key=text,
                weight=60,
            )
        )
    return steps


def build_steps(spec: JobSpec, plan: Plan, profile: Profile, app: AppConfig, output: Path) -> JobSteps:
    if plan.source.path is None:
        raise ToolError("The plan has no source file")
    work = spec.work_dir
    steps = video_steps(spec, plan, app) if spec.encodes_video else []

    settings = profile.audio_settings()
    encoded: dict[int, Path] = {}
    for pos, a in enumerate(plan.audio):
        src = a.source.external_path or plan.source.path  # an added audio file is read from itself
        cmd = audio_command(a, pos, src, work, settings, app.tools)
        if cmd is None:
            continue
        encoded[pos] = cmd.output
        steps.append(
            Step(
                f"audio.{pos + 1}",
                f"Encode audio {pos + 1}: {a.title}",
                argvs=cmd.argvs,
                outputs=(cmd.output,),
                inputs=(src,),
                weight=4,
            )
        )

    container = spec.container(profile)
    if container == "mp4" and (chapters := mp4_chapters_step(plan, work)) is not None:
        steps.append(chapters)
        plan = replace(plan, chapters_path=chapters.outputs[0])
    partial = output.with_name(output.name + ".partial")
    mux = MUXERS[container].command(plan, encoded, partial, app, split_args(spec.mux.extra))
    mux_inputs = [
        p for p in (plan.source.path, plan.encode_path, plan.chapters_path, *encoded.values()) if p is not None
    ]
    mux_inputs += [s.source.external_path for s in plan.subs if s.source.external_path is not None]
    mux_inputs += list(dict.fromkeys(a.source.external_path for a in plan.audio if a.source.external_path is not None))
    steps.append(
        Step(
            "mux",
            "Mux",
            argvs=(tuple(mux),),
            outputs=(output,),
            writes=(partial,),
            inputs=tuple(mux_inputs),
            finalize=lambda: partial.replace(output),
            weight=3,
        )
    )
    return JobSteps(steps, output, encoded)
