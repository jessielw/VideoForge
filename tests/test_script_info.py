"""The script's frames and frame rate (vspipe --info) and the length check against the source."""

from __future__ import annotations

from fractions import Fraction

from videoforge.core.models import Severity, VideoInfo
from videoforge.core.video.info import ScriptInfo, length_issues, length_warning, parse

INFO = """Output Index: 0
Type: Video
Width: 1920
Height: 1080
Frames: 34047
FPS: 24000/1001 (23.976 fps)
Format Name: YUV420P10
"""


def test_parse_vspipe_info():
    assert parse(INFO) == ScriptInfo(34047, Fraction(24000, 1001))
    assert parse(INFO.replace("FPS: 24000/1001 (23.976 fps)", "FPS: Variable")) == ScriptInfo(34047, None)
    assert parse("Width: 1920\n") is None


NTSC = 33366667  # 29.97 fps frame duration, ns


def test_an_ivtc_or_a_double_rate_deinterlace_keeps_the_length():
    source = VideoInfo(720, 480, default_duration_ns=NTSC, frames=43157)
    assert length_warning(source, 34525, Fraction(24000, 1001)) == ""  # VFM + VDecimate: 4 of 5 frames
    assert length_warning(source, 34526, Fraction(24000, 1001)) == ""  # a frame off at the end: still fine
    assert length_warning(source, 86314, Fraction(60000, 1001)) == ""  # QTGMC at double rate


def test_a_trim_or_a_speed_change_warns():
    source = VideoInfo(1920, 1080, default_duration_ns=41708333, frames=34047)
    trimmed = length_warning(source, 34047 - 240, Fraction(24000, 1001))
    assert "out of step" in trimmed and "-10.010 s" in trimmed
    assert length_warning(source, 34047, Fraction(25)) != ""  # AssumeFPS(25): a PAL speed-up
    issues = length_issues(source, ScriptInfo(34047 - 240, Fraction(24000, 1001)))
    assert [(i.severity, i.code) for i in issues] == [(Severity.WARN, "video.length")]


def test_no_check_without_both_lengths():
    assert length_warning(VideoInfo(1920, 1080, default_duration_ns=41708333), 100, Fraction(24)) == ""  # no frames
    assert length_warning(VideoInfo(1920, 1080, frames=100), 50, Fraction(24)) == ""  # no source rate
    source = VideoInfo(1920, 1080, default_duration_ns=41708333, frames=100)
    assert length_warning(source, 50, None) == ""  # a variable-rate script
    assert length_issues(source, None) == []  # the info step hasn't run
