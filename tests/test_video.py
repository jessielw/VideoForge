"""Video: script generation, encoder command lines, auto-crop, and the real VapourSynth + encoders.

The integration tests make a small letterboxed MKV with ffmpeg and use the plugins
in tools/vs-plugins and the encoders in tools/; they skip when those are missing.
"""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from pathlib import Path
import shutil
import subprocess

import numpy as np
import pytest

from videoforge.core.config import PROJECT_ROOT
from videoforge.core.models import VideoColor, VideoInfo
from videoforge.core.plan_io import from_json, to_json
from videoforge.core.video import crop as autocrop, vs as vsx
from videoforge.core.video.encoders import (
    VP8_CRF_CAP,
    encoder_command,
    issues as encoder_issues,
    output_name,
    progress,
    progress_line,
    qpfile_frames,
    rate,
    stats_path,
    vspipe_command,
)
from videoforge.core.video.filters import PRESETS
from videoforge.core.video.script import build_script, script_parts
from videoforge.core.video.settings import (
    Crop,
    Encoder,
    EncoderSettings,
    FilterCategory,
    FilterStep,
    RateControl,
    Resize,
    SourceFilter,
    VideoSettings,
    ar_error,
    fit_height,
    fit_width,
)

TOOLS = PROJECT_ROOT / "tools"
PLUGINS = TOOLS / "vs-plugins"
FFMPEG = shutil.which("ffmpeg")
vsx.configure(PLUGINS)  # before any clip loads in this test process
INVERT = FilterStep(FilterCategory.CUSTOM, "Invert", "clip = clip.std.Invert()")


# --- script -------------------------------------------------------------------------


def test_script_layout():
    s = VideoSettings(crop=Crop(0, 22, 0, 22), resize=Resize(1280, 544), filters=[INVERT])
    src, work = Path("D:/Show/E01.mkv"), Path("D:/Show/E01.mkv_tmp")
    text = build_script(s, src, work, depth=10)
    lines = text.splitlines()
    index = work / "E01.mkv.ffindex"
    assert lines[2] == f"src = core.ffms2.Source({str(src)!r}, cachefile={str(index)!r})"  # FFMS2 is the default
    assert "clip = core.std.Crop(clip, left=0, right=0, top=22, bottom=22)" in lines
    assert "clip = core.resize.Spline36(clip, width=1280, height=544)" in lines
    assert "clip = clip.std.Invert()" in lines
    assert "bits_per_sample=10" in text and lines[-1] == "clip.set_output()"
    compile(text, "<script>", "exec")

    source_only = build_script(s, Path("a.mkv"), Path("w"), stage="source")
    assert "Crop" not in source_only and source_only.endswith("clip = src\nclip.set_output()\n")
    custom = build_script(
        VideoSettings(source_filter=SourceFilter.LSMASH, custom="clip = src[10:20]"), Path("a.mkv"), Path("w")
    )
    assert "lsmas.LWLibavSource" in custom and "clip = src[10:20]" in custom and "Crop" not in custom


def test_script_parts_split_the_editable_body():
    s = VideoSettings(crop=Crop(0, 22, 0, 22), filters=[INVERT])
    head, body, tail = script_parts(s, Path("a.mkv"), Path("w"), depth=10)
    assert head[-1] == "clip = src" and tail[-1] == "clip.set_output()"
    assert body == ["clip = core.std.Crop(clip, left=0, right=0, top=22, bottom=22)", "clip = clip.std.Invert()"]
    assert "\n".join(head + body + tail) + "\n" == build_script(s, Path("a.mkv"), Path("w"), depth=10)
    s.custom = "\n  clip = src[1:]\n\n"
    assert script_parts(s, Path("a.mkv"), Path("w"))[1] == ["  clip = src[1:]"]
    assert script_parts(s, Path("a.mkv"), Path("w"), stage="source")[1:] == ([], ["clip.set_output()"])


def test_crop_stage_is_the_output_with_its_margins_back():
    s = VideoSettings(crop=Crop(0, 22, 0, 20), resize=Resize(1280, 544), filters=[INVERT])
    s.filters = [s.filters[0], INVERT, s.filters[1]]  # crop, invert, resize
    body = script_parts(s, Path("a.mkv"), Path("w"), stage="crop")[1]
    assert body == [
        "_vf_pre = clip",
        "clip = core.std.Crop(clip, left=0, right=0, top=22, bottom=20)",
        "clip = clip.std.Invert()",  # the resize after the crop is left out: the lines are in uncropped pixels
        "from videoforge.core.video.vs import crop_view as _vf_crop_view",
        "clip = _vf_crop_view(_vf_pre, clip, left=0, top=22, right=0, bottom=20)",
    ]
    s.filters = [s.filters[2], s.filters[0], s.filters[1]]  # a resize before the crop stays
    assert script_parts(s, Path("a.mkv"), Path("w"), stage="crop")[1][0].startswith("clip = core.resize.Spline36")
    s.custom = "clip = src"
    assert script_parts(s, Path("a.mkv"), Path("w"), stage="crop")[1] == ["clip = src"]


@pytest.mark.parametrize(
    ("script", "line", "message"),
    [
        ("a = 1\nb = (\n", 2, "SyntaxError"),
        ("a = 1\n\nb = undefined_name\n", 3, "NameError: name 'undefined_name' is not defined"),
        ("def f():\n    raise ValueError('bad')\n\nf()\n", 2, "ValueError: bad"),  # the innermost script line
        ("clip = 1\n", None, "must leave a video clip"),
    ],
)
def test_script_errors_carry_the_line(script, line, message):
    with pytest.raises(vsx.ScriptError) as e:
        vsx.load_clip(script)
    assert e.value.line == line and message in e.value.message
    assert str(e.value).startswith(f"Line {line}: ") if line else str(e.value) == e.value.message


# --- encoders -----------------------------------------------------------------------


def test_x264_two_pass_and_options():
    s = EncoderSettings(
        rate_control=RateControl.TWO_PASS,
        bitrate_kbps=10000,
        preset="veryslow",
        options={"ref": "4", "no-fast-pskip": "", "--aq-mode": "3"},
        extra="--aq-strength 0.9",
    )
    argv = encoder_command(
        "x264", s, frames=100, output=Path("v.264"), pass_number=2, stats=Path("s.log"), qpfile=Path("c.qpf")
    )
    assert argv[:5] == ["x264", "--demuxer", "y4m", "--frames", "100"]
    assert argv[argv.index("--bitrate") + 1] == "10000" and argv[argv.index("--pass") + 1] == "2"
    assert ["--ref", "4", "--no-fast-pskip", "--aq-mode", "3"] == argv[
        argv.index("--ref") : argv.index("--aq-mode") + 2
    ]
    assert argv[-5:] == ["--aq-strength", "0.9", "--output", "v.264", "-"]
    assert argv[argv.index("--qpfile") + 1] == "c.qpf"
    with pytest.raises(ValueError):
        encoder_command("x264", s, frames=1, output=Path("v.264"))
    assert output_name(s) == "video.264"


def test_x265_crf_depth():
    s = EncoderSettings(encoder=Encoder.X265, crf=20.5, depth=10)
    argv = encoder_command("x265", s, frames=10, output=Path("v.hevc"))
    assert argv[:4] == ["x265", "--y4m", "--frames", "10"]
    assert argv[argv.index("--crf") + 1] == "20.5" and argv[argv.index("--output-depth") + 1] == "10"
    assert output_name(s) == "video.hevc"


def test_encode_keeps_the_pixel_aspect():
    """The encoder is told the encode's pixel aspect (vspipe's y4m has none): an anamorphic source's when
    it isn't resized, square after a keep-AR resize, the shape undoing a fixed size's stretch otherwise."""
    dvd = Fraction(32, 27)
    s = VideoSettings(crop=Crop(8, 0, 8, 0))
    assert s.output_sar(720, 480, dvd) == dvd  # a crop keeps the pixels' shape
    s.resize = Resize(854, 480, keep_ar=True)
    assert s.output_sar(720, 480, dvd) == 1
    s.resize = Resize(704, 480)  # the size it went in at: still anamorphic
    assert s.output_sar(720, 480, dvd) == dvd
    s.resize = Resize(640, 480)  # squeezed
    assert s.output_sar(720, 480, dvd) == dvd * 704 / 640
    assert VideoSettings(crop=Crop(0, 140, 0, 140), resize=Resize(1280, 534)).output_sar(1920, 1080) == 1  # 0.1% off
    assert VideoSettings(custom="clip = clip").output_sar(720, 480, dvd) is None

    enc = EncoderSettings(extra="--sar 1:1")
    argv = encoder_command("x264", enc, output=Path("v.264"), sar=dvd)
    assert argv[argv.index("--sar") + 1] == "32:27" and argv.index("--sar") < argv.index("1:1")  # the user's wins
    assert "--sar" not in encoder_command("x265", EncoderSettings(Encoder.X265), output=Path("v.hevc"), sar=Fraction(1))


def test_vp9_through_ffmpeg(tmp_path):
    """VP9 runs as StaxRip's ffmpeg encoder writes it: -crf with -b:v 0, the preset as -cpu-used, its VP9
    defaults before the job's options (which win: ffmpeg takes the last), the chapters' keyframes forced, into
    an IVF."""
    s = EncoderSettings(Encoder.VP9, crf=31.4, preset="2", depth=10, options={"tile-columns": "2"}, extra="-g 240")
    color = VideoColor("bt2020", "smpte2084", "bt2020nc", "limited", 2, P3_1000, 1000, 400)
    argv = encoder_command("ffmpeg", s, frames=48, output=Path("v.ivf"), color=color, keyframes=[0, 24])
    assert argv[:9] == ["ffmpeg", "-hide_banner", "-y", "-f", "yuv4mpegpipe", "-i", "-", "-c:v", "libvpx-vp9"]
    assert argv[argv.index("-frames:v") + 1] == "48" and argv[argv.index("-cpu-used") + 1] == "2"
    assert argv[argv.index("-crf") : argv.index("-crf") + 4] == ["-crf", "31", "-b:v", "0"]  # libvpx takes whole ones
    assert argv[argv.index("-color_trc") + 1] == "smpte2084" and argv[argv.index("-colorspace") + 1] == "bt2020nc"
    assert argv[argv.index("-color_range") + 1] == "tv" and "--master-display" not in argv
    assert argv[argv.index("-force_key_frames") + 1] == "expr:eq(n,0)+eq(n,24)"
    tiles = [i for i, a in enumerate(argv) if a == "-tile-columns"]
    assert [argv[i + 1] for i in tiles] == ["6", "2"] and argv[argv.index("-row-mt") + 1] == "1"
    assert argv[-6:] == ["-g", "240", "-an", "-f", "ivf", "v.ivf"]
    assert "--sar" not in argv and output_name(s) == "video.ivf"

    two = replace(s, rate_control=RateControl.TWO_PASS, bitrate_kbps=4000)
    stats = stats_path(tmp_path, two)
    assert stats.name == "video.stats-0.log"  # what ffmpeg writes for -passlogfile video.stats
    first = encoder_command("ffmpeg", two, output=Path("NUL"), pass_number=1, stats=stats, keyframes=[0, 24])
    assert first[first.index("-b:v") + 1] == "4000k" and first[first.index("-pass") + 1] == "1"
    assert first[first.index("-passlogfile") + 1] == str(tmp_path / "video.stats")
    assert first[-3:] == ["-f", "null", "NUL"]
    # forced in pass 1 too, libvpx leaves them out of pass 2: the last pass only
    assert "-force_key_frames" not in first
    second = encoder_command("ffmpeg", two, output=Path("v.ivf"), pass_number=2, stats=stats, keyframes=[0, 24])
    assert second[second.index("-force_key_frames") + 1] == "expr:eq(n,0)+eq(n,24)"
    with pytest.raises(ValueError):
        encoder_command("ffmpeg", two, output=Path("v.ivf"))
    assert stats_path(tmp_path, EncoderSettings()).name == "video.stats"


def test_vp8_and_issues():
    vp8 = EncoderSettings(Encoder.VP8, preset="", rate_control=RateControl.ABR, bitrate_kbps=2500)
    argv = encoder_command("ffmpeg", vp8, output=Path("v.ivf"), color=VideoColor("bt709", "bt470bg", "gbr", "full"))
    assert argv[argv.index("-c:v") + 1] == "libvpx" and argv[argv.index("-b:v") + 1] == "2500k"
    assert "-cpu-used" not in argv and "-tile-columns" not in argv  # VP9's defaults only
    # ffmpeg's own names for these
    assert argv[argv.index("-color_trc") + 1] == "gamma28" and argv[argv.index("-colorspace") + 1] == "rgb"
    assert argv[argv.index("-color_range") + 1] == "pc"

    # -b:v 0 is ffmpeg's 256 kbit/s cap on VP8's constrained quality: a ceiling it doesn't reach instead
    crf = encoder_command("ffmpeg", replace(vp8, rate_control=RateControl.CRF, crf=20), output=Path("v.ivf"))
    assert crf[crf.index("-crf") : crf.index("-crf") + 4] == ["-crf", "20", "-b:v", VP8_CRF_CAP]

    assert encoder_issues(vp8, None) == []
    codes = [i.code for i in encoder_issues(replace(vp8, depth=10, preset="slower"), None)]
    assert codes == ["video.vp8_depth", "video.vpx_preset"]
    assert [i.code for i in encoder_issues(replace(vp8, preset="4"), None)] == ["video.vp8_speed"]
    assert encoder_issues(replace(vp8, preset="3"), None) == []
    assert encoder_issues(replace(vp8, encoder=Encoder.VP9, preset="5"), None) == []  # VP8's alone
    hdr10 = VideoInfo(
        3840, 2160, color=VideoColor("bt2020", "smpte2084", "bt2020nc", "limited", None, P3_1000, 1000, 400)
    )
    assert [i.code for i in encoder_issues(replace(vp8, encoder=Encoder.VP9, preset="-3"), hdr10)] == [
        "video.vpx_hdr10"
    ]
    assert encoder_issues(replace(vp8, encoder=Encoder.VP9, source_color=False), hdr10) == []
    assert encoder_issues(EncoderSettings(Encoder.X265, depth=10, preset="slower"), hdr10) == []


def test_svtav1_command(tmp_path):
    """SVT-AV1 runs as StaxRip's SvtAv1EncApp: --rc 0 --crf (quarter steps), --progress 2 before the job's options,
    the source's colour as H.273 code points with the HDR10 mastering display in plain numbers, the chapters'
    keyframes forced (CRF only), into an IVF."""
    s = EncoderSettings(Encoder.SVTAV1, crf=27.25, preset="6", tune="0", depth=10, options={"film-grain": "8"})
    color = VideoColor("bt2020", "smpte2084", "bt2020nc", "", 2, P3_1000, 1000, 400)
    argv = encoder_command("SvtAv1EncApp", s, frames=48, output=Path("v.ivf"), color=color, keyframes=[0, 24])
    assert argv[:5] == ["SvtAv1EncApp", "--input", "-", "--frames", "48"]
    assert argv[argv.index("--preset") + 1] == "6" and argv[argv.index("--tune") + 1] == "0"
    assert argv[argv.index("--rc") : argv.index("--rc") + 4] == ["--rc", "0", "--crf", "27.25"]
    assert (
        argv[argv.index("--color-primaries") + 1] == "9" and argv[argv.index("--transfer-characteristics") + 1] == "16"
    )
    assert (
        argv[argv.index("--matrix-coefficients") + 1] == "9" and argv[argv.index("--chroma-sample-position") + 1] == "2"
    )
    assert argv[argv.index("--color-range") + 1] == "0"  # an HDR10 source's range is limited unless it says
    md = "G(0.265,0.69)B(0.15,0.06)R(0.68,0.32)WP(0.3127,0.329)L(1000,0.005)"
    assert argv[argv.index("--mastering-display") + 1] == md
    assert argv[argv.index("--content-light") + 1] == "1000,400"
    assert argv[argv.index("--force-key-frames") + 1] == "0f,24f"
    assert argv.index("--progress") < argv.index("--film-grain") and argv[-2:] == ["--output", "v.ivf"]
    assert "--qpfile" not in encoder_command("SvtAv1EncApp", s, output=Path("v.ivf"), qpfile=tmp_path / "c.qpf")
    assert output_name(s) == "video.ivf" and stats_path(tmp_path, s).name == "video.stats"

    # a bitrate is VBR; SvtAv1EncApp refuses forced keyframes with it
    two = replace(s, rate_control=RateControl.TWO_PASS, bitrate_kbps=4000)
    first = encoder_command("SvtAv1EncApp", two, output=Path("NUL"), pass_number=1, stats=Path("s"), keyframes=[0, 24])
    assert first[first.index("--rc") : first.index("--rc") + 4] == ["--rc", "1", "--tbr", "4000"]
    assert first[first.index("--pass") : first.index("--pass") + 4] == ["--pass", "1", "--stats", "s"]
    assert "--force-key-frames" not in first and "--crf" not in first
    assert first[first.index("--undershoot-pct") + 1] == "5"  # SVT-AV1's 25 came in 26-33% under --tbr
    own = encoder_command(
        "SvtAv1EncApp", replace(two, extra="--undershoot-pct 10"), output=Path("v.ivf"), pass_number=2, stats=Path("s")
    )
    assert own.count("--undershoot-pct") == 1 and own[own.index("--undershoot-pct") + 1] == "10"
    abr = encoder_command("SvtAv1EncApp", replace(two, rate_control=RateControl.ABR), output=Path("v.ivf"))
    assert "--undershoot-pct" not in abr
    with pytest.raises(ValueError):
        encoder_command("SvtAv1EncApp", two, output=Path("v.ivf"))
    # SDR: type 0 chroma ("left") is AV1's vertical; a stated range with no HDR10
    sdr = encoder_command(
        "SvtAv1EncApp", s, output=Path("v.ivf"), color=VideoColor("bt709", "bt709", "bt709", "full", 0)
    )
    assert sdr[sdr.index("--chroma-sample-position") + 1] == "1" and sdr[sdr.index("--color-range") + 1] == "1"
    assert "--mastering-display" not in sdr and "--content-light" not in sdr
    assert "--color-range" not in encoder_command("SvtAv1EncApp", s, output=Path("v.ivf"), color=VideoColor("bt709"))


def test_svtav1_issues():
    s = EncoderSettings(Encoder.SVTAV1, crf=30, preset="4", depth=10)
    assert encoder_issues(s, None, chapters=True) == []
    codes = [i.code for i in encoder_issues(replace(s, depth=12, preset="slower", crf=80), None)]
    assert codes == ["video.svtav1_depth", "video.svtav1_preset", "video.svtav1_crf"]
    assert [i.code for i in encoder_issues(replace(s, preset="14"), None)] == ["video.svtav1_preset"]
    assert encoder_issues(replace(s, preset="-1"), None) == encoder_issues(replace(s, preset=""), None) == []
    abr = replace(s, rate_control=RateControl.ABR, crf=99)  # the CRF isn't used
    assert [i.code for i in encoder_issues(abr, None, chapters=True)] == ["video.svtav1_keyframes"]
    assert encoder_issues(abr, None) == []
    assert encoder_issues(replace(s, rate_control=RateControl.TWO_PASS, target_mb=500), None) == []
    hdr10 = VideoInfo(3840, 2160, color=VideoColor("bt2020", "smpte2084", "bt2020nc", "limited", None, P3_1000, 1000))
    assert encoder_issues(s, hdr10) == []  # AV1 carries HDR10


def test_qpfile_frames(tmp_path):
    qpf = tmp_path / "c.qpf"
    assert qpfile_frames(qpf) == []  # not written yet
    qpf.write_text("0 I\n1234 I -1\n\n5678 K\n", encoding="utf-8")
    assert qpfile_frames(qpf) == [0, 1234, 5678]


def test_progress_lines():
    assert progress("[x264] [ 12.5%] 125/1000 frames, 30.1 fps, 9000 kb/s, eta 0:00:29") == 0.125
    assert progress("[x265] [50.0%] 500/1000 frames, 4.12 fps") == 0.5
    assert progress("[vspipe] Frame: 50/200 (12.3 fps)") == 0.25
    assert progress("[x265] 250 frames: 4.1 fps, 900 kb/s", frames=1000) == 0.25
    assert progress("[x264] encoded 1000 frames") is None
    # Patman's x264 / x265 mods
    patman = "[x264] [69.9%] 1006/1440 Frames @ 201.8 FPS | 5878.2 kb/s | 0:00:04 [-0:01:02] | 30.80 MB [44.09 MB]  "
    assert progress(patman) == pytest.approx(0.699)
    assert progress("[x265] 8 Frames @ 13.61 FPS | 48387 kb/s | 2.02 MB  ", frames=80) == 0.1
    ffmpeg = "[ffmpeg] frame=  120 fps= 23 q=0.0 size=    1024KiB time=00:00:05.00 bitrate=1677.7kbits/s speed=0.96x"
    assert progress(ffmpeg, frames=480) == 0.25 and progress(ffmpeg) is None and progress_line(ffmpeg)
    assert not progress_line("[ffmpeg] size=    1024KiB time=00:00:05.00 bitrate= 192.0kbits/s speed=40x")  # audio
    # SvtAv1EncApp --progress 2 (colours stripped); without the total when it doesn't know the length
    svt = "[svtav1encapp] Encoding:  360/1440 Frames @ 111.89 fps | 11863.40 kb/s | Size: 88.98 MB [88.98 MB] | Time: 0:00:13 [-0:00:39] "
    assert progress(svt) == 0.25 and progress_line(svt)
    assert (
        progress("[svtav1encapp] Encoding:  360 Frames @ 149.40 fps | 1697.27 kb/s | Size: 12.72 MB", frames=720) == 0.5
    )
    assert progress("[svtav1encapp] Encoding:  360 Frames @ 149.40 fps | 1697.27 kb/s") is None
    assert not progress_line("[svtav1encapp] Svt[info]: SVT [config]: preset / tune / pred struct : 8 / PSNR")


def test_rate_lines():
    assert rate("[x264] [ 12.5%] 125/1000 frames, 30.1 fps, 9000 kb/s, eta 1:00:29") == (30.1, 3629)
    assert rate("[x265] [50.0%] 500/1000 frames, 4.12 fps") == (4.12, None)
    assert rate("[x264] [69.9%] 1006/1440 Frames @ 201.8 FPS | 5878.2 kb/s | 0:00:04 [-0:01:02] | 30.80 MB") == (
        201.8,
        62,
    )
    assert rate("[x265] 8 Frames @ 13.61 FPS | 48387 kb/s | 2.02 MB  ") == (13.61, None)
    assert rate("[vspipe] Frame: 50/200 (12.3 fps)") == (None, None)  # it reads ahead: not the encode's speed
    assert rate("[vspipe] Frame: 50/200") == (None, None)
    assert rate("[ffmpeg] frame=  120 fps= 23.5 q=0.0 size=    1024KiB time=00:00:05.00") == (23.5, None)
    svt = "[svtav1encapp] Encoding:  360/1440 Frames @ 111.89 fps | 11863.40 kb/s | Size: 88.98 MB [88.98 MB] | Time: 0:00:13 [-0:00:39] "
    assert rate(svt) == (111.89, 39)
    assert rate("[svtav1encapp] Encoding:    3/1440 Frames @ 30.00 fpm | 900.0 kb/s | Time: 0:00:06 [-0:47:54]") == (
        0.5,
        2874,
    )


# --- auto-crop ----------------------------------------------------------------------


def letterboxed(h=180, w=320, top=22, bottom=22, left=0, right=0) -> np.ndarray:
    rgb = np.full((h, w, 3), 128, np.uint8)
    rgb[:top] = rgb[h - bottom :] = 0
    rgb[:, :left] = 0
    if right:
        rgb[:, w - right :] = 0
    return rgb


def test_frame_borders_and_combine():
    assert autocrop.frame_borders(letterboxed(left=10, right=6)) == Crop(10, 22, 6, 22)
    dark_frame = np.zeros((180, 320, 3), np.uint8)  # a fade: everything up to the quarter limit
    assert autocrop.frame_borders(dark_frame) == Crop(80, 45, 80, 45)
    crops = [autocrop.frame_borders(f) for f in (letterboxed(top=23), dark_frame, letterboxed(top=25))]
    assert autocrop.combine(crops) == Crop(0, 22, 0, 22)  # smallest per side, rounded to mod 2
    assert autocrop.sample_frames(1000, 4) == [162, 387, 612, 837]
    assert autocrop.sample_frames(3, 10) == [0, 1, 2]


def to_yuv420(rgb: np.ndarray, bits: int, matrix: int, full: bool) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """An RGB frame as YUV 4:2:0 planes (chroma: the top-left sample of each 2x2)."""
    kr, kb = autocrop._KR_KB[matrix]
    x = rgb.astype(np.float64) / 255
    y = kr * x[..., 0] + (1 - kr - kb) * x[..., 1] + kb * x[..., 2]
    cb, cr = (x[..., 2] - y) / (2 * (1 - kb)), (x[..., 0] - y) / (2 * (1 - kr))
    peak, s = (1 << bits) - 1, 1 << (bits - 8)
    ys, cs, yo = (peak, peak, 0) if full else (219 * s, 224 * s, 16 * s)
    dtype = np.uint8 if bits == 8 else np.uint16
    to = lambda a, scale, off: np.round(a * scale + off).astype(dtype)
    return to(y, ys, yo), to(cb[::2, ::2], cs, 1 << (bits - 1)), to(cr[::2, ::2], cs, 1 << (bits - 1))


@pytest.mark.parametrize("bits,matrix,full", [(8, 1, False), (10, 9, False), (8, 6, True), (10, 1, True)])
def test_yuv_borders_judge_like_rgb(bits, matrix, full):
    """Read straight from YUV, a frame gets the RGB lightness verdict: dark navy and dark red picture
    is picture (luma alone would call it black), black bars are bars, at any depth, matrix and range."""
    for picture in ((0, 0, 40), (45, 0, 0), (128, 128, 128)):
        rgb = letterboxed(left=10, right=6)
        rgb[22:158, 10:314] = picture
        assert (
            autocrop.yuv_borders(*to_yuv420(rgb, bits, matrix, full), bits=bits, matrix=matrix, full_range=full)
            == autocrop.frame_borders(rgb)
            == Crop(10, 22, 6, 22)
        ), picture
    dark = np.zeros((180, 320, 3), np.uint8)
    assert autocrop.yuv_borders(
        *to_yuv420(dark, bits, matrix, full), bits=bits, matrix=matrix, full_range=full
    ) == Crop(80, 45, 80, 45)


def test_detect_reads_the_frames_range():
    """Y = 16 bars are black in limited range (and when unset) but not in full range (16/255 is past the
    threshold): detect reads _Range from each frame."""
    import vapoursynth as vs

    core = vs.core
    bar = core.std.BlankClip(width=320, height=22, format=vs.YUV420P8, color=[16, 128, 128], length=30)
    picture = core.std.BlankClip(width=320, height=136, format=vs.YUV420P8, color=[30, 160, 120], length=30)
    clip = core.std.StackVertical([bar, picture, bar])
    assert autocrop.detect(clip) == Crop(0, 22, 0, 22)  # no range set
    assert autocrop.detect(clip.std.SetFrameProps(_Range=int(vs.RANGE_LIMITED))) == Crop(0, 22, 0, 22)
    assert autocrop.detect(clip.std.SetFrameProps(_Range=int(vs.RANGE_FULL))) == Crop()


# --- filter chain ---------------------------------------------------------------------


def test_chain_order_makes_the_script():
    """The steps run in their chain order; the crop and resize steps are always there, made from crop/resize."""
    grain = FilterStep(FilterCategory.GRAIN, "Grain", "clip = grain(clip)")
    field = FilterStep(FilterCategory.FIELD, "IVTC", "clip = ivtc(clip)")
    off = FilterStep(FilterCategory.NOISE, "Off", "clip = off(clip)", enabled=False)
    s = VideoSettings(crop=Crop(0, 22, 0, 22), resize=Resize(1280, 544), filters=[field, grain, off])
    assert [f.category for f in s.filters] == ["field", "crop", "resize", "grain", "noise"]  # put in at their place
    head, body, tail = script_parts(s, Path("a.mkv"), Path("w"))
    assert body == [
        "clip = ivtc(clip)",
        "clip = core.std.Crop(clip, left=0, right=0, top=22, bottom=22)",
        "clip = core.resize.Spline36(clip, width=1280, height=544)",
        "clip = grain(clip)",
    ]
    s.filters = [s.filters[2], s.filters[1]]  # resize before crop
    s.__post_init__()
    assert script_parts(s, Path("a.mkv"), Path("w"))[1][0].startswith("clip = core.resize")
    assert s.output_size(1920, 1080) == (1280, 500)
    s.resize = None
    assert script_parts(s, Path("a.mkv"), Path("w"))[1] == [
        "clip = core.std.Crop(clip, left=0, right=0, top=22, bottom=22)"
    ]
    assert s.output_size(1920, 1080) == (1920, 1036)
    dupes = VideoSettings(filters=[*VideoSettings().filters, FilterStep(FilterCategory.CROP, "Crop", enabled=False)])
    assert [f.category for f in dupes.filters] == ["crop", "resize"] and dupes.filters[0].enabled


def test_keep_ar_resize_follows_the_crop():
    """StaxRip's resize: the height follows the width at the display aspect ratio going in (the crop, the
    pixel aspect), both on the mod; a fixed size, a custom body or a resize before the crop is left alone."""
    assert fit_height(1280, 1920, 800) == 534 and fit_height(1280, 1920, 800, mod=8) == 536
    assert fit_width(534, 1920, 800) == 1282
    assert abs(ar_error(1280, 534, 1920, 800)) < 0.2
    assert fit_height(720, 720, 480, Fraction(32, 27)) == 406  # a 16:9 DVD: 405 on mod 2
    assert fit_height(854, 704, 480, Fraction(32, 27)) == 492  # its 704 wide picture, 1.74:1

    s = VideoSettings(crop=Crop(0, 140, 0, 140), resize=Resize(1281, 720, keep_ar=True))
    assert s.fit_resize(1920, 1080) and (s.resize.width, s.resize.height) == (1282, 534)  # the width on the mod
    assert not s.fit_resize(1920, 1080)  # already fitted
    s.crop = Crop()
    assert s.fit_resize(1920, 1080) and s.resize.height == 722
    s.resize.mod = 16
    assert s.fit_resize(1920, 1080) and (s.resize.width, s.resize.height) == (1280, 720)
    s.filters = [s.filters[1], s.filters[0]]  # resize before crop: the source's own aspect
    s.crop = Crop(0, 140, 0, 140)
    assert not s.fit_resize(1920, 1080)
    s.filters.reverse()
    s.custom = "clip = clip"
    assert not s.fit_resize(1920, 1080)
    fixed = VideoSettings(crop=Crop(0, 140, 0, 140), resize=Resize(1280, 720))
    assert not fixed.fit_resize(1920, 1080) and fixed.resize.height == 720
    old = from_json(Resize, {"width": 1280, "height": 544, "kernel": "Spline36"})  # saved before keep_ar
    assert not old.keep_ar and old.mod == 2


def test_old_filters_text_becomes_a_custom_step():
    old = from_json(VideoSettings, {"filters": "clip = clip.std.Invert()", "crop": {"top": 2}})
    assert [(f.category, f.script) for f in old.filters] == [
        ("crop", ""),
        ("resize", ""),
        ("custom", "clip = clip.std.Invert()"),
    ]
    assert old.crop == Crop(top=2)
    assert from_json(VideoSettings, {"filters": ""}).filters == VideoSettings().filters
    assert from_json(VideoSettings, to_json(old)) == old  # the new shape reads back as it is


def test_filter_presets():
    """Every preset compiles; a family's variants share one category; names are unique."""
    assert len({p.name for p in PRESETS}) == len(PRESETS)
    for p in PRESETS:
        compile(p.script, p.name, "exec")
        assert "{}" not in p.script and p.category not in (FilterCategory.CROP, FilterCategory.RESIZE)
    families: dict[str, FilterCategory] = {}
    for p in PRESETS:
        assert families.setdefault(p.family, p.category) is p.category


@pytest.mark.parametrize("preset", [p for p in PRESETS if p.script], ids=lambda p: p.name)
def test_filter_presets_run(preset, tmp_path):
    """Each preset runs on 8- and 16-bit video (skipped when its plugin or filter script isn't installed); a file
    to fill in (the burn-in's) is a real SRT."""
    import vapoursynth as vs

    core = vs.core
    srt = tmp_path / "a.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
    script = preset.script.replace("file=r''", f"file={str(srt)!r}")
    for fmt in (vs.YUV420P8, vs.YUV420P16):
        if fmt == vs.YUV420P16 and preset.family == "IVTC (VIVTC)":
            continue  # VFM takes 8-bit only
        clip = core.std.BlankClip(width=640, height=360, format=fmt, length=12, fpsnum=24000, fpsden=1001)
        ns = {"vs": vs, "core": core, "clip": clip}
        try:
            exec(script, ns)  # noqa: S102 - the built-in presets
        except ImportError as e:
            pytest.skip(f"no filter script: {e}")
        except AttributeError as e:
            if "namespace" not in str(e):
                raise
            pytest.skip(f"no plugin: {e}")
        ns["clip"].get_frame(5)


# --- real VapourSynth and encoders ---------------------------------------------------

needs_vs = pytest.mark.skipif(
    FFMPEG is None or not (PLUGINS / "ffms2.dll").exists(), reason="needs ffmpeg and tools/vs-plugins"
)


@pytest.fixture(scope="module")
def clip_file(tmp_path_factory) -> Path:
    """2 s, 24 fps, 320x180 with 22 px black bars top and bottom."""
    out = tmp_path_factory.mktemp("video") / "Movie.mkv"
    subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=duration=2:size=320x136:rate=24",
         "-vf", "pad=320:180:0:22:black", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", str(out)],
        check=True,
    )  # fmt: skip
    return out


@needs_vs
@pytest.mark.parametrize("source_filter", list(SourceFilter))
def test_source_filters_index_into_the_work_dir(clip_file, tmp_path, source_filter):
    script = build_script(VideoSettings(source_filter=source_filter), clip_file, tmp_path)
    info = vsx.clip_info(vsx.load_clip(script))
    assert (info.frames, info.width, info.height, info.fps_num, info.fps_den) == (48, 320, 180, 24, 1)
    assert any(tmp_path.iterdir()), "the index belongs in the work folder"


@needs_vs
def test_ffms2_index_with_progress(clip_file, tmp_path):
    """The index step's FFMS2 index (core/video/ffindex.py): progress lines, read by Source() as it is, kept when valid."""
    import io

    from videoforge.core.pipeline.steps import line_progress
    from videoforge.core.video.ffindex import make_index
    from videoforge.core.video.script import ffms2_index, index_exists

    index = ffms2_index(clip_file, tmp_path)
    out = io.StringIO()
    make_index(clip_file, index, str(PLUGINS / "ffms2.dll"), out)
    lines = out.getvalue().splitlines()
    assert lines[-1] == "ffms2 index progress 100%" and line_progress(lines[0]) is not None
    assert index_exists(clip_file, SourceFilter.FFMS2, tmp_path) and not list(tmp_path.glob("*.partial"))
    written = index.stat().st_mtime_ns
    clip = vsx.load_clip(build_script(VideoSettings(source_filter=SourceFilter.FFMS2), clip_file, tmp_path))
    assert clip.num_frames == 48 and index.stat().st_mtime_ns == written  # Source() took it, didn't index again
    again = io.StringIO()
    make_index(clip_file, index, str(PLUGINS / "ffms2.dll"), again)
    assert again.getvalue() == "ffms2 index: already there\n" and index.stat().st_mtime_ns == written


@needs_vs
def test_autocrop_preview_and_output(clip_file, tmp_path):
    settings = VideoSettings()
    cache = vsx.ClipCache()
    src = cache.get(build_script(settings, clip_file, tmp_path, stage="source"))
    found = autocrop.detect(src, samples=6)
    # Read from YUV (no upsampled chroma bleeding into the bars' last rows): the exact bars.
    assert found == Crop(0, 22, 0, 22)
    settings.crop = Crop(0, 22, 0, 22)
    out = cache.get(build_script(settings, clip_file, tmp_path, depth=10))
    info = vsx.clip_info(out)
    assert (info.width, info.height, info.bits) == (320, 136, 10)
    jpeg = vsx.frame_image(out, 10)
    assert jpeg[:2] == b"\xff\xd8"
    assert vsx.frame_image(src, 0, "png")[:4] == b"\x89PNG"
    assert vsx.frame_rgb(out, 999).shape == (136, 320, 3)  # past the end: the last frame
    assert cache.get(build_script(settings, clip_file, tmp_path, depth=10)) is out
    with pytest.raises(vsx.ScriptError):
        vsx.load_clip("clip = 1")


@needs_vs
def test_crop_view_lines_up_with_the_uncropped_frame():
    import vapoursynth as vs

    core = vs.core
    pre = core.std.BlankClip(format=vs.YUV420P8, width=64, height=48, length=3, color=[100, 128, 128])
    clip = core.std.Crop(pre, left=2, right=4, top=6, bottom=8).std.Invert()
    view = vsx.crop_view(pre, clip, 2, 6, 4, 8)
    assert (view.width, view.height, view.num_frames) == (64, 48, 3)
    f = view.get_frame(1)
    luma = np.asarray(f[0])
    assert f.props[vsx.CROP_VIEW_PROP] == 1
    assert (
        (luma[:6] == 100).all()
        and (luma[-8:] == 100).all()
        and (luma[:, :2] == 100).all()
        and (luma[:, -4:] == 100).all()
    )
    assert (luma[6:-8, 2:-4] == 155).all()  # the filtered output, exactly between the lines
    deeper = core.resize.Point(clip, format=vs.YUV420P16)
    assert vsx.crop_view(pre, deeper, 2, 6, 4, 8).format.id == vs.YUV420P16  # the margins follow the depth
    resized = core.resize.Point(clip, width=32, height=16)
    assert vsx.crop_view(pre, resized, 2, 6, 4, 8) is resized  # can't line up: the output as it is
    assert (
        vsx.crop_view(pre, pre, 0, 0, 0, 0).get_frame(0).props[vsx.CROP_VIEW_PROP] == 1
    )  # no crop: the frame as it is


P3_1000 = "G(13250,34500)B(7500,3000)R(34000,16000)WP(15635,16450)L(10000000,50)"


@needs_vs
@pytest.mark.parametrize("encoder", [Encoder.X264, Encoder.X265])
def test_vspipe_into_encoder(clip_file, tmp_path, encoder):
    from videoforge.core.config import default_vspipe
    from videoforge.core.execute import process

    exe = TOOLS / encoder.value / f"{encoder.value}.exe"
    if not exe.exists():
        pytest.skip(f"needs {exe}")
    vspipe = default_vspipe()
    vsx.ensure_vspipe(vspipe)
    settings = VideoSettings(crop=Crop(0, 22, 0, 22))
    script = tmp_path / "video.vpy"
    script.write_text(build_script(settings, clip_file, tmp_path, depth=8), encoding="utf-8")
    enc = EncoderSettings(encoder=encoder, preset="ultrafast", crf=30)
    out = tmp_path / output_name(enc)
    lines: list[str] = []
    # An HDR10 source's colour (the flags must be ones the real encoder takes, and land in the stream).
    color = VideoColor("bt2020", "smpte2084", "bt2020nc", "limited", 2, P3_1000, 1000, 400)
    argv = encoder_command(str(exe), enc, frames=48, output=out, color=color)
    # vspipe finds the plugins through the environment configure() set for this process.
    process.run([vspipe_command(vspipe, script), argv], lines.append)
    assert out.is_file() and out.stat().st_size > 1000
    assert any(progress(line) is not None for line in lines) or any("frames" in line for line in lines)
    from pymediainfo import MediaInfo

    [video] = [t for t in MediaInfo.parse(str(out)).tracks if t.track_type == "Video"]
    assert (video.color_primaries, video.transfer_characteristics) == ("BT.2020", "PQ")
    if encoder is Encoder.X265:
        assert video.mastering_display_luminance == "min: 0.0050 cd/m2, max: 1000 cd/m2"
        assert video.maximum_content_light_level == "1000 cd/m2"


@needs_vs
@pytest.mark.parametrize("encoder", [Encoder.VP8, Encoder.VP9])
@pytest.mark.parametrize("override", [False, True])
def test_vspipe_into_libvpx_and_mux(clip_file, tmp_path, encoder, override):
    """A real VP8 / VP9 encode (ffmpeg) with the chapters' keyframe forced, muxed to MKV and MP4: both come out
    with the anamorphic pixel aspect and the colour the IVF couldn't hold."""
    from conftest import plan_for, source
    from pymediainfo import MediaInfo

    from videoforge.core.config import default_vspipe
    from videoforge.core.execute import process
    from videoforge.core.execute.mux import mp4box_command, mux_command
    from videoforge.core.video.color import effective_container_color

    mkvmerge, mp4box = TOOLS / "MKVToolNix" / "mkvmerge.exe", shutil.which("MP4Box")
    if FFMPEG is None or not mkvmerge.exists() or mp4box is None:
        pytest.skip("needs ffmpeg, tools/MKVToolNix and MP4Box")
    vspipe = default_vspipe()
    vsx.ensure_vspipe(vspipe)
    depth = 8 if encoder is Encoder.VP8 else 10
    script = tmp_path / "video.vpy"
    script.write_text(build_script(VideoSettings(), clip_file, tmp_path, depth=depth), encoding="utf-8")
    enc = EncoderSettings(encoder=encoder, preset="8", crf=40, depth=depth)
    if override:
        enc.extra = "-color_primaries bt709 -color_trc bt709 -colorspace bt709 -color_range pc"
    out = tmp_path / output_name(enc)
    color = VideoColor("bt2020", "smpte2084", "bt2020nc", "limited")
    lines: list[str] = []
    argv = encoder_command(FFMPEG, enc, frames=48, output=out, color=color, keyframes=[0, 31])
    process.run([vspipe_command(vspipe, script), argv], lines.append)
    assert any(rate(line)[0] is not None for line in lines if "frame=" in line)  # ffmpeg's fps
    probe = subprocess.run(
        [shutil.which("ffprobe") or "ffprobe", "-v", "error", "-select_streams", "v", "-show_entries",
         "stream=codec_name,pix_fmt:frame=key_frame", "-of", "csv=p=0", str(out)],
        capture_output=True, text=True, check=True,
    ).stdout.split()  # fmt: skip
    keys = [n for n, k in enumerate(line for line in probe if line in ("0", "1")) if k == "1"]
    assert keys == [0, 31]
    assert any(line.startswith(encoder.value) for line in probe)

    plan = plan_for(source(name=str(clip_file)))
    plan.source.path, plan.encode_path = clip_file, out
    sar, tags = Fraction(4, 3), effective_container_color(color, enc)
    mkv, mp4 = tmp_path / "out.mkv", tmp_path / "out.mp4"
    process.run([mux_command(plan, {}, mkv, str(mkvmerge), (), sar=sar, color=tags)], lines.append)
    process.run([mp4box_command(plan, {}, mp4, mp4box, (), sar=sar, color=tags)], lines.append)
    for file in (mkv, mp4):
        [video] = [t for t in MediaInfo.parse(str(file)).tracks if t.track_type == "Video"]
        assert video.format == encoder.value.upper() and video.frame_count == "48"
        assert float(video.display_aspect_ratio) == pytest.approx(320 * 4 / 3 / 180, abs=0.003)  # 4:3 pixels
        expected = ("BT.709", "BT.709") if override else ("BT.2020", "PQ")
        assert (video.color_primaries, video.transfer_characteristics) == expected, file
        if override:
            assert video.color_range == "Full", file


@needs_vs
@pytest.mark.parametrize("override", [False, True])
def test_vspipe_into_svtav1_and_mux(clip_file, tmp_path, override):
    """A real SVT-AV1 encode of an HDR10 clip, the chapters' keyframe forced, muxed to MKV and MP4: both come out
    with the anamorphic pixel aspect, the colour and the HDR10 mastering display and light levels (the MKV's from
    the mux's tags, the MP4's from the stream), and the progress lines read."""
    from conftest import plan_for, source
    from pymediainfo import MediaInfo

    from videoforge.core.config import default_vspipe
    from videoforge.core.execute import process
    from videoforge.core.execute.mux import mp4box_command, mux_command
    from videoforge.core.video.color import effective_container_color

    svt = TOOLS / "SvtAv1EncApp" / "SvtAv1EncApp.exe"
    mkvmerge, mp4box = TOOLS / "MKVToolNix" / "mkvmerge.exe", shutil.which("MP4Box")
    if not svt.exists() or FFMPEG is None or not mkvmerge.exists() or mp4box is None:
        pytest.skip("needs tools/SvtAv1EncApp, ffmpeg, tools/MKVToolNix and MP4Box")
    vspipe = default_vspipe()
    vsx.ensure_vspipe(vspipe)
    script = tmp_path / "video.vpy"
    script.write_text(build_script(VideoSettings(), clip_file, tmp_path, depth=10), encoding="utf-8")
    enc = EncoderSettings(encoder=Encoder.SVTAV1, preset="12", crf=40, depth=10)
    if override:
        enc.extra = (
            "--color-primaries 1 --transfer-characteristics 1 --matrix-coefficients 1 --color-range 1 "
            '--content-light 500,100 --mastering-display "G(0.265,0.69)B(0.15,0.06)R(0.68,0.32)'
            'WP(0.3127,0.329)L(2000,0.005)"'
        )
    out = tmp_path / output_name(enc)
    color = VideoColor("bt2020", "smpte2084", "bt2020nc", "limited", 2, P3_1000, 1000, 400)
    lines: list[str] = []
    argv = encoder_command(str(svt), enc, frames=48, output=out, color=color, keyframes=[0, 31])
    process.run([vspipe_command(vspipe, script), argv], lines.append)
    assert any(progress(line) == 1.0 for line in lines if "Encoding:" in line)
    probe = subprocess.run(
        [shutil.which("ffprobe") or "ffprobe", "-v", "error", "-select_streams", "v", "-show_entries",
         "packet=flags", "-of", "csv=p=0", str(out)],
        capture_output=True, text=True, check=True,
    ).stdout.split()  # fmt: skip
    assert [n for n, f in enumerate(probe) if "K" in f] == [0, 31] and len(probe) == 48

    plan = plan_for(source(name=str(clip_file)))
    plan.source.path, plan.encode_path = clip_file, out
    sar, tags = Fraction(4, 3), effective_container_color(color, enc)
    mkv, mp4 = tmp_path / "out.mkv", tmp_path / "out.mp4"
    process.run([mux_command(plan, {}, mkv, str(mkvmerge), (), sar=sar, color=tags)], lines.append)
    process.run([mp4box_command(plan, {}, mp4, mp4box, (), sar=sar, color=tags)], lines.append)
    for file in (mkv, mp4):
        [video] = [t for t in MediaInfo.parse(str(file)).tracks if t.track_type == "Video"]
        assert video.format == "AV1" and video.frame_count == "48"
        assert float(video.display_aspect_ratio) == pytest.approx(320 * 4 / 3 / 180, abs=0.003)  # 4:3 pixels
        expected = ("BT.709", "BT.709") if override else ("BT.2020", "PQ")
        assert (video.color_primaries, video.transfer_characteristics) == expected, file
        if override:
            assert video.color_range == "Full", file
        assert video.mastering_display_color_primaries == "Display P3", file
        max_nits = 2000 if override else 1000
        assert video.mastering_display_luminance == f"min: 0.0050 cd/m2, max: {max_nits} cd/m2", file
        light = (video.maximum_content_light_level, video.maximum_frameaverage_light_level)
        assert [n.split()[0] for n in light] == (["500", "100"] if override else ["1000", "400"]), file


def test_manual_encode_defaults_are_fresh_copies(profile):
    video, enc = profile.video_defaults()
    assert (enc.encoder, enc.rate_control, enc.crf, enc.preset) == (Encoder.X264, RateControl.CRF, 18.0, "slow")
    enc.options["ref"] = "9"
    video.crop.top = 2
    again_video, again = profile.video_defaults()
    assert again.options == {} and again_video.crop.top == 0
