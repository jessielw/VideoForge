"""A 2-pass target size's bitrate (core/video/target.py): StaxRip's Calc.GetVideoBitrate."""

from __future__ import annotations

from fractions import Fraction

from conftest import audio, plan_for, source, sub

from videoforge.core.models import AudioAction, AudioCodec as C, Layout, Severity, SubFormat as F, VideoInfo
from videoforge.core.video import target
from videoforge.core.video.info import ScriptInfo
from videoforge.core.video.settings import EncoderSettings, RateControl
from videoforge.server.views import encoder_label

FILM = Fraction(24000, 1001)


def film_plan(tmp_path):
    """24000 frames at 23.976 (1001 s): a TrueHD copy, a DDP 640 encode, an AAC TVBR 91 stereo encode, a PGS."""
    tracks = [audio(C.TRUEHD, "7.1", index=0), audio(C.TRUEHD, "5.1", index=1), audio(C.FLAC, "2.0", index=2)]
    tracks[0].size_bytes = 500_000_000
    src = source(tracks, [sub(F.PGS, index=0)])
    src.subs[0].size_bytes = 30_000_000
    src.attachments_bytes = 2_000_000
    src.video = VideoInfo(1920, 1080, default_duration_ns=41708333, frames=24000)
    plan = plan_for(src)
    _, ddp, aac = plan.audio
    ddp.action, ddp.out_codec, ddp.out_layout, ddp.bitrate_kbps = AudioAction.DDP, C.EAC3, Layout(5, 1), 640
    aac.action, aac.out_codec, aac.out_layout, aac.bitrate_kbps = AudioAction.AAC, C.AAC, Layout(2, 0), None
    aac.options["quality"] = "91"
    return plan


def test_the_budget_is_staxrips_sum(tmp_path):
    plan = film_plan(tmp_path)
    found = target.budget(4700, plan, "mkv", ScriptInfo(24000, FILM))
    assert found is not None
    assert found.seconds == 1001
    aac = int((12.5 + 237.5 * 91 / 127) * 1000 / 8 * 1001)  # StaxRip's qaac TVBR guess: 182.7 kb/s for stereo 91
    assert found.audio == 500_000_000 + 640 * 125 * 1001 + aac
    assert (found.subs, found.attachments, found.metadata) == (30_000_000, 2_000_000, 0)
    assert found.overhead == int(24000 * 0.014 * 1024)  # StaxRip's bytes per frame in an MKV
    assert found.video == 4_700_000_000 - found.audio - 32_000_000 - found.overhead
    assert found.kbps == int(found.video * 8 / 1000 / 1001)
    assert not found.unknown

    mp4 = target.budget(4700, plan, "mp4", ScriptInfo(24000, FILM))
    assert mp4 is not None
    assert (mp4.attachments, mp4.overhead) == (0, int(24000 * 0.013 * 1024))  # an MP4 keeps no attachments


def test_pass_2_counts_the_encoded_files_and_metadata(tmp_path):
    plan = film_plan(tmp_path)
    ddp, rpu = tmp_path / "audio1.ec3", tmp_path / "dv_rpu.bin"
    ddp.write_bytes(b"x" * 1000)
    rpu.write_bytes(b"x" * 500)
    planned = target.budget(4700, plan, "mkv", ScriptInfo(24000, FILM))
    found = target.budget(4700, plan, "mkv", ScriptInfo(24000, FILM), {1: ddp, 2: tmp_path / "missing.m4a"}, [rpu])
    assert planned is not None and found is not None
    assert found.audio == planned.audio - 640 * 125 * 1001 + 1000  # a missing file: its planned size
    assert found.metadata == 500


def test_the_length_is_the_scripts_once_known(tmp_path):
    video = VideoInfo(1920, 1080, default_duration_ns=41708333, frames=24000)
    assert target.length(video, ScriptInfo(12000, Fraction(12)), "mkv") == (1000, 12000)
    seconds, frames = target.length(video, None, "mkv") or (0, 0)
    assert (round(seconds, 3), frames) == (1001, 24000)  # before the info step: the source's
    vfr = VideoInfo(1920, 1080, default_duration_ns=41708333, frames=24000, vfr=True, duration_ms=1100_000)
    assert target.length(vfr, ScriptInfo(24000, FILM), "mkv") == (1100, 24000)  # timed by the source's timestamps
    assert target.length(vfr, ScriptInfo(24000, FILM), "mp4") == (1001, 24000)  # muxed at the script's rate
    assert target.length(VideoInfo(1920, 1080), None, "mkv") is None


def test_issues(tmp_path):
    plan = film_plan(tmp_path)
    two_pass = EncoderSettings(rate_control=RateControl.TWO_PASS, target_mb=4700)
    assert target.issues(two_pass, plan, "mkv") == []
    assert target.issues(EncoderSettings(rate_control=RateControl.ABR, target_mb=500), plan, "mkv") == []

    small = target.issues(EncoderSettings(rate_control=RateControl.TWO_PASS, target_mb=500), plan, "mkv")
    assert [(i.severity, i.code) for i in small] == [(Severity.BLOCK, "video.target_small")]

    plan.audio[0].source.size_bytes = None  # a copy MediaInfo gives no size or bitrate
    plan.subs[0].source.size_bytes = None
    unknown = target.issues(two_pass, plan, "mkv")
    assert [(i.severity, i.code) for i in unknown] == [(Severity.WARN, "video.target_unknown")]
    assert "audio 1" in unknown[0].message and "subtitle 1" in unknown[0].message

    plan.source.video = VideoInfo(1920, 1080)
    assert [i.code for i in target.issues(two_pass, plan, "mkv")] == ["video.target_length"]


def test_encoder_label():
    assert encoder_label(EncoderSettings(rate_control=RateControl.TWO_PASS, target_mb=4700)) == "x264 2-pass 4700 MB"
    assert encoder_label(EncoderSettings(rate_control=RateControl.ABR, target_mb=4700)) == "x264 10000 kb/s"
