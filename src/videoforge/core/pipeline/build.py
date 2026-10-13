"""A job's steps from its spec and plan.

    script -> index -> chapters/qpf -> video (1 or 2 passes) -> audio encodes -> mux

Everything is written into the job's work folder except the mux, which writes
<output>.partial and moves it into place when it is complete. A job that reuses
an existing encode has no script/index/chapters/video steps.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from videoforge.core.config import AppConfig
from videoforge.core.execute.audio import audio_command
from videoforge.core.execute.mux import MUXERS, frame_rate
from videoforge.core.execute.process import LogFn, ToolError
from videoforge.core.job import JobSpec
from videoforge.core.models import Plan
from videoforge.core.pipeline.steps import Step
from videoforge.core.video.encoders import encoder_command, vspipe_command
from videoforge.core.video.qpf import make_qpf, qpf_paths
from videoforge.core.video.script import build_script
from videoforge.core.video.settings import Encoder

if TYPE_CHECKING:
    from videoforge.core.profile import Profile


@dataclass(slots=True)
class JobSteps:
    steps: list[Step]
    output: Path
    encoded_audio: dict[int, Path] = field(default_factory=dict)  # plan.audio position -> file


def output_path(plan: Plan, out_dir: Path, profile: Profile) -> Path:
    return out_dir / (profile.output_stem(plan) + MUXERS[profile.container].extension)


def video_steps(spec: JobSpec, plan: Plan, app: AppConfig) -> list[Step]:
    work, source, enc = spec.work_dir, spec.inputs.source, spec.encoder
    text = build_script(spec.video, source, work, depth=enc.depth)
    script = work / "video.vpy"

    def write_script(_log: LogFn) -> None:
        script.write_text(text, encoding="utf-8")

    steps = [
        Step("script", "Write the VapourSynth script", call=write_script, outputs=(script,), key=text, weight=0.01),
        # Opening the script makes the source filter build its index (minutes on a big remux).
        Step("index", "Index the source", argvs=((app.tools.vspipe, "--info", str(script), "-"),),
             inputs=(source, script), weight=2),
    ]
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

        steps.append(Step("chapters", "Chapters and qpfile (AutoQPF)", call=make_chapters,
                          outputs=(files.qpfile, files.chapters), inputs=(source,), key=str(fps), weight=0.1))
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
            Step("video.pass1", f"Video pass 1/2 ({name})", argvs=(pipe, tuple(first)), outputs=(stats,),
                 inputs=shared, key=text, weight=40),
            Step("video.pass2", f"Video pass 2/2 ({name})", argvs=(pipe, tuple(second)), outputs=(out,),
                 inputs=(*shared, stats), key=text, weight=60),
        ]
    else:
        argv = encoder_command(exe, enc, output=out, qpfile=qpfile)
        steps.append(Step("video", f"Video ({name})", argvs=(pipe, tuple(argv)), outputs=(out,), inputs=shared,
                          key=text, weight=60))
    return steps


def build_steps(spec: JobSpec, plan: Plan, profile: Profile, app: AppConfig, output: Path) -> JobSteps:
    if plan.source.path is None:
        raise ToolError("The plan has no source file")
    work = spec.work_dir
    steps = video_steps(spec, plan, app) if spec.encodes_video else []

    settings = profile.audio_settings()
    encoded: dict[int, Path] = {}
    for pos, a in enumerate(plan.audio):
        cmd = audio_command(a, pos, plan.source.path, work, settings, app.tools)
        if cmd is None:
            continue
        encoded[pos] = cmd.output
        steps.append(Step(f"audio.{pos + 1}", f"Encode audio {pos + 1}: {a.title}", argvs=cmd.argvs,
                          outputs=(cmd.output,), inputs=(plan.source.path,), weight=4))

    partial = output.with_name(output.name + ".partial")
    mux = MUXERS[profile.container].command(plan, encoded, partial, app)
    mux_inputs = [p for p in (plan.encode_path, plan.chapters_path, *encoded.values()) if p is not None]
    mux_inputs += [s.source.external_path for s in plan.subs if s.source.external_path is not None]
    steps.append(Step("mux", "Mux", argvs=(tuple(mux),), outputs=(output,), writes=(partial,),
                      inputs=(plan.source.path, *mux_inputs), finalize=lambda: partial.replace(output), weight=3))
    return JobSteps(steps, output, encoded)
