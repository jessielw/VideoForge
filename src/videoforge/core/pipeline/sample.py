"""A test encode (StaxRip's compressibility check): the job's script and encoder settings on short blocks spread
over the video, for the bitrate they give, the size and time the whole encode would take, and frames to compare
with what went into the encoder.

    <job>/sample/sample.vpy   the job's script, then SelectEvery: `length` frames of every `cycle`
    <job>/sample/video.<ext>  the encode: one pass (a 2-pass job's at the bitrate its first pass gets)
    <job>/sample/sample.mkv   the encode in an MKV (mkvmerge), which the preview opens (FFMS2) and a player plays
    <job>/sample/sample.quality.json  its SSIMULACRA2 and XPSNR against sample.vpy (Settings' quality score, off
                              by default; core/video/metrics.py)
    <job>/sample/sample.json  what it gave (SampleResult)

The blocks are StaxRip's: 2 s each, one in every 100 / percent (5%: 2 s of every 40 s). SelectEvery keeps each
frame's duration, so the sample is timed as the job's encode. HDR10+ and Dolby Vision metadata and the chapters'
keyframes are left out (their frames are the whole video's); the source colour and HDR10 go in as the job's encode
writes them. The script info step (the whole script's frames and rate) runs first: the blocks are laid out by it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace
from datetime import datetime
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys

from videoforge.core.config import AppConfig
from videoforge.core.execute.mux import frame_rate
from videoforge.core.execute.process import LogFn
from videoforge.core.job import JobSpec, StepRecord
from videoforge.core.models import Plan
from videoforge.core.pipeline.build import info_step, job_script
from videoforge.core.pipeline.steps import Step
from videoforge.core.plan_io import to_json
from videoforge.core.video import burn as burn_in, info, metrics, target
from videoforge.core.video.encoders import TOOLS, encoder_command, output_name, vspipe_command
from videoforge.core.video.info import ScriptInfo
from videoforge.core.video.script import ffms2_index
from videoforge.core.video.settings import Encoder, EncoderSettings, RateControl

SAMPLE_DIR = "sample"  # in the job's folder
SCRIPT = "sample.vpy"
MKV = "sample.mkv"
RESULT = "sample.json"
QUALITY = "sample.quality.json"
_METRICS = "ssimulacra2 mean, p5; xpsnr y"  # what the quality step measures: a change measures again
PERCENTS = (1, 2, 5, 10)  # of the video's length
DEFAULT_PERCENT = 5  # StaxRip's CompCheckPercentage
BLOCK_SECONDS = 2  # StaxRip's CompCheckTestblockSeconds
_RAW = (".264", ".hevc")  # mkvmerge needs their frame rate


def sample_dir(spec: JobSpec) -> Path:
    return spec.job_dir / SAMPLE_DIR


@dataclass(frozen=True, slots=True)
class Selection:
    """`length` frames from the start of every `cycle`."""

    cycle: int
    length: int

    def frames(self, total: int) -> int:
        """The frames it takes from a clip of total frames."""
        return (total // self.cycle) * self.length + min(total % self.cycle, self.length)


def selection(found: ScriptInfo, percent: int, fallback_fps: Fraction | None = None) -> Selection:
    """The blocks for percent of the script: BLOCK_SECONDS each, at its frame rate (a variable one: fallback_fps,
    the source's; else 24)."""
    fps = found.fps or fallback_fps or Fraction(24)
    length = max(1, round(fps * BLOCK_SECONDS))
    return Selection(max(length, round(length * 100 / percent)), length)


def script_text(job_script: str, sel: Selection) -> str:
    """The job's script with the selection before its output."""
    head, out = job_script.rstrip("\n").rsplit("\n", 1)
    return (
        "\n".join(
            [
                head,
                f"# VideoForge test encode: {sel.length} frames of every {sel.cycle}",
                f"clip = core.std.SelectEvery(clip, cycle={sel.cycle}, offsets=list(range({sel.length})), "
                "modify_duration=False)",
                out,
            ]
        )
        + "\n"
    )


def sample_key(spec: JobSpec, plan: Plan) -> str:
    """What a sample depends on besides its percent: the job's script and encoder settings. A result made with
    another key is out of date."""
    doc = json.dumps([job_script(spec, plan.source.video, plan.burn), to_json(spec.encoder)], default=str)
    return hashlib.sha1(doc.encode("utf-8"), usedforsecurity=False).hexdigest()


def one_pass(enc: EncoderSettings, plan: Plan, container: str, found: ScriptInfo) -> EncoderSettings:
    """The job's settings as one pass: 2-pass at its bitrate, a target size's as its first pass works it out."""
    if enc.rate_control is not RateControl.TWO_PASS:
        return enc
    kbps = enc.bitrate_kbps
    if target.applies(enc) and enc.target_mb is not None:
        found_budget = target.budget(enc.target_mb, plan, container, found)
        if found_budget is not None:
            kbps = found_budget.kbps
    return replace(enc, rate_control=RateControl.ABR, bitrate_kbps=kbps)


def describe(enc: EncoderSettings) -> str:
    """The rate the sample ran at, for its result: "x265 crf 18", "x264 8000 kb/s"."""
    rate = f"crf {enc.crf:g}" if enc.rate_control is RateControl.CRF else f"{enc.bitrate_kbps} kb/s"
    return f"{enc.encoder.label} {rate}"


def prepare_steps(spec: JobSpec, plan: Plan, app: AppConfig) -> list[Step]:
    """What the sample needs first, after the job's index steps (index_steps): the script's info, which lays
    out the blocks."""
    return [info_step(spec, app, job_script(spec, plan.source.video, plan.burn))]


def sample_steps(
    spec: JobSpec, plan: Plan, app: AppConfig, container: str, percent: int, quality: bool = False
) -> list[Step]:
    """The sample's script, encode and MKV, then with quality its scores against the script; the script info
    step (prepare_steps) has run."""
    found = info.read(spec.job_dir / info.SCRIPT_INFO)
    if found is None:
        raise ValueError("The script's frames aren't known: its info step hasn't run")
    v, home = plan.source.video, sample_dir(spec)
    source_fps = frame_rate(v.default_duration_ns) if v is not None and v.default_duration_ns else None
    sel = selection(found, percent, source_fps)
    text = script_text(job_script(spec, v, plan.burn), sel)
    script, mkv = home / SCRIPT, home / MKV
    enc = one_pass(spec.encoder, plan, container, found)
    out = home / output_name(enc)

    def write_script(_log: LogFn) -> None:
        home.mkdir(parents=True, exist_ok=True)
        script.write_text(text, encoding="utf-8")

    argv = encoder_command(
        getattr(app.tools, TOOLS[enc.encoder]),
        enc,
        output=out,
        frames=sel.frames(found.frames) if enc.encoder is Encoder.SVTAV1 else None,
        sar=spec.video.output_sar(v.width, v.height, v.sar) if v is not None else None,
        color=v.color if v is not None else None,
    )
    inputs = (script, spec.inputs.source)
    if plan.burn is not None:
        inputs += burn_in.dependencies(plan.burn, spec.work_dir)
    fps = found.fps or source_fps
    mux = [app.tools.mkvmerge, "--output", str(mkv)]
    if out.suffix in _RAW and fps:
        mux += ["--default-duration", f"0:{fps}p"]
    steps = [
        Step(
            "sample.script",
            "Write the test encode's script",
            call=write_script,
            outputs=(script,),
            key=text,
            weight=0.01,
        ),
        Step(
            "sample.video",
            f"Test encode ({enc.encoder.label}, {percent}%)",
            argvs=(tuple(vspipe_command(app.tools.vspipe, script)), tuple(argv)),
            outputs=(out,),
            inputs=inputs,
            key=text,
            weight=60,
        ),
        Step(
            "sample.mux",
            "Test encode into an MKV (mkvmerge)",
            argvs=((*mux, str(out)),),
            outputs=(mkv,),
            inputs=(out,),
            weight=1,
            # The last MKV's FFMS2 index (the preview's, the quality step's): Source() won't open a new one by it
            finalize=lambda: ffms2_index(mkv, home).unlink(missing_ok=True),
        ),
    ]
    if quality:
        scores = home / QUALITY
        steps.append(
            Step(
                "sample.quality",
                "Test encode quality (SSIMULACRA2, XPSNR)",
                argvs=((sys.executable, "-m", "videoforge.core.video.metrics", str(script), str(mkv), str(scores)),),
                outputs=(scores,),
                inputs=(script, mkv),
                key=_METRICS,
                weight=20,
            )
        )
    return steps


@dataclass(frozen=True, slots=True)
class SampleResult:
    percent: int
    cycle: int
    length: int
    frames: int  # the sample's
    total_frames: int  # the script's
    fps: float | None  # the script's (None: variable)
    bytes: int  # the encoded stream's
    seconds: float  # the encode took
    encoder: str  # describe()
    key: str  # sample_key() when it was made
    finished: str  # ISO time
    # Its quality against the script (metrics.Scores), when Settings' quality score was on
    ssimulacra2: float | None = None
    ssimulacra2_p5: float | None = None
    xpsnr: float | None = None  # dB

    @property
    def kbps(self) -> float | None:
        return self.bytes * 8 / 1000 / (self.frames / self.fps) if self.fps and self.frames else None

    @property
    def estimate_mb(self) -> float | None:
        """The whole video's encode, in decimal MB, at the sample's bitrate (no container overhead)."""
        rate = self.kbps
        return rate * (self.total_frames / self.fps) / 8 / 1000 if rate is not None and self.fps else None

    @property
    def estimate_seconds(self) -> float | None:
        """The whole video's encode time at the sample's pace (one pass)."""
        return self.seconds * self.total_frames / self.frames if self.frames and self.seconds else None

    @property
    def encode_fps(self) -> float | None:
        return self.frames / self.seconds if self.seconds else None


def finish(
    spec: JobSpec,
    plan: Plan,
    container: str,
    percent: int,
    records: dict[str, StepRecord],
    quality: bool = False,
) -> SampleResult:
    """The sample's result from its steps' files and records (with quality, the quality step's scores), written
    to sample.json."""
    found = info.read(spec.job_dir / info.SCRIPT_INFO)
    if found is None:
        raise ValueError("The script's frames aren't known: its info step hasn't run")
    v = plan.source.video
    source_fps = frame_rate(v.default_duration_ns) if v is not None and v.default_duration_ns else None
    sel = selection(found, percent, source_fps)
    enc = one_pass(spec.encoder, plan, container, found)
    out = sample_dir(spec) / output_name(enc)
    record = records.get("sample.video")
    fps = found.fps or source_fps
    scores = metrics.read(sample_dir(spec) / QUALITY) if quality else None
    result = SampleResult(
        percent=percent,
        cycle=sel.cycle,
        length=sel.length,
        frames=sel.frames(found.frames),
        total_frames=found.frames,
        fps=float(fps) if fps else None,
        bytes=out.stat().st_size,
        seconds=record.seconds if record else 0.0,
        encoder=describe(enc),
        key=sample_key(spec, plan),
        finished=datetime.now().isoformat(timespec="seconds"),
        ssimulacra2=scores.ssimulacra2 if scores else None,
        ssimulacra2_p5=scores.ssimulacra2_p5 if scores else None,
        xpsnr=scores.xpsnr if scores else None,
    )
    (sample_dir(spec) / RESULT).write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
    return result


def read_result(spec: JobSpec) -> SampleResult | None:
    """The job's last sample, while its MKV is there; None without one (or one that can't be read). One from
    before the quality scores has none."""
    home = sample_dir(spec)
    if not (home / MKV).is_file():
        return None
    try:
        data = json.loads((home / RESULT).read_text(encoding="utf-8"))
        return SampleResult(**{f.name: data[f.name] for f in fields(SampleResult) if f.name in data})
    except (OSError, ValueError, KeyError, TypeError):
        return None
