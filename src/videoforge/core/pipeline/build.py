"""A job's steps from its spec and plan.

    script -> index -> script info -> chapters/qpf -> (VFR) timestamps -> audio encodes -> video (1 or 2 passes)
    -> mux

The script info (vspipe --info) gives the encode's frame rate, which an IVTC or a double-rate deinterlace makes
other than the source's: AutoQPF and the mux read it when their turn comes (Step.refresh). A VFR source's
timestamps (core/video/vfr.py) time an MKV's encode instead, when they fit the script's frame count.

The audio encodes are background steps: with AppConfig.parallel_audio they run alongside the
video encode (after the index, which reads the whole source too), and the mux waits for them. A target size's
second pass waits for them too: its bitrate counts their files (core/video/target.py).

Everything is written into the job's work folder except the mux, which writes
<output>.partial and moves it into place when it is complete. A job that reuses
an existing encode has no script/index/chapters/video steps.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from fractions import Fraction
from functools import partial
import os
from pathlib import Path
import sys
from typing import TYPE_CHECKING

from videoforge.core.config import AppConfig
from videoforge.core.execute import chapters as ogm, loudness
from videoforge.core.execute.audio import audio_command, measure_argv, measure_path, needs_measure
from videoforge.core.execute.mux import MUXERS, frame_rate, split_args
from videoforge.core.execute.process import LogFn, ToolError
from videoforge.core.job import JobSpec
from videoforge.core.models import Plan, PlannedAudio, VideoColor, VideoInfo
from videoforge.core.pipeline.steps import Step
from videoforge.core.video import hdr, info, target, vfr
from videoforge.core.video.encoders import encoder_command, vspipe_command
from videoforge.core.video.qpf import make_qpf, qpf_paths
from videoforge.core.video.script import build_script, ffms2_index, index_exists
from videoforge.core.video.settings import Encoder, EncoderSettings, SourceFilter

if TYPE_CHECKING:
    from videoforge.core.profile import Profile


@dataclass(slots=True)
class JobSteps:
    steps: list[Step]
    output: Path
    encoded_audio: dict[int, Path] = field(default_factory=dict)  # plan.audio position -> file


def output_path(spec: JobSpec, plan: Plan, profile: Profile, out_dir: Path) -> Path:
    """The job's output in out_dir: its own name if it has one, else the profile's, with the job's label
    (if any) after it: `<name>.<label>.mkv`."""
    stem = (spec.output_name or profile.output_stem(plan)) + (f".{spec.label}" if spec.label else "")
    return out_dir / (stem + MUXERS[spec.container(profile)].extension)


def job_output(spec: JobSpec, plan: Plan, profile: Profile) -> Path | None:
    """The file a job writes; None without an output folder."""
    if spec.output_dir is None:
        return None
    return output_path(spec, plan, profile, spec.output_dir)


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


def baked_el(spec: JobSpec, video: VideoInfo | None) -> Path | None:
    """The enhancement layer the job's script bakes in (hdr.bakes_fel), in its work folder; None without one."""
    return spec.work_dir / hdr.DV_EL if spec.encodes_video and hdr.bakes_fel(video, spec.encoder) else None


def job_script(spec: JobSpec, video: VideoInfo | None) -> str:
    """The job's VapourSynth script, as the encode runs it."""
    return build_script(
        spec.video, spec.inputs.source, spec.work_dir, depth=spec.encoder.depth, el=baked_el(spec, video)
    )


def index_steps(spec: JobSpec, app: AppConfig, video: VideoInfo | None = None) -> list[Step]:
    """Write the script and index the source: a job's first steps, and all a batch index runs. video is the
    source's (the plan's): a FEL to bake adds its enhancement layer's demux, MKV and index."""
    work, source = spec.work_dir, spec.inputs.source
    text = job_script(spec, video)
    script = work / "video.vpy"
    source_filter = spec.video.source_filter
    el = baked_el(spec, video)

    def write_script(_log: LogFn) -> None:
        script.write_text(text, encoding="utf-8")

    steps = [
        Step("script", "Write the VapourSynth script", call=write_script, outputs=(script,), key=text, weight=0.01)
    ]
    if el is not None and video is not None:
        if not video.default_duration_ns:
            raise ToolError("The source has no frame rate to time its enhancement layer by")
        hevc = work / hdr.DV_EL_HEVC
        steps += [
            Step(
                "dovi.el",
                "Dolby Vision enhancement layer (dovi_tool demux)",
                argvs=hdr.el_argvs(app.tools, source, hevc),
                outputs=(hevc,),
                inputs=(source,),
                weight=1,
            ),
            Step(
                "dovi.el_mkv",
                "Enhancement layer into an MKV (mkvmerge)",
                argvs=(hdr.el_mkv_argv(app.tools.mkvmerge, hevc, el, video.default_duration_ns),),
                outputs=(el,),
                inputs=(hevc,),
                weight=0.3,
            ),
        ]

    if source_filter is SourceFilter.FFMS2:
        # FFMS2's Source() indexes silently: build its index first, with progress (core/video/ffindex.py).
        # It depends on the source alone, so a crop edit doesn't index again.
        argv = (sys.executable, "-m", "videoforge.core.video.ffindex", str(source), str(ffms2_index(source, work)))
        inputs: tuple[Path, ...] = (source,)
    else:
        # Opening the script makes the source filter build its index (minutes on a big remux).
        # With a FEL to bake, the script opens its enhancement layer too: both are indexed.
        argv, inputs = (app.tools.vspipe, "--info", str(script), "-"), (source, script)
    steps.append(
        # Reused while the index is there (BestSource names its file after the track).
        Step(
            "index",
            "Index the source",
            argvs=(argv,),
            inputs=inputs,
            key=source_filter.value,
            weight=2,
            present=lambda: indexed(spec, video),
        )
    )
    if el is not None and source_filter is SourceFilter.FFMS2:
        el_index = (sys.executable, "-m", "videoforge.core.video.ffindex", str(el), str(ffms2_index(el, work)))
        steps.append(
            Step(
                "dovi.el_index",
                "Index the enhancement layer",
                argvs=(el_index,),
                inputs=(el,),
                weight=0.5,
                present=lambda: index_exists(el, source_filter, work),
            )
        )
    return steps


def script_fps(spec: JobSpec) -> Fraction | None:
    """The script's frame rate, once the job's script info step has written it; None before that, or for a
    variable rate."""
    found = info.read(spec.work_dir / info.SCRIPT_INFO)
    return found.fps if found else None


def indexed(spec: JobSpec, video: VideoInfo | None) -> bool:
    """Whether the job's source (and a FEL's enhancement layer it bakes) is indexed: opening its video is quick."""
    s, el = spec.video.source_filter, baked_el(spec, video)
    return index_exists(spec.inputs.source, s, spec.work_dir) and (el is None or index_exists(el, s, spec.work_dir))


def video_steps(
    spec: JobSpec, plan: Plan, app: AppConfig, container: str = "mkv", encoded: Mapping[int, Path] | None = None
) -> list[Step]:
    """encoded: plan.audio position -> its encoded file, which a target size's pass 2 counts."""
    work, source, enc = spec.work_dir, spec.inputs.source, spec.encoder
    script = work / "video.vpy"
    v = plan.source.video
    text = job_script(spec, v)
    steps = index_steps(spec, app, v)
    info_file = work / info.SCRIPT_INFO
    steps.append(
        Step(
            "script.info",
            "Script frames and frame rate (vspipe --info)",
            argvs=(info.info_argv(app.tools.vspipe, script, info_file),),
            outputs=(info_file,),
            inputs=(script, source),
            key=text,
            weight=0.05,
        )
    )
    qpfile = None
    if spec.makes_chapters:
        files = qpf_paths(work)
        video = plan.source.video
        if video is None or not video.default_duration_ns:
            raise ToolError("The source has no frame rate to place chapters by")
        source_fps = frame_rate(video.default_duration_ns)

        # The chapters' frames are the script's: its frame rate once the info step has read it (before a run,
        # the source's).
        def chapters_step(fps: Fraction) -> Step:
            def make_chapters(log: LogFn) -> None:
                if make_qpf(source, work, fps) is None:
                    raise ToolError("AutoQPF could not read or generate chapters for the source")
                log(f"Chapters and qpfile written ({fps} fps)")

            return Step(
                "chapters",
                "Chapters and qpfile (AutoQPF)",
                call=make_chapters,
                outputs=(files.qpfile, files.chapters),
                inputs=(source,),
                key=str(fps),
                weight=0.1,
                refresh=lambda: chapters_step(script_fps(spec) or source_fps),
            )

        steps.append(chapters_step(source_fps))
        qpfile = files.qpfile

    exe = app.tools.x265 if enc.encoder is Encoder.X265 else app.tools.x264
    sar = spec.video.output_sar(v.width, v.height, v.sar) if v is not None else None
    color = v.color if v is not None else None
    pipe = tuple(vspipe_command(app.tools.vspipe, script))
    shared = (script, source) + ((qpfile,) if qpfile else ())
    hdr10plus = None
    if hdr.keeps_hdr10plus(v, enc):
        hdr10plus = work / hdr.HDR10PLUS_JSON
        meta = hdr10plus

        def check_frames(log: LogFn) -> None:
            hdr.check_frames(app.tools.vspipe, script, meta, log)

        steps += [
            Step(
                "hdr10plus",
                "HDR10+ metadata (hdr10plus_tool)",
                argvs=hdr.hdr10plus_argvs(app.tools, source, meta),
                outputs=(meta,),
                inputs=(source,),
                weight=1,
            ),
            Step(
                "hdr10plus.check",
                "HDR10+ frames against the script",
                call=check_frames,
                inputs=(script, meta),
                key=text,
                weight=0.1,
            ),
        ]
        shared += (meta,)
    dolby_vision, source_rpu, dv_profile = None, work / hdr.DV_SOURCE_RPU, hdr.dv_profile(v)
    if hdr.keeps_dv(v, enc) and v is not None:
        dolby_vision = work / hdr.DV_RPU
        rpu, width, height = dolby_vision, v.width, v.height
        order = [s.category.value for s in spec.video.filters if s.category.value in ("crop", "resize")]

        def edit_rpu(log: LogFn) -> None:
            hdr.edit_rpu(app.tools.dovi_tool, source_rpu, rpu, spec.video, width, height, log, dv_profile)

        def check_rpu(log: LogFn) -> None:
            hdr.check_rpu_frames(app.tools.vspipe, app.tools.dovi_tool, script, rpu, log)

        steps += [
            Step(
                "dovi.rpu",
                "Dolby Vision RPU (dovi_tool)",
                argvs=hdr.rpu_argvs(app.tools, source, source_rpu),
                outputs=(source_rpu,),
                inputs=(source,),
                weight=1,
            ),
            # Keyed by the crop and resize (and their order): a new one edits the RPU again.
            Step(
                "dovi.edit",
                f"Dolby Vision RPU: crop, resize, profile {dv_profile}",
                call=edit_rpu,
                outputs=(rpu,),
                inputs=(source_rpu,),
                key=f"{width}x{height} {spec.video.crop} {spec.video.resize} {order} {dv_profile}",
                weight=0.2,
            ),
            Step(
                "dovi.check",
                "Dolby Vision frames against the script",
                call=check_rpu,
                inputs=(script, rpu),
                key=text,
                weight=0.1,
            ),
        ]
        shared += (rpu,)
    out = spec.video_output
    name = enc.encoder.value
    audio_files = tuple((encoded or {}).values())

    def sized(final: bool) -> EncoderSettings:
        """The settings with a target size's bitrate: the script's length once its info step has run (before a
        run, the source's); pass 2 (final) counts the encoded audio's files, pass 1 the planned sizes. Without a
        length, the typed bitrate (target.issues blocks the job)."""
        if not target.applies(enc) or enc.target_mb is None:
            return enc
        found = target.budget(
            enc.target_mb, plan, container, info.read(info_file), encoded if final else None, (hdr10plus, dolby_vision)
        )
        return enc if found is None else replace(enc, bitrate_kbps=found.kbps)

    def encodes(color: VideoColor | None) -> list[Step]:
        command = partial(
            encoder_command,
            exe,
            qpfile=qpfile,
            sar=sar,
            color=color,
            hdr10plus=hdr10plus,
            dolby_vision=dolby_vision,
            dv_profile=dv_profile,
        )
        if enc.passes != 2:
            argv = command(enc, output=out)
            return [
                Step(
                    "video",
                    f"Video ({name})",
                    argvs=(pipe, tuple(argv)),
                    outputs=(out,),
                    inputs=shared,
                    key=text,
                    weight=60,
                )
            ]
        stats = work / "video.stats"
        first = command(sized(False), output=Path(os.devnull), pass_number=1, stats=stats)
        second = command(sized(True), output=out, pass_number=2, stats=stats)
        # A target size's pass 2 waits for the audio encodes (run_steps), whose files its bitrate counts.
        waits = audio_files if target.applies(enc) else ()
        return [
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
                inputs=(*shared, stats, *waits),
                key=text,
                weight=60,
            ),
        ]

    fel = baked_el(spec, v) is not None and color is not None
    if not fel and not target.applies(enc):
        return steps + encodes(color)
    # A baked FEL's HDR10 values come from the source's RPU, read when the encode's turn comes (the steps
    # before it extract the RPU); until then (the Encoder tab before a run) the source's. A target size's
    # bitrate is worked out again then too: by the script's length and the files the steps before it wrote.
    source_color, dovi_tool = color, app.tools.dovi_tool

    def fel_color() -> VideoColor | None:
        if not fel or source_color is None or not source_rpu.is_file():
            return source_color
        return hdr.fel_color(source_color, hdr.rpu_summary(dovi_tool, source_rpu))

    def refreshed(k: int) -> Step:
        return replace(encodes(fel_color())[k], refresh=lambda: refreshed(k))

    return steps + [refreshed(k) for k in range(len(encodes(color)))]


def build_steps(spec: JobSpec, plan: Plan, profile: Profile, app: AppConfig, output: Path) -> JobSteps:
    if plan.source.path is None:
        raise ToolError("The plan has no source file")
    work = spec.work_dir
    settings = profile.audio_settings()
    encoded: dict[int, Path] = {}
    audio: list[Step] = []
    for pos, a in enumerate(plan.audio):
        src = a.source.external_path or plan.source.path  # an added audio file is read from itself
        cmd = audio_command(a, pos, src, work, settings, app.tools)
        if cmd is None:
            continue
        encoded[pos] = cmd.output
        encode = Step(
            f"audio.{pos + 1}",
            f"Encode audio {pos + 1}: {a.title}",
            argvs=cmd.argvs,
            outputs=(cmd.output,),
            inputs=(src,),
            weight=4,
            background=True,
        )
        if needs_measure(a):
            # Normalizing by a peak or a loudness: the encode applies what the measure step read, when its
            # turn comes (on its own thread, beside the video: run_steps).
            found = measure_path(a, pos, work)
            audio.append(
                Step(
                    f"audio.{pos + 1}.measure",
                    f"Measure audio {pos + 1}: {a.title}",
                    argvs=(measure_argv(a, src, found, app.tools),),
                    outputs=(found,),
                    inputs=(src,),
                    weight=1,
                    background=True,
                )
            )

            def measured(base: Step, a: PlannedAudio = a, pos: int = pos, src: Path = src, found: Path = found) -> Step:
                again = audio_command(a, pos, src, work, settings, app.tools, loudness.read(found))
                argvs = base.argvs if again is None else again.argvs
                return replace(base, argvs=argvs, refresh=partial(measured, base))

            encode = replace(encode, inputs=(src, found))
            encode = replace(encode, refresh=partial(measured, encode))
        audio.append(encode)
    container = spec.container(profile)
    steps = video_steps(spec, plan, app, container, encoded) if spec.encodes_video else []
    video = plan.source.video
    timestamps = work / vfr.TIMESTAMPS if vfr.carries(video, container) and video is not None else None
    if timestamps is not None and video is not None:
        argv = vfr.extract_argv(app.tools.mkvextract, plan.source.path, video.id, timestamps)
        stamps = Step(
            "timestamps",
            "Source timestamps (mkvextract)",
            argvs=(argv,),
            outputs=(timestamps,),
            inputs=(plan.source.path,),
            weight=0.5,
        )
        audio.insert(0, stamps)
    at = next((n for n, s in enumerate(steps) if s.id.startswith("video")), len(steps))
    steps[at:at] = audio

    if container == "mp4" and (chapters := mp4_chapters_step(plan, work)) is not None:
        steps.append(chapters)
        plan = replace(plan, chapters_path=chapters.outputs[0])
    unfinished = output.with_name(output.name + ".partial")
    mux_inputs = [
        p for p in (plan.source.path, plan.encode_path, plan.chapters_path, *encoded.values()) if p is not None
    ]
    mux_inputs += [s.source.external_path for s in plan.subs if s.source.external_path is not None]
    mux_inputs += list(dict.fromkeys(a.source.external_path for a in plan.audio if a.source.external_path is not None))
    muxer, extra = MUXERS[container], split_args(spec.mux.extra)

    # The job's encode is timed by the script's frame rate, once the info step has read it (before a run, the
    # source's); a reused encode by the source's. A VFR source's timestamps time it instead, while they fit the
    # script (one per frame: an IVTC or a trim drops them for the script's rate).
    def timing() -> tuple[Fraction | None, Path | None]:
        found = info.read(work / info.SCRIPT_INFO)
        if found is None:
            return None, timestamps
        return found.fps, timestamps if timestamps is not None and vfr.fits(timestamps, found.frames) else None

    def mux_step(fps: Fraction | None, stamps: Path | None) -> Step:
        return Step(
            "mux",
            "Mux",
            argvs=(tuple(muxer.command(plan, encoded, unfinished, app, extra, fps, stamps)),),
            outputs=(output,),
            writes=(unfinished,),
            inputs=(*mux_inputs, *((stamps,) if stamps else ())),
            finalize=lambda: unfinished.replace(output),
            weight=3,
            refresh=(lambda: mux_step(*timing())) if spec.encodes_video else None,
        )

    steps.append(mux_step(None, timestamps))
    return JobSteps(steps, output, encoded)
