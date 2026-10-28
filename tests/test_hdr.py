"""A source's Dolby Vision / HDR10+ layers (MediaInfo; FEL or MEL from the RPU)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from videoforge.core.models import VideoHdr, VideoInfo
from videoforge.core.plan_io import from_json, to_json
from videoforge.core.video import hdr
from videoforge.core.video.encoders import encoder_command, level_vbv
from videoforge.core.video.hdr import from_mediainfo, hdr10plus_frames, l5_offsets, rpu_edit, video_stream_argv
from videoforge.core.video.settings import (
    Crop,
    Encoder,
    EncoderSettings,
    FilterCategory,
    FilterStep,
    Resize,
    VideoSettings,
)
from videoforge.core.video.starters import starters

# The FEL test file (a UHD Blu-ray remux), as MediaInfo 25 reads it
P7_FEL = SimpleNamespace(
    hdr_format="Dolby Vision / SMPTE ST 2086",
    hdr_format_commercial="Blu-ray / HDR10",
    hdr_format_level="06 / ",
    hdr_format_profile="dvhe.07 / ",
    hdr_format_settings="BL+EL+RPU / ",
    other_hdr_format=[
        "Dolby Vision, Version 1.0, Profile 7.6, dvhe.07.06, BL+EL+RPU, no metadata compression, Blu-ray "
        "compatible / SMPTE ST 2086, Version HDR10, HDR10 compatible"
    ],
)


def test_profile_7_from_mediainfo():
    hdr = from_mediainfo(P7_FEL)
    assert hdr == VideoHdr(dv_profile=7, dv_compat=6, dv_level=6, dv_layers="BL+EL+RPU")
    assert hdr.dv_name == "7.6"  # FEL or MEL comes from the RPU (probe_inputs)


def test_profile_8_with_hdr10plus():
    mi = SimpleNamespace(
        hdr_format="Dolby Vision / SMPTE ST 2094 App 4",
        hdr_format_commercial="HDR10 / HDR10+",
        hdr_format_level="06 / ",
        hdr_format_profile="dvhe.08 / ",
        hdr_format_settings="BL+RPU / ",
        other_hdr_format=["Dolby Vision, Version 1.0, Profile 8.1, dvhe.08.06, BL+RPU / SMPTE ST 2094 App 4"],
    )
    assert from_mediainfo(mi) == VideoHdr(8, 1, 6, "BL+RPU", hdr10plus=True)


def test_hdr10plus_only_and_none():
    assert from_mediainfo(SimpleNamespace(hdr_format="SMPTE ST 2094 App 4")) == VideoHdr(hdr10plus=True)
    assert from_mediainfo(SimpleNamespace(hdr_format_commercial="HDR10+ Profile B")) == VideoHdr(hdr10plus=True)
    assert from_mediainfo(SimpleNamespace(hdr_format="SMPTE ST 2086")) == VideoHdr()
    assert from_mediainfo(None) == VideoHdr()
    assert VideoHdr().dv_name == ""


def test_profile_without_the_long_name():
    """Only the codec string: the profile, no compatibility id."""
    mi = SimpleNamespace(hdr_format="Dolby Vision", hdr_format_profile="dvhe.05", hdr_format_settings="BL+RPU")
    assert from_mediainfo(mi) == VideoHdr(dv_profile=5, dv_layers="BL+RPU")
    assert VideoHdr(7, 6, dv_el="FEL").dv_name == "7.6 FEL"


def test_old_probes_load_without_hdr():
    data = to_json(VideoInfo(3840, 2160))
    del data["hdr"]
    assert from_json(VideoInfo, data).hdr == VideoHdr()


def test_video_stream_argv():
    argv = video_stream_argv("ffmpeg", Path("a.mkv"), start_s=10, seconds=1)
    assert argv[argv.index("-ss") + 1] == "10" and argv[argv.index("-t") + 1] == "1"
    assert argv.index("-ss") < argv.index("-i") < argv.index("-t")
    assert argv[-9:] == ["-map", "0:v:0", "-c:v:0", "copy", "-bsf:v", "hevc_mp4toannexb", "-f", "hevc", "-"]
    assert "-ss" not in video_stream_argv("ffmpeg", Path("a.mkv"))


def test_hdr10plus_frames_and_x264(tmp_path):
    meta = tmp_path / "hdr10plus.json"
    meta.write_text('{"JSONInfo": {"HDR10plusProfile": "B"}, "SceneInfo": [{}, {}, {}]}', encoding="utf-8")
    assert hdr10plus_frames(meta) == 3
    x264 = encoder_command("x264", EncoderSettings(), output=Path("v.264"), hdr10plus=meta)
    assert "--dhdr10-info" not in x264  # x264 has no HDR10+
    x265 = encoder_command(
        "x265", EncoderSettings(encoder=Encoder.X265, depth=10), output=Path("v.hevc"), hdr10plus=meta
    )
    assert x265[x265.index("--dhdr10-info") + 1] == str(meta)


def test_script_frames_reads_vspipe_info(monkeypatch):
    """process.run hands back vspipe's lines tagged with its name."""

    def fake_run(argvs, log, cancel=None):
        for line in ("Output Index: 0", "Width: 3840", "Frames: 1200", "FPS: 24000/1001 (23.976 fps)"):
            log(f"[vspipe] {line}")

    monkeypatch.setattr(hdr, "run", fake_run)
    assert hdr.script_frames("vspipe", Path("video.vpy")) == 1200


def test_l5_offsets_follow_crop_and_resize():
    bars = {"id": 0, "left": 0, "right": 0, "top": 276, "bottom": 276}  # 2.40:1 in 3840x2160
    plain = VideoSettings()
    assert l5_offsets(bars, plain, 3840, 2160) == {"left": 0, "right": 0, "top": 276, "bottom": 276}
    cropped = VideoSettings(crop=Crop(top=276, bottom=276))
    assert l5_offsets(bars, cropped, 3840, 2160) == dict.fromkeys(("left", "right", "top", "bottom"), 0)
    # cropped past the bars: 0, not negative (DoviCrop's -f)
    over = VideoSettings(crop=Crop(left=4, right=4, top=280, bottom=270))
    assert l5_offsets(bars, over, 3840, 2160) == {"left": 0, "right": 0, "top": 0, "bottom": 6}
    # a resize after the crop scales what's left: 3840 -> 1920 halves it
    half = VideoSettings(crop=Crop(bottom=270), resize=Resize(1920, 945))
    assert l5_offsets(bars, half, 3840, 2160) == {"left": 0, "right": 0, "top": 138, "bottom": 3}
    # a resize before the crop: the crop is in the resized picture's pixels
    first = VideoSettings(
        crop=Crop(top=138, bottom=138),
        resize=Resize(1920, 1080),
        filters=[FilterStep(FilterCategory.RESIZE, "Resize"), FilterStep(FilterCategory.CROP, "Crop")],
    )
    assert l5_offsets(bars, first, 3840, 2160) == dict.fromkeys(("left", "right", "top", "bottom"), 0)

    export = {"mode": 0, "active_area": {"crop": True, "presets": [bars], "edits": {"0-1796": 0}}}
    assert rpu_edit(export, cropped, 3840, 2160) == {
        "mode": 2,
        "active_area": {
            "crop": True,
            "presets": [{"id": 0, "left": 0, "right": 0, "top": 0, "bottom": 0}],
            "edits": {"0-1796": 0},
        },
    }
    assert rpu_edit({"presets": [bars]}, plain, 3840, 2160)["active_area"]["edits"] == {"all": 0}  # older export
    assert rpu_edit({"mode": 0}, plain, 3840, 2160) == {"mode": 2}  # no L5


def _preset(pid, top, bottom, left=0, right=0):
    return {"id": pid, "left": left, "right": right, "top": top, "bottom": bottom}


def test_l5_bars_both_export_shapes():
    """dovi_tool >= 2.3.3 wraps the area in "active_area"; older ones export it bare (DoviCrop reads both)."""
    godzilla = _preset(0, 276, 277)  # Godzilla Minus One's L5: an odd bottom
    new = {"mode": 0, "active_area": {"crop": True, "presets": [godzilla], "edits": {"0-461": 0}}}
    assert hdr.l5_bars(new) == Crop(left=0, top=276, right=0, bottom=277)
    assert hdr.l5_bars({"presets": [godzilla], "edits": {"all": 0}}) == Crop(top=276, bottom=277)
    assert hdr.l5_bars({"mode": 0}) == Crop()  # no L5 authored
    assert hdr.l5_bars({"active_area": {"presets": [], "edits": {}}}) == Crop()


def test_l5_bars_varying_aspect_keeps_every_frame():
    """IMAX scenes (another preset): each side takes the smallest bar, so the open-matte frames keep their picture;
    a preset only used in the first or last 1000 frames (a full-frame logo) doesn't count."""
    presets = [_preset(0, 0, 0), _preset(1, 276, 276), _preset(2, 140, 142, left=2, right=4)]
    film = {"active_area": {"presets": presets, "edits": {"0-239": 0, "240-90000": 1, "90001-120000": 2}}}
    assert hdr.l5_bars(film) == Crop(left=0, top=140, right=0, bottom=142)  # the logo's 0 skipped
    one = {"active_area": {"presets": presets, "edits": {"0-239": 0, "240-120000": 1}}}
    assert hdr.l5_bars(one) == Crop(top=276, bottom=276)
    # the IMAX scenes in the middle of the film count
    imax = {"active_area": {"presets": presets, "edits": {"0-50000": 1, "50001-60000": 0, "60001-120000": 1}}}
    assert hdr.l5_bars(imax) == Crop()
    # a short clip: the margin is 5% of it (23 frames of 462), so a cut still has frames left
    cut = {"active_area": {"presets": presets, "edits": {"0-10": 0, "11-461": 1}}}
    assert hdr.l5_bars(cut) == Crop(top=276, bottom=276)
    # all of it in the margin: every preset counts
    tiny = {"active_area": {"presets": presets[:2], "edits": {"0-0": 0, "1-1": 1}}}
    assert hdr.l5_bars(tiny) == Crop()


def test_l5_crop_rounds_down_and_checks_the_picture():
    l5 = Crop(top=276, bottom=277)
    # the luma crop stops 2-3 px short (the bars' soft edge): the L5's, an odd side rounded down (1 px of bar kept)
    crop, origin = hdr.l5_crop(l5, Crop(top=274, bottom=274))
    assert crop == Crop(top=276, bottom=276)
    assert origin.startswith("Dolby Vision L5 (left 0, top 276, right 0, bottom 277; detected 0, 274, 0, 274)")
    assert hdr.l5_crop(Crop(left=3, right=5, top=1), Crop(left=2, right=4))[0] == Crop(left=2, right=4)
    # past the L5 is fine: the L5 is the smaller crop (a dark scene by the bar reads as bar)
    assert hdr.l5_crop(l5, Crop(top=300, bottom=300))[0] == Crop(top=276, bottom=276)
    # the picture shows inside the L5's bar: that side takes the detected crop, and says so
    crop, origin = hdr.l5_crop(l5, Crop(top=200, bottom=274), "detected black borders")
    assert crop == Crop(top=200, bottom=276)
    assert origin.endswith("the picture shows inside the L5 bar, so detected: top 200 (L5 276)")
    # no bars: the detected crop
    assert hdr.l5_crop(Crop(), Crop(top=20, bottom=20), "detected black borders") == (
        Crop(top=20, bottom=20),
        "detected black borders (the Dolby Vision L5 has no bars)",
    )


def test_dolby_vision_x265_args():
    rpu = Path("dv_rpu.bin")
    x264 = encoder_command("x264", EncoderSettings(), output=Path("v.264"), dolby_vision=rpu)
    assert "--dolby-vision-rpu" not in x264
    x265 = encoder_command(
        "x265", EncoderSettings(encoder=Encoder.X265, depth=10), output=Path("v.hevc"), dolby_vision=rpu
    )
    i = x265.index("--dolby-vision-profile")
    assert x265[i : i + 4] == ["--dolby-vision-profile", "8.1", "--dolby-vision-rpu", "dv_rpu.bin"]
    # VBV from --level-idc, only where the job sets none
    leveled = EncoderSettings(encoder=Encoder.X265, depth=10, options={"level-idc": "5.1", "vbv-maxrate": "50000"})
    x265 = encoder_command("x265", leveled, output=Path("v.hevc"), dolby_vision=rpu)
    assert x265[i + 4 : i + 6] == ["--vbv-bufsize", "160000"] and x265.count("--vbv-maxrate") == 1
    plain = encoder_command("x265", leveled, output=Path("v.hevc"))
    assert "--vbv-bufsize" not in plain  # only for Dolby Vision


@pytest.mark.parametrize(
    ("options", "extra", "vbv"),
    [
        ({"vbv-maxrate": "40000", "vbv-bufsize": "30000"}, "", []),
        ({}, "", None),
        ({"level-idc": "5.1"}, "", ["--vbv-maxrate", "160000", "--vbv-bufsize", "160000"]),
        ({"level-idc": "51", "no-high-tier": ""}, "", ["--vbv-maxrate", "40000", "--vbv-bufsize", "40000"]),
        ({"level-idc": "4"}, "--vbv-maxrate=20000", ["--vbv-bufsize", "30000"]),
        ({}, "--level-idc 6.2 --no-high-tier", ["--vbv-maxrate", "240000", "--vbv-bufsize", "240000"]),
        ({"level-idc": "3"}, "", ["--vbv-maxrate", "6000", "--vbv-bufsize", "6000"]),  # no High tier
        ({"level-idc": "4.4"}, "", None),
        ({"level-idc": "high"}, "", None),
    ],
)
def test_level_vbv(options, extra, vbv):
    assert level_vbv(EncoderSettings(encoder=Encoder.X265, options=options, extra=extra)) == vbv


def test_starter_presets():
    """The starters build commands; the Dolby Vision one keeps DV on and fills x265's VBV from its level."""
    by_name = {s.name: s.settings for s in starters()}
    dv = encoder_command("x265", by_name["x265-dv"], output=Path("v.hevc"), dolby_vision=Path("rpu.bin"))
    assert dv[dv.index("--vbv-maxrate") + 1] == dv[dv.index("--vbv-bufsize") + 1] == "160000"
    assert by_name["x265-dv"].dolby_vision and not by_name["x265-hdr10"].dolby_vision
    for s in by_name.values():
        argv = encoder_command(s.encoder.value, s, output=Path("v"))
        assert s.depth == 10 and s.preset in argv
    assert starters()[0].settings is not starters()[0].settings  # fresh copies
