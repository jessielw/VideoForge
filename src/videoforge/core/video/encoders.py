"""x264 / x265 command lines fed by vspipe, one per pass, plus progress parsing.

    vspipe -c y4m video.vpy -  |  x264 --demuxer y4m --frames N ... --output video.264 -

Both encoders write a raw elementary stream (.264 / .hevc); the mux gives it its
timestamps. A qpfile (from the chapters) forces keyframes at chapter starts.
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path
import re
import shlex

from videoforge.core.models import VideoColor
from videoforge.core.video.color import color_args
from videoforge.core.video.settings import Encoder, EncoderSettings, RateControl

EXTENSIONS = {Encoder.X264: ".264", Encoder.X265: ".hevc"}
_PERCENT = re.compile(r"\[\s*(\d+(?:\.\d+)?)%\]")  # both encoders: "[ 12.3%] 1234/10000 frames, ..."
# x265 without --frames: "1234 frames: 23.4 fps, ..." (Patman's mod: "1234 Frames @ 23.4 FPS | ...")
_X265_FRAMES = re.compile(r"^\s*(\d+) frames(?::| @)", re.IGNORECASE)
_VSPIPE_FRAMES = re.compile(r"Frame:\s*(\d+)/(\d+)")
_FPS = re.compile(r"(\d+(?:\.\d+)?) fps\b", re.IGNORECASE)
# x264 / x265 "eta 0:01:23"; Patman's mods "| 0:00:04 [-0:01:23] |" (elapsed [-left])
_ETA = re.compile(r"(?:\beta |\[-)(\d+):(\d\d):(\d\d)")


def output_name(settings: EncoderSettings) -> str:
    return "video" + EXTENSIONS[settings.encoder]


def vspipe_command(vspipe: str, script: Path) -> list[str]:
    """y4m to stdout; -p prints "Frame: n/total" to stderr, the progress the pipeline reads."""
    return [vspipe, "-c", "y4m", "-p", str(script), "-"]


def _options(options: dict[str, str]) -> list[str]:
    args = []
    for name, value in options.items():
        flag = "--" + name.lstrip("-")
        args += [flag] if value == "" else [flag, value]
    return args


def encoder_command(
    exe: str,
    settings: EncoderSettings,
    *,
    output: Path,
    frames: int | None = None,
    pass_number: int | None = None,
    stats: Path | None = None,
    qpfile: Path | None = None,
    sar: Fraction | None = None,
    color: VideoColor | None = None,
) -> list[str]:
    """One encoder run reading y4m from stdin. pass_number is 1 or 2 for a two-pass encode. sar is the
    encode's pixel aspect ratio (vspipe's y4m carries none), written when it isn't square; color is the
    source's colour description (color.color_args). A --sar or colour flag in the options or extra arguments
    comes after them, and wins."""
    x265 = settings.encoder is Encoder.X265
    argv = [exe, "--y4m"] if x265 else [exe, "--demuxer", "y4m"]
    argv += ["--frames", str(frames)] if frames else []
    argv += ["--preset", settings.preset] if settings.preset else []
    argv += ["--tune", settings.tune] if settings.tune else []
    if settings.rate_control is RateControl.CRF:
        argv += ["--crf", f"{settings.crf:g}"]
    else:
        argv += ["--bitrate", str(settings.bitrate_kbps)]
    if settings.rate_control is RateControl.TWO_PASS:
        if pass_number not in (1, 2) or stats is None:
            raise ValueError("A two-pass encode needs pass_number 1 or 2 and a stats file")
        argv += ["--pass", str(pass_number), "--stats", str(stats)]
    if x265 or settings.depth != 8:
        argv += ["--output-depth", str(settings.depth)]
    if sar is not None and sar != 1:
        argv += ["--sar", f"{sar.numerator}:{sar.denominator}"]
    argv += color_args(color, settings)
    argv += _options(settings.options)
    if qpfile is not None:
        argv += ["--qpfile", str(qpfile)]
    if settings.extra.strip():
        argv += shlex.split(settings.extra, posix=False)
    argv += ["--output", str(output), "-"]
    return argv


def progress(line: str, frames: int | None = None) -> float | None:
    """Fraction done (0..1) from one line of encoder or vspipe output, if it carries one."""
    if m := _PERCENT.search(line):
        return float(m.group(1)) / 100
    if m := _VSPIPE_FRAMES.search(line):
        total = int(m.group(2))
        return int(m.group(1)) / total if total else None
    if frames and (m := _X265_FRAMES.match(line.split("] ", 1)[-1])):
        return int(m.group(1)) / frames
    return None


def rate(line: str) -> tuple[float | None, int | None]:
    """Frames per second and the encoder's own time left (seconds) from a line progress() reads, where it prints
    them. Only for progress lines: an info line like "1920x1080 fps 24/1" isn't one. vspipe's lines give neither:
    it reads ahead of the encoder, so its fps isn't the encode's."""
    if _VSPIPE_FRAMES.search(line):
        return None, None
    fps = float(m.group(1)) if (m := _FPS.search(line)) else None
    eta = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) if (m := _ETA.search(line)) else None
    return fps, eta
