"""Video: script generation, encoder command lines, auto-crop, and the real VapourSynth + encoders.

The integration tests make a small letterboxed MKV with ffmpeg and use the plugins
in tools/vs-plugins and the encoders in tools/; they skip when those are missing.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from videoforge.core.config import PROJECT_ROOT
from videoforge.core.video import crop as autocrop
from videoforge.core.video import vs as vsx
from videoforge.core.video.encoders import encoder_command, output_name, progress, vspipe_command
from videoforge.core.video.script import build_script
from videoforge.core.video.settings import (
    Crop,
    Encoder,
    EncoderSettings,
    RateControl,
    Resize,
    SourceFilter,
    VideoSettings,
)

TOOLS = PROJECT_ROOT / "tools"
PLUGINS = TOOLS / "vs-plugins"
FFMPEG = shutil.which("ffmpeg")
vsx.configure(PLUGINS)  # before any clip loads in this test process


# --- script -------------------------------------------------------------------------


def test_script_layout():
    s = VideoSettings(crop=Crop(0, 22, 0, 22), resize=Resize(1280, 544), filters="clip = clip.std.Invert()")
    text = build_script(s, Path(r"D:\Show\E01.mkv"), Path(r"D:\Show\E01.mkv_tmp"), depth=10)
    lines = text.splitlines()
    assert lines[2] == ("src = core.bs.VideoSource('D:\\\\Show\\\\E01.mkv', cachemode=4, "
                        "cachepath='D:\\\\Show\\\\E01.mkv_tmp\\\\E01.mkv')")
    assert "clip = core.std.Crop(clip, left=0, right=0, top=22, bottom=22)" in lines
    assert "clip = core.resize.Spline36(clip, width=1280, height=544)" in lines
    assert "clip = clip.std.Invert()" in lines
    assert "bits_per_sample=10" in text and lines[-1] == "clip.set_output()"
    compile(text, "<script>", "exec")

    source_only = build_script(s, Path("a.mkv"), Path("w"), stage="source")
    assert "Crop" not in source_only and source_only.endswith("clip = src\nclip.set_output()\n")
    custom = build_script(VideoSettings(source_filter=SourceFilter.LSMASH, custom="clip = src[10:20]"),
                          Path("a.mkv"), Path("w"))
    assert "lsmas.LWLibavSource" in custom and "clip = src[10:20]" in custom and "Crop" not in custom


# --- encoders -----------------------------------------------------------------------


def test_x264_two_pass_and_options():
    s = EncoderSettings(rate_control=RateControl.TWO_PASS, bitrate_kbps=10000, preset="veryslow",
                        options={"ref": "4", "no-fast-pskip": "", "--aq-mode": "3"}, extra='--aq-strength 0.9')
    argv = encoder_command("x264", s, frames=100, output=Path("v.264"), pass_number=2, stats=Path("s.log"),
                           qpfile=Path("c.qpf"))
    assert argv[:5] == ["x264", "--demuxer", "y4m", "--frames", "100"]
    assert argv[argv.index("--bitrate") + 1] == "10000" and argv[argv.index("--pass") + 1] == "2"
    assert ["--ref", "4", "--no-fast-pskip", "--aq-mode", "3"] == argv[argv.index("--ref"):argv.index("--aq-mode") + 2]
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


def test_progress_lines():
    assert progress("[x264] [ 12.5%] 125/1000 frames, 30.1 fps, 9000 kb/s, eta 0:00:29") == 0.125
    assert progress("[x265] [50.0%] 500/1000 frames, 4.12 fps") == 0.5
    assert progress("[vspipe] Frame: 50/200 (12.3 fps)") == 0.25
    assert progress("[x265] 250 frames: 4.1 fps, 900 kb/s", frames=1000) == 0.25
    assert progress("[x264] encoded 1000 frames") is None


# --- auto-crop ----------------------------------------------------------------------


def letterboxed(h=180, w=320, top=22, bottom=22, left=0, right=0) -> np.ndarray:
    rgb = np.full((h, w, 3), 128, np.uint8)
    rgb[:top] = rgb[h - bottom:] = 0
    rgb[:, :left] = 0
    if right:
        rgb[:, w - right:] = 0
    return rgb


def test_frame_borders_and_combine():
    assert autocrop.frame_borders(letterboxed(left=10, right=6)) == Crop(10, 22, 6, 22)
    dark_frame = np.zeros((180, 320, 3), np.uint8)  # a fade: everything up to the quarter limit
    assert autocrop.frame_borders(dark_frame) == Crop(80, 45, 80, 45)
    crops = [autocrop.frame_borders(f) for f in (letterboxed(top=23), dark_frame, letterboxed(top=25))]
    assert autocrop.combine(crops) == Crop(0, 22, 0, 22)  # smallest per side, rounded to mod 2
    assert autocrop.sample_frames(1000, 4) == [162, 387, 612, 837]
    assert autocrop.sample_frames(3, 10) == [0, 1, 2]


# --- real VapourSynth and encoders ---------------------------------------------------

needs_vs = pytest.mark.skipif(
    FFMPEG is None or not (PLUGINS / "bestsource.dll").exists(), reason="needs ffmpeg and tools/vs-plugins"
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
def test_autocrop_preview_and_output(clip_file, tmp_path):
    settings = VideoSettings()
    cache = vsx.ClipCache()
    src = cache.get(build_script(settings, clip_file, tmp_path, stage="source"))
    found = autocrop.detect(src, samples=6)
    # The lossy fixture bleeds chroma into the bars' last rows; the detector keeps those (conservative).
    assert (found.left, found.right) == (0, 0) and found.top in (20, 22) and found.bottom in (20, 22)
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
@pytest.mark.parametrize("encoder", list(Encoder))
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
    # vspipe finds the plugins through the environment configure() set for this process.
    process.run([vspipe_command(vspipe, script), encoder_command(str(exe), enc, frames=48, output=out)], lines.append)
    assert out.is_file() and out.stat().st_size > 1000
    assert any(progress(line) is not None for line in lines) or any("frames" in line for line in lines)


def test_manual_encode_defaults_are_fresh_copies(profile):
    video, enc = profile.video_defaults()
    assert (enc.encoder, enc.rate_control, enc.crf, enc.preset) == (Encoder.X264, RateControl.CRF, 18.0, "slow")
    enc.options["ref"] = "9"
    video.crop.top = 2
    again_video, again = profile.video_defaults()
    assert again.options == {} and again_video.crop.top == 0
