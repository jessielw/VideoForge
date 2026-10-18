"""A source's Dolby Vision / HDR10+ layers (MediaInfo; FEL or MEL from the RPU)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from videoforge.core.models import VideoHdr, VideoInfo
from videoforge.core.plan_io import from_json, to_json
from videoforge.core.video import hdr
from videoforge.core.video.encoders import encoder_command
from videoforge.core.video.hdr import from_mediainfo, hdr10plus_frames, video_stream_argv
from videoforge.core.video.settings import Encoder, EncoderSettings

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
