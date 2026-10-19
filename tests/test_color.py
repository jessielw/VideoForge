"""The source's colour description (MediaInfo) -> x264 / x265 flags."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from videoforge.core.models import VideoColor, VideoInfo
from videoforge.core.plan_io import from_json, to_json
from videoforge.core.video.color import color_args, from_mediainfo, master_display
from videoforge.core.video.encoders import encoder_command
from videoforge.core.video.settings import Encoder, EncoderSettings

P3_4000 = "G(13250,34500)B(7500,3000)R(34000,16000)WP(15635,16450)L(40000000,50)"  # x265's own example
HDR10 = VideoColor("bt2020", "smpte2084", "bt2020nc", "limited", 2, P3_4000, 1000, 657)


def track(**fields):
    return SimpleNamespace(**fields)


def test_hdr10_from_mediainfo():
    """A UHD Blu-ray's HDR10 base layer, as MediaInfo 25 reads it ("Container / Stream" pairs: the first)."""
    mi = track(
        color_primaries="BT.2020",
        transfer_characteristics="PQ",
        matrix_coefficients="BT.2020 non-constant",
        color_range="Limited",
        chroma_subsampling_position="Type 2",
        mastering_display_color_primaries="Display P3",
        mastering_display_luminance="min: 0.0050 cd/m2, max: 4000 cd/m2",
        maximum_content_light_level="1000 cd/m2",
        maximum_frameaverage_light_level="657 cd/m2",
    )
    assert from_mediainfo(mi) == HDR10


def test_sdr_and_unknown_names():
    mi = track(color_primaries="BT.709", transfer_characteristics="BT.709", matrix_coefficients="BT.709 / BT.709")
    assert from_mediainfo(mi) == VideoColor("bt709", "bt709", "bt709")
    assert from_mediainfo(track(color_primaries="Something new")) == VideoColor()
    assert from_mediainfo(None) == VideoColor()


def test_master_display_by_coordinates():
    primaries = "R: x=0.708000 y=0.292000, G: x=0.170000 y=0.797000, B: x=0.131000 y=0.046000, White point: x=0.312700 y=0.329000"
    assert master_display(primaries, "min: 0.0001 cd/m2, max: 1000 cd/m2") == (
        "G(8500,39850)B(6550,2300)R(35400,14600)WP(15635,16450)L(10000000,1)"
    )
    assert master_display("BT.2020", "min: 0.0001 cd/m2, max: 1000 cd/m2") == master_display(
        primaries, "min: 0.0001 cd/m2, max: 1000 cd/m2"
    )
    assert master_display("Display P3", "") == "" and master_display("R: x=1", "min: 1 cd/m2, max: 2 cd/m2") == ""


def test_flags_per_encoder():
    x265 = EncoderSettings(Encoder.X265, depth=10)
    assert color_args(HDR10, x265) == [
        "--colorprim", "bt2020", "--transfer", "smpte2084", "--colormatrix", "bt2020nc", "--range", "limited",
        "--chromaloc", "2", "--master-display", P3_4000, "--max-cll", "1000,657",
        "--hdr10", "--repeat-headers", "--hrd", "--aud",
    ]  # fmt: skip
    # x264: the VUI only, with its own range names
    assert color_args(HDR10, EncoderSettings()) == [
        "--colorprim", "bt2020", "--transfer", "smpte2084", "--colormatrix", "bt2020nc", "--range", "tv",
        "--chromaloc", "2",
    ]  # fmt: skip
    assert color_args(VideoColor(range="full"), EncoderSettings()) == ["--range", "pc"]
    # HDR10 with no range from the source: limited, as StaxRip sets it
    assert color_args(VideoColor(max_cll=1000), x265) == [
        "--max-cll", "1000,0", "--hdr10", "--repeat-headers", "--hrd", "--aud", "--range", "limited",
    ]  # fmt: skip
    assert color_args(VideoColor("bt709", "bt709", "bt709"), x265) == [
        "--colorprim", "bt709", "--transfer", "bt709", "--colormatrix", "bt709",
    ]  # fmt: skip  # SDR: none of them
    assert color_args(HDR10, EncoderSettings(Encoder.X265, source_color=False)) == []
    assert color_args(None, x265) == []


def test_the_users_option_wins():
    """The colour flags go before the options and extra arguments: the encoder takes the last one."""
    enc = EncoderSettings(Encoder.X265, depth=10, options={"colorprim": "bt709"}, extra="--max-cll 500,100")
    argv = encoder_command("x265", enc, output=Path("v.hevc"), color=HDR10)
    prims = [i for i, a in enumerate(argv) if a == "--colorprim"]
    assert [argv[i + 1] for i in prims] == ["bt2020", "bt709"]
    assert argv[len(argv) - 1 - argv[::-1].index("--max-cll") + 1] == "500,100"


def test_the_options_turn_the_hdr10_flags_off():
    """StaxRip's HDR10 flags are on by default; a --no- form in the options or extra arguments comes after them,
    and x265 takes the last one."""
    enc = EncoderSettings(Encoder.X265, depth=10, options={"no-hrd": ""}, extra="--no-aud")
    argv = encoder_command("x265", enc, output=Path("v.hevc"), color=HDR10)
    assert argv.index("--hrd") < argv.index("--no-hrd") and argv.index("--aud") < argv.index("--no-aud")
    assert "--repeat-headers" in argv and "--hdr10" in argv


def test_hdr10_fills_the_vbv_from_the_level():
    """As StaxRip does with HDR10: a --level-idc without VBV gets the level's max bitrate (High tier)."""
    enc = EncoderSettings(Encoder.X265, depth=10, options={"level-idc": "5.1"})
    argv = encoder_command("x265", enc, output=Path("v.hevc"), color=HDR10)
    assert argv[argv.index("--vbv-maxrate") + 1] == "160000" and argv[argv.index("--vbv-bufsize") + 1] == "160000"
    assert "--vbv-maxrate" not in encoder_command("x265", EncoderSettings(Encoder.X265), output=Path("v.hevc"))
    sdr = encoder_command("x265", enc, output=Path("v.hevc"), color=VideoColor("bt709", "bt709", "bt709"))
    assert "--vbv-maxrate" not in sdr


def test_old_probes_load_without_colour():
    """A job saved before colour was probed loads with none (the next probe fills it)."""
    data = to_json(VideoInfo(1920, 1080))
    del data["color"]
    assert from_json(VideoInfo, data).color == VideoColor()
    assert from_json(VideoInfo, to_json(VideoInfo(3840, 2160, color=HDR10))).color == HDR10
