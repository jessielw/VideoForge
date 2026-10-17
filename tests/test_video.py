"""Video: script generation, encoder command lines, auto-crop, and the real VapourSynth + encoders.

The integration tests make a small letterboxed MKV with ffmpeg and use the plugins
in tools/vs-plugins and the encoders in tools/; they skip when those are missing.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import numpy as np
import pytest

from videoforge.core.config import PROJECT_ROOT
from videoforge.core.plan_io import from_json, to_json
from videoforge.core.video import crop as autocrop, vs as vsx
from videoforge.core.video.encoders import encoder_command, output_name, progress, vspipe_command
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


def test_progress_lines():
    assert progress("[x264] [ 12.5%] 125/1000 frames, 30.1 fps, 9000 kb/s, eta 0:00:29") == 0.125
    assert progress("[x265] [50.0%] 500/1000 frames, 4.12 fps") == 0.5
    assert progress("[vspipe] Frame: 50/200 (12.3 fps)") == 0.25
    assert progress("[x265] 250 frames: 4.1 fps, 900 kb/s", frames=1000) == 0.25
    assert progress("[x264] encoded 1000 frames") is None


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
def test_filter_presets_run(preset):
    """Each preset runs on 8- and 16-bit video (skipped when its plugin or filter script isn't installed)."""
    import vapoursynth as vs

    core = vs.core
    for fmt in (vs.YUV420P8, vs.YUV420P16):
        if fmt == vs.YUV420P16 and preset.family == "IVTC (VIVTC)":
            continue  # VFM takes 8-bit only
        clip = core.std.BlankClip(width=640, height=360, format=fmt, length=12, fpsnum=24000, fpsden=1001)
        ns = {"vs": vs, "core": core, "clip": clip}
        try:
            exec(preset.script, ns)  # noqa: S102 - the built-in presets
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
