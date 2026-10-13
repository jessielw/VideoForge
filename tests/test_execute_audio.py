"""Encode commands built from planned tracks."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import audio

from videoforge.core.config import Tools
from videoforge.core.execute.audio import AudioSettings, audio_command
from videoforge.core.models import AudioAction as A
from videoforge.core.models import AudioCodec as C
from videoforge.core.models import Layout, PlannedAudio

TOOLS = Tools(mkvmerge="mkvmerge", deezy="deezy", dee="dee", truehdd="truehdd", qaac="qaac64", ffmpeg="ffmpeg")
SRC = Path("Show.S01E01.mkv")
TMP = Path("tmp")


def planned(codec, layout, action, out_layout=None, bitrate=None, *, atmos=False, upmix=False, index=0) -> PlannedAudio:
    track = audio(codec, layout, atmos=atmos, index=index)
    out_codec = {A.COPY: codec, A.AAC: C.AAC}.get(action, C.EAC3)
    return PlannedAudio(
        source=track,
        action=action,
        out_codec=out_codec,
        out_layout=Layout.parse(out_layout or layout),
        out_atmos=action is A.ATMOS,
        bitrate_kbps=bitrate,
        upmix_50=upmix,
        language="en",
        title="",
        default=True,
    )


def command(p: PlannedAudio, settings: AudioSettings | None = None):
    return audio_command(p, 1, SRC, TMP, settings or AudioSettings(), TOOLS)


def test_copy_has_no_command():
    assert command(planned(C.AC3, "5.1", A.COPY)) is None


def test_ddp_51():
    cmd = command(planned(C.TRUEHD, "5.1", A.DDP, bitrate=640, index=1))
    (argv,) = cmd.argvs
    assert argv[:3] == ("deezy", "encode", "ddp")
    assert "--channels=6" in argv and "--bitrate=640" in argv
    assert "--track-index=1" in argv and "--delay=0ms" in argv
    assert "--upmix-50-to-51" not in argv
    assert argv[-1] == str(SRC)
    assert cmd.output.suffix == ".ec3"


@pytest.mark.parametrize("action", [A.DDP, A.ATMOS])
def test_deezy_gets_source_delay(action):
    p = planned(C.TRUEHD, "7.1", action, "5.1", 1024, atmos=action is A.ATMOS)
    p.source.delay_ms = -42
    (argv,) = command(p).argvs
    assert "--delay=-42ms" in argv


def test_ddp_50_upmixes():
    (argv,) = command(planned(C.DTS_HD_MA, "5.0", A.DDP, "5.1", 640, upmix=True)).argvs
    assert "--upmix-50-to-51" in argv and "--channels=6" in argv


def test_ddp_71():
    (argv,) = command(planned(C.DTS_HD_MA, "7.1", A.DDP, bitrate=1280)).argvs
    assert "--channels=8" in argv and "--bitrate=1280" in argv


def test_atmos():
    (argv,) = command(planned(C.TRUEHD, "7.1", A.ATMOS, "5.1", 1024, atmos=True)).argvs
    assert argv[:3] == ("deezy", "encode", "atmos")
    assert "--atmos-mode=streaming" in argv and "--bitrate=1024" in argv
    assert not any(a.startswith("--channels") for a in argv)


def test_settings_extra_args():
    settings = AudioSettings(atmos_mode="bluray", qaac_tvbr=91, deezy_extra_args=("--x",), qaac_extra_args=("--y",))
    (argv,) = command(planned(C.TRUEHD, "7.1", A.ATMOS, "5.1", 1024, atmos=True), settings).argvs
    assert "--atmos-mode=bluray" in argv and "--x" in argv
    _, qaac = command(planned(C.FLAC, "2.0", A.AAC), settings).argvs
    assert qaac[qaac.index("--tvbr") + 1] == "91" and "--y" in qaac


@pytest.mark.parametrize(("layout", "out", "channels"), [("1.0", "1.0", "1"), ("2.0", "2.0", "2"), ("4.1", "2.0", "2")])
def test_aac_pipes_ffmpeg_into_qaac(layout, out, channels):
    cmd = command(planned(C.FLAC, layout, A.AAC, out, index=2))
    ffmpeg, qaac = cmd.argvs
    assert ffmpeg[0] == "ffmpeg" and ffmpeg[-1] == "-"
    assert ffmpeg[ffmpeg.index("-map") + 1] == "0:a:2"
    assert ffmpeg[ffmpeg.index("-ac") + 1] == channels
    assert qaac[0] == "qaac64" and qaac[-1] == "-"
    assert qaac[qaac.index("--tvbr") + 1] == "127"
    assert qaac[qaac.index("-o") + 1] == str(cmd.output)
    assert cmd.output.suffix == ".m4a"
