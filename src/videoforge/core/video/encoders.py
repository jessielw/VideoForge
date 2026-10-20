"""Encoder command lines fed by vspipe, one per pass, plus progress parsing.

    vspipe -c y4m video.vpy -  |  x264 --demuxer y4m --frames N ... --output video.264 -
    vspipe -c y4m video.vpy -  |  ffmpeg -f yuv4mpegpipe -i - -c:v libvpx-vp9 ... -f ivf video.ivf
    vspipe -c y4m video.vpy -  |  SvtAv1EncApp --input - --frames N ... --output video.ivf

x264 / x265 write a raw elementary stream (.264 / .hevc); the mux gives it its timestamps. A qpfile (from the
chapters) forces keyframes at chapter starts. VP8 / VP9 go through ffmpeg's libvpx, as in StaxRip, into an IVF
(timed by the y4m's frame rate); the chapters' keyframes become -force_key_frames, and the mux writes the pixel
aspect and the colour the stream doesn't hold. SVT-AV1 (SvtAv1EncApp, as StaxRip runs it) writes an IVF too; its
keyframes are --force-key-frames (CRF only: SvtAv1EncApp refuses it with a bitrate), and the mux writes the pixel
aspect, and the colour mkvmerge doesn't copy from the stream.
"""

from __future__ import annotations

from collections.abc import Sequence
from fractions import Fraction
from pathlib import Path
import re
import shlex

from videoforge.core.models import Issue, Severity, VideoColor, VideoInfo
from videoforge.core.video.color import color_args, hdr10
from videoforge.core.video.settings import Encoder, EncoderSettings, RateControl

EXTENSIONS = {
    Encoder.X264: ".264",
    Encoder.X265: ".hevc",
    Encoder.VP8: ".ivf",
    Encoder.VP9: ".ivf",
    Encoder.SVTAV1: ".ivf",
}
# The Tools field that runs each encoder
TOOLS = {
    Encoder.X264: "x264",
    Encoder.X265: "x265",
    Encoder.VP8: "ffmpeg",
    Encoder.VP9: "ffmpeg",
    Encoder.SVTAV1: "svtav1",
}
LIBVPX = {Encoder.VP8: "libvpx", Encoder.VP9: "libvpx-vp9"}
# StaxRip's ffmpeg VP9 defaults (ffmpegEnc.vb), plus row-based threading; the job's options come after them, and win
VP9_DEFAULTS = {"tile-columns": "6", "frame-parallel": "1", "auto-alt-ref": "1", "lag-in-frames": "25", "row-mt": "1"}
# VP8's CRF ceiling. ffmpeg runs VP8 -crf as constrained quality and reads -b:v 0 as its 256 kbit/s default (VP9
# alone has a true constant quality); a Fallout 1080p sample at -crf 20 came out the same with 100M and 1000M
VP8_CRF_CAP = "100M"
# SvtAv1EncApp's --preset and --crf ranges (13 fastest; CRF in quarter steps)
SVTAV1_PRESETS = range(-1, 14)
SVTAV1_CRF = (1, 70)
_PERCENT = re.compile(r"\[\s*(\d+(?:\.\d+)?)%\]")  # both encoders: "[ 12.3%] 1234/10000 frames, ..."
# x265 without --frames: "1234 frames: 23.4 fps, ..." (Patman's mod: "1234 Frames @ 23.4 FPS | ...")
_X265_FRAMES = re.compile(r"^\s*(\d+) frames(?::| @)", re.IGNORECASE)
_FFMPEG_FRAMES = re.compile(r"^frame=\s*(\d+)\s+fps=\s*(\d+(?:\.\d+)?)")  # "frame=  123 fps= 23 q=..."
# SvtAv1EncApp --progress 2 (its colours stripped): "Encoding:  123/1000 Frames @ 4.56 fps | ... [-0:01:23]"; below
# a frame a second, frames per minute ("fpm"); without the total when it doesn't know it ("Encoding:  123 Frames")
_SVT_FRAMES = re.compile(r"^Encoding:\s*(\d+)(?:/(\d+))? Frames @ (\d+(?:\.\d+)?) fp([sm])")
_VSPIPE_FRAMES = re.compile(r"Frame:\s*(\d+)/(\d+)")
_FPS = re.compile(r"(\d+(?:\.\d+)?) fps\b", re.IGNORECASE)
# x264 / x265 "eta 0:01:23"; Patman's mods "| 0:00:04 [-0:01:23] |" (elapsed [-left])
_ETA = re.compile(r"(?:\beta |\[-)(\d+):(\d\d):(\d\d)")
# H.265's MaxBR for Main / Main 10 (kb/s) by level x 10: (Main tier, High tier); below level 4 there's no High tier
_LEVEL_KBPS = {
    10: (128, 128),
    20: (1500, 1500),
    21: (3000, 3000),
    30: (6000, 6000),
    31: (10000, 10000),
    40: (12000, 30000),
    41: (20000, 50000),
    50: (25000, 100000),
    51: (40000, 160000),
    52: (60000, 240000),
    60: (60000, 240000),
    61: (120000, 480000),
    62: (240000, 800000),
}


def output_name(settings: EncoderSettings) -> str:
    return "video" + EXTENSIONS[settings.encoder]


def forces_keyframes(settings: EncoderSettings) -> bool:
    """Whether the chapters' keyframes go in as a list of frames (keyframes), not a qpfile: VP8 / VP9, and SVT-AV1
    in CRF (SvtAv1EncApp: "Force key frames is not supported for VBR mode")."""
    return settings.encoder.libvpx or (settings.encoder is Encoder.SVTAV1 and settings.rate_control is RateControl.CRF)


def stats_path(work: Path, settings: EncoderSettings) -> Path:
    """The file a two-pass encode's first pass writes: ffmpeg adds "-0.log" to its -passlogfile."""
    return work / ("video.stats-0.log" if settings.encoder.libvpx else "video.stats")


def qpfile_frames(qpfile: Path) -> list[int]:
    """The frames a qpfile ("1234 I" lines) forces keyframes at; [] when it isn't written yet."""
    if not qpfile.is_file():
        return []
    lines = qpfile.read_text(encoding="utf-8", errors="replace").split("\n")
    return [int(f[0]) for f in (line.split() for line in lines) if f and f[0].isdigit()]


def vspipe_command(vspipe: str, script: Path) -> list[str]:
    """y4m to stdout; -p prints "Frame: n/total" to stderr, the progress the pipeline reads."""
    return [vspipe, "-c", "y4m", "-p", str(script), "-"]


def _options(options: dict[str, str], dashes: str = "--") -> list[str]:
    args = []
    for name, value in options.items():
        flag = dashes + name.lstrip("-")
        args += [flag] if value == "" else [flag, value]
    return args


def _setting(settings: EncoderSettings, name: str) -> str | None:
    """The value the options or the extra arguments give a flag ("" for a bare flag; the extra arguments come
    last, so theirs wins); None when neither sets it."""
    value = None
    for key, v in settings.options.items():
        if key.lstrip("-") == name:
            value = v
    args = shlex.split(settings.extra, posix=False) if settings.extra.strip() else []
    for i, arg in enumerate(args):
        flag, eq, v = arg.partition("=")
        if flag.startswith("--") and flag[2:] == name:
            nxt = args[i + 1] if i + 1 < len(args) else ""
            value = v if eq else ("" if nxt.startswith("--") else nxt)
    return value


def level_vbv(settings: EncoderSettings) -> list[str] | None:
    """The --vbv-maxrate / --vbv-bufsize the options and extra arguments leave out, filled with --level-idc's
    max bitrate (High tier unless --no-high-tier, x265's default), as StaxRip does for an HDR encode: [] when
    both are set, None when one is missing and the level isn't set or known. x265 reads a level below 10 as
    "5.1" and from 10 as "51"."""
    missing = [f for f in ("vbv-maxrate", "vbv-bufsize") if not _setting(settings, f)]
    if not missing:
        return []
    try:
        level = float(_setting(settings, "level-idc") or "")
    except ValueError:
        return None
    kbps = _LEVEL_KBPS.get(int(10 * level + 0.5) if level < 10 else int(level))
    if kbps is None:
        return None
    rate = str(kbps[0] if _setting(settings, "no-high-tier") is not None else kbps[1])
    return [arg for f in missing for arg in ("--" + f, rate)]


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
    hdr10plus: Path | None = None,
    dolby_vision: Path | None = None,
    dv_profile: str = "8.1",
    keyframes: Sequence[int] = (),
) -> list[str]:
    """One encoder run reading y4m from stdin. pass_number is 1 or 2 for a two-pass encode. sar is the
    encode's pixel aspect ratio (vspipe's y4m carries none), written when it isn't square; color is the
    source's colour description (color.color_args); hdr10plus an x265 encode's HDR10+ metadata and dolby_vision
    its RPU, written as dv_profile (8.1, or 5: hdr.dv_profile); with that RPU or HDR10, the VBV (HRD) is filled from --level-idc (level_vbv), as
    StaxRip does. A --sar or colour flag in the options or extra arguments comes after them, and wins. VP8 / VP9
    (ffmpeg_command) and SVT-AV1 (svtav1_command) take keyframes (qpfile_frames) instead of the qpfile, and no
    sar."""
    if settings.encoder is Encoder.SVTAV1:
        return svtav1_command(
            exe,
            settings,
            output=output,
            frames=frames,
            pass_number=pass_number,
            stats=stats,
            color=color,
            keyframes=keyframes,
        )
    if settings.encoder.libvpx:
        return ffmpeg_command(
            exe,
            settings,
            output=output,
            frames=frames,
            pass_number=pass_number,
            stats=stats,
            color=color,
            keyframes=keyframes,
        )
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
    if hdr10plus is not None and x265:
        argv += ["--dhdr10-info", str(hdr10plus)]
    if dolby_vision is not None and x265:
        argv += ["--dolby-vision-profile", dv_profile, "--dolby-vision-rpu", str(dolby_vision)]
    if x265 and (dolby_vision is not None or hdr10(color, settings)):
        argv += level_vbv(settings) or []
    argv += _options(settings.options)
    if qpfile is not None:
        argv += ["--qpfile", str(qpfile)]
    if settings.extra.strip():
        argv += shlex.split(settings.extra, posix=False)
    argv += ["--output", str(output), "-"]
    return argv


def ffmpeg_command(
    exe: str,
    settings: EncoderSettings,
    *,
    output: Path,
    frames: int | None = None,
    pass_number: int | None = None,
    stats: Path | None = None,
    color: VideoColor | None = None,
    keyframes: Sequence[int] = (),
) -> list[str]:
    """A VP8 / VP9 run of ffmpeg (libvpx) reading y4m from stdin, as StaxRip's ffmpeg encoder writes it: -crf
    with -b:v 0 for constant quality (VP8: -b:v VP8_CRF_CAP, where StaxRip's 0 is a 256 kbit/s cap), the preset as
    -cpu-used, VP9_DEFAULTS before the job's options. stats is
    the first pass's log (stats_path: -passlogfile is it less "-0.log"); keyframes are forced (the chapters'),
    in the last pass only: forced in the first pass too, libvpx leaves them out of the second (a Fallout sample's
    chapter at frame 72 came out a P-frame)."""
    first = settings.rate_control is RateControl.TWO_PASS and pass_number == 1
    argv = [exe, "-hide_banner", "-y", "-f", "yuv4mpegpipe", "-i", "-", "-c:v", LIBVPX[settings.encoder]]
    argv += ["-frames:v", str(frames)] if frames else []
    argv += ["-cpu-used", settings.preset] if settings.preset else []
    if settings.rate_control is RateControl.CRF:
        argv += ["-crf", str(round(settings.crf)), "-b:v", VP8_CRF_CAP if settings.encoder is Encoder.VP8 else "0"]
    else:
        argv += ["-b:v", f"{settings.bitrate_kbps}k"]
    if settings.rate_control is RateControl.TWO_PASS:
        if pass_number not in (1, 2) or stats is None:
            raise ValueError("A two-pass encode needs pass_number 1 or 2 and a stats file")
        argv += ["-pass", str(pass_number), "-passlogfile", str(stats).removesuffix("-0.log")]
    argv += color_args(color, settings)
    if keyframes and not first:
        argv += ["-force_key_frames", "expr:" + "+".join(f"eq(n,{n})" for n in keyframes)]
    argv += _options(VP9_DEFAULTS if settings.encoder is Encoder.VP9 else {}, "-")
    argv += _options(settings.options, "-")
    if settings.extra.strip():
        argv += shlex.split(settings.extra, posix=False)
    argv += ["-an", "-f", "null" if first else "ivf", str(output)]
    return argv


def svtav1_command(
    exe: str,
    settings: EncoderSettings,
    *,
    output: Path,
    frames: int | None = None,
    pass_number: int | None = None,
    stats: Path | None = None,
    color: VideoColor | None = None,
    keyframes: Sequence[int] = (),
) -> list[str]:
    """A SvtAv1EncApp run reading y4m from stdin, as StaxRip's SVT-AV1 encoder writes it: --rc 0 --crf for
    constant quality, --rc 1 --tbr (VBR) for a bitrate, --pass / --stats for two passes, --progress 2 (the
    progress lines progress() reads). The y4m gives the size, frame rate and bit depth. keyframes (the chapters')
    are forced in CRF only (forces_keyframes)."""
    argv = [exe, "--input", "-"]
    argv += ["--frames", str(frames)] if frames else []
    argv += ["--preset", settings.preset] if settings.preset else []
    argv += ["--tune", settings.tune] if settings.tune else []
    if settings.rate_control is RateControl.CRF:
        argv += ["--rc", "0", "--crf", f"{settings.crf:g}"]
    else:
        argv += ["--rc", "1", "--tbr", str(settings.bitrate_kbps)]
    if settings.rate_control is RateControl.TWO_PASS:
        if pass_number not in (1, 2) or stats is None:
            raise ValueError("A two-pass encode needs pass_number 1 or 2 and a stats file")
        argv += ["--pass", str(pass_number), "--stats", str(stats)]
    argv += color_args(color, settings)
    if keyframes and forces_keyframes(settings):
        argv += ["--force-key-frames", ",".join(f"{n}f" for n in keyframes)]
    argv += ["--progress", "2"]
    argv += _options(settings.options)
    if settings.extra.strip():
        argv += shlex.split(settings.extra, posix=False)
    argv += ["--output", str(output)]
    return argv


def issues(settings: EncoderSettings, video: VideoInfo | None, chapters: bool = False) -> list[Issue]:
    """What a VP8 / VP9 / SVT-AV1 encode can't do as set. VP8 / VP9: VP8 is 8-bit only, the preset is -cpu-used (a
    number), VP8 at -cpu-used 4 and up puts keyframes on every 2nd-3rd frame after a scene cut (a Fallout sample:
    69-73 of 200 at 4-5, 3 at 0-3), and an HDR10 source's mastering display and light levels aren't carried (the
    transfer and primaries are). SVT-AV1: 8 or 10-bit, its preset and CRF ranges, and with chapters (the job makes
    them) a bitrate can't force their keyframes; its 2-pass undershoots a target size."""
    if settings.encoder is Encoder.SVTAV1:
        return _svtav1_issues(settings, chapters)
    if not settings.encoder.libvpx:
        return []
    name, out = settings.encoder.label, []
    if settings.encoder is Encoder.VP8 and settings.depth != 8:
        out.append(Issue(Severity.BLOCK, "video.vp8_depth", "VP8 is 8-bit only: set the bit depth to 8"))
    if settings.preset and not settings.preset.removeprefix("-").isdigit():
        out.append(
            Issue(
                Severity.BLOCK,
                "video.vpx_preset",
                f"{name}'s preset is ffmpeg's -cpu-used, a number (0 slowest): {settings.preset!r} isn't one",
            )
        )
    elif settings.encoder is Encoder.VP8 and settings.preset and int(settings.preset) >= 4:
        out.append(
            Issue(
                Severity.WARN,
                "video.vp8_speed",
                f"VP8 at -cpu-used {settings.preset} puts a keyframe on every 2nd-3rd frame after a scene cut: "
                "3 or below keeps them to the cuts",
            )
        )
    color = video.color if video is not None else None
    if settings.source_color and color is not None and (color.master_display or color.max_cll or color.max_fall):
        out.append(
            Issue(
                Severity.WARN,
                "video.vpx_hdr10",
                f"{name} doesn't carry the source's HDR10 mastering display and light levels yet: the encode is "
                "tagged with its transfer and primaries only",
            )
        )
    return out


def _svtav1_issues(settings: EncoderSettings, chapters: bool) -> list[Issue]:
    out = []
    if settings.depth not in (8, 10):
        out.append(Issue(Severity.BLOCK, "video.svtav1_depth", "SVT-AV1 encodes 8 or 10-bit: set the bit depth to one"))
    try:
        preset_ok = not settings.preset or int(settings.preset) in SVTAV1_PRESETS
    except ValueError:
        preset_ok = False
    if not preset_ok:
        out.append(
            Issue(
                Severity.BLOCK,
                "video.svtav1_preset",
                f"SVT-AV1's preset is a number from -1 to 13 (13 fastest): {settings.preset!r} isn't one",
            )
        )
    low, high = SVTAV1_CRF
    if settings.rate_control is RateControl.CRF and not low <= settings.crf <= high:
        out.append(
            Issue(
                Severity.BLOCK, "video.svtav1_crf", f"SVT-AV1's CRF goes from {low} to {high}: {settings.crf:g} isn't"
            )
        )
    if chapters and not forces_keyframes(settings):
        out.append(
            Issue(
                Severity.WARN,
                "video.svtav1_keyframes",
                "SVT-AV1 forces keyframes in CRF only: with a bitrate, the chapters don't start on one",
            )
        )
    if settings.rate_control is RateControl.TWO_PASS and settings.target_mb is not None:
        out.append(
            Issue(
                Severity.WARN,
                "video.svtav1_target",
                "SVT-AV1's 2-pass comes in under its bitrate (a Fallout sample: 27% under, as with its own --passes 2): "
                "the file will be smaller than the target size",
            )
        )
    return out


def _tail(line: str) -> str:
    """A tool's line without the "[tool] " the pipeline puts before it."""
    return line.split("] ", 1)[-1]


def progress(line: str, frames: int | None = None) -> float | None:
    """Fraction done (0..1) from one line of encoder or vspipe output, if it carries one."""
    if m := _PERCENT.search(line):
        return float(m.group(1)) / 100
    tail = _tail(line)
    m = _VSPIPE_FRAMES.search(line) or _SVT_FRAMES.match(tail)
    if m and m.group(2):  # SvtAv1EncApp leaves the total out when it doesn't know it
        total = int(m.group(2))
        return int(m.group(1)) / total if total else None
    if frames and (m := _X265_FRAMES.match(tail) or _FFMPEG_FRAMES.match(tail) or _SVT_FRAMES.match(tail)):
        return int(m.group(1)) / frames
    return None


def progress_line(line: str) -> bool:
    """Whether a line of encoder or vspipe output is a progress line (one every frame or two), with or without
    a fraction progress() can read from it."""
    tail = _tail(line)
    return bool(
        _PERCENT.search(line)
        or _VSPIPE_FRAMES.search(line)
        or _X265_FRAMES.match(tail)
        or _FFMPEG_FRAMES.match(tail)
        or _SVT_FRAMES.match(tail)
    )


def rate(line: str) -> tuple[float | None, int | None]:
    """Frames per second and the encoder's own time left (seconds) from a progress line (progress_line), where it
    prints them. Only for progress lines: an info line like "1920x1080 fps 24/1" isn't one. vspipe's lines give
    neither: it reads ahead of the encoder, so its fps isn't the encode's. ffmpeg gives no time left. SvtAv1EncApp
    gives frames a minute below one a second."""
    if _VSPIPE_FRAMES.search(line):
        return None, None
    if m := _FFMPEG_FRAMES.match(_tail(line)):
        return float(m.group(2)), None
    fps = float(m.group(1)) if (m := _FPS.search(line)) else None
    if m := _SVT_FRAMES.match(_tail(line)):  # its "fpm" below a frame a second
        fps = float(m.group(3)) / (60 if m.group(4) == "m" else 1)
    eta = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) if (m := _ETA.search(line)) else None
    return fps, eta
