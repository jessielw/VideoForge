"""Encode commands built from planned tracks."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

from conftest import audio
import pytest

from videoforge.core.config import Tools
from videoforge.core.execute.audio import AudioSettings, audio_command
from videoforge.core.models import AudioAction as A, AudioCodec as C, Layout, PlannedAudio

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


@pytest.mark.parametrize("mode, encoder", [(None, "ddp"), ("standard", "ddp"), ("bluray", "ddp-bluray")])
def test_ddp_mode_selects_command_independently_of_bitrate(mode, encoder):
    p = planned(C.TRUEHD, "7.1", A.DDP, bitrate=1536)
    if mode:
        p.options = {"ddp_mode": mode}
    (argv,) = command(p).argvs
    assert argv[:3] == ("deezy", "encode", encoder)
    assert "--channels=8" in argv and "--bitrate=1536" in argv
    assert "--upmix-50-to-51" not in argv
    assert not any(a.startswith("--ddp-mode") for a in argv)


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


def test_aac_bitrate_is_constrained_vbr():
    _, qaac = command(planned(C.FLAC, "2.0", A.AAC, bitrate=192)).argvs
    assert qaac[qaac.index("--cvbr") + 1] == "192" and "--tvbr" not in qaac


# --- ffmpeg's own encoders ------------------------------------------------------------


@pytest.mark.parametrize(
    ("action", "suffix", "codec_args"),
    [
        (A.FLAC, ".flac", ["-c:a", "flac", "-compression_level", "8"]),
        (A.OPUS, ".opus", ["-c:a", "libopus", "-b:a", "384k"]),
        (A.AAC_FFMPEG, ".m4a", ["-c:a", "aac", "-b:a", "384k"]),
        (A.AC3, ".ac3", ["-c:a", "ac3", "-b:a", "384k"]),
        (A.EAC3, ".eac3", ["-c:a", "eac3", "-b:a", "384k"]),
    ],
)
def test_ffmpeg_encodes(action, suffix, codec_args):
    cmd = command(
        planned(C.TRUEHD, "7.1", action, out_layout="5.1", bitrate=None if action is A.FLAC else 384, index=2)
    )
    (argv,) = cmd.argvs
    assert argv[0] == "ffmpeg" and argv[argv.index("-map") + 1] == "0:a:2"
    assert argv[argv.index("-af") + 1] == "aformat=channel_layouts=5.1"  # exact, so libopus takes 5.1(side) sources
    i = argv.index("-c:a")
    assert list(argv[i : i + len(codec_args)]) == codec_args
    assert cmd.output.suffix == suffix and argv[-1] == str(cmd.output)


def test_ffmpeg_names_mono_and_stereo():
    (argv,) = command(planned(C.AC3, "2.0", A.OPUS, out_layout="2.0", bitrate=160)).argvs
    assert argv[argv.index("-af") + 1] == "aformat=channel_layouts=stereo"


FFMPEG = shutil.which("ffmpeg")


@pytest.mark.skipif(FFMPEG is None, reason="needs ffmpeg")
@pytest.mark.parametrize(
    ("action", "out_layout", "channels"),
    [
        (A.FLAC, "5.1", 6),
        (A.OPUS, "5.1", 6),
        (A.OPUS, "2.0", 2),
        (A.AAC_FFMPEG, "5.1", 6),
        (A.AC3, "5.1", 6),
        (A.EAC3, "2.0", 2),
    ],
)
def test_ffmpeg_encodes_for_real(tmp_path, action, out_layout, channels):
    """A 5.1(side) source (what TrueHD/DTS decode to) through each encode."""
    src = tmp_path / "src.mka"
    subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "sine=f=440:d=1", "-filter_complex",
                    "[0]asplit=6[a][b][c][d][e][f];[a][b][c][d][e][f]join=inputs=6:channel_layout=5.1(side)",
                    "-c:a", "pcm_s24le", str(src)], check=True)  # fmt: skip
    p = planned(C.LPCM, "5.1", action, out_layout=out_layout, bitrate=None if action is A.FLAC else 192)
    tools = Tools(mkvmerge="", deezy="", dee="", truehdd="", qaac="", ffmpeg=FFMPEG)
    cmd = audio_command(p, 1, src, tmp_path, AudioSettings(), tools)
    subprocess.run(cmd.argvs[0], check=True)
    probe = subprocess.run([FFMPEG, "-hide_banner", "-i", str(cmd.output)], capture_output=True, text=True).stderr
    assert "Audio:" in probe and (f"{channels} channels" in probe or ("5.1" if channels == 6 else "stereo") in probe)


def test_ffmpeg_encode_options():
    p = planned(C.TRUEHD, "5.1", A.OPUS, bitrate=384)
    p.options = {"vbr": "off", "application": "voip", "complexity": "5", "extra": "-cutoff 20000"}
    (argv,) = command(p).argvs
    assert argv[argv.index("-vbr") + 1] == "off" and argv[argv.index("-application") + 1] == "voip"
    assert argv[argv.index("-compression_level") + 1] == "5"
    assert argv[-3:-1] == ("-cutoff", "20000")  # extra arguments go just before the output
    flac = planned(C.TRUEHD, "5.1", A.FLAC)
    flac.options = {"level": "12"}
    (argv,) = command(flac).argvs
    assert argv[argv.index("-compression_level") + 1] == "12"
    ac3 = planned(C.TRUEHD, "5.1", A.AC3, bitrate=640)
    (argv,) = command(ac3).argvs
    assert argv[argv.index("-dialnorm") + 1] == "-31"  # the default when none is planned


# --- DeeZy, qaac and opusenc options -------------------------------------------------------


def test_deezy_options():
    ddp = planned(C.TRUEHD, "5.1", A.DDP, "2.0", 256)
    (argv,) = command(ddp).argvs
    assert not any(a.startswith(("--drc", "--custom-dialnorm", "--stereo-down-mix")) for a in argv)  # DeeZy's own
    ddp.options = {
        "drc_line": "film_light",
        "drc_rf": "speech",
        "dialnorm": "-27",
        "stereo_downmix": "dpl2",
        "extra": "--metering-mode 1770_3",
    }
    (argv,) = command(ddp, AudioSettings(deezy_extra_args=("--x",))).argvs
    assert {
        "--drc-line-mode=film_light",
        "--drc-rf-mode=speech",
        "--custom-dialnorm=-27",
        "--stereo-down-mix=dpl2",
    } <= set(argv)
    assert argv[-4:] == ("--x", "--metering-mode", "1770_3", str(SRC))  # the profile's extras, then the track's

    atmos = planned(C.TRUEHD, "7.1", A.ATMOS, "5.1", 1024, atmos=True)
    atmos.options = {"atmos_mode": "bluray", "warp": "loro", "bed_conform": "on"}
    (argv,) = command(atmos).argvs
    assert {"--atmos-mode=bluray", "--thd-warp-mode=loro", "--bed-conform"} <= set(argv)


def test_profile_defaults_stand_in_for_unset_options():
    settings = AudioSettings(atmos_mode="bluray", qaac_tvbr=91)
    (argv,) = command(planned(C.TRUEHD, "7.1", A.ATMOS, "5.1", 1024, atmos=True), settings).argvs
    assert "--atmos-mode=bluray" in argv
    aac = planned(C.FLAC, "2.0", A.AAC)
    aac.options = {"quality": "100", "extra": "--lowpass 20000"}
    _, qaac = command(aac, settings).argvs
    assert qaac[qaac.index("--tvbr") + 1] == "100"  # the track's own beats the profile's
    assert qaac[-5:] == ("--lowpass", "20000", "-o", qaac[-2], "-")


def test_a_profile_dialnorm_goes_to_deezy_unless_the_track_sets_one():
    settings = AudioSettings(dialnorm=-31)
    ddp = planned(C.TRUEHD, "5.1", A.DDP, "5.1", 640)
    atmos = planned(C.TRUEHD, "7.1", A.ATMOS, "5.1", 1024, atmos=True)
    for p in (ddp, atmos):
        (argv,) = command(p, settings).argvs
        assert "--custom-dialnorm=-31" in argv
    ddp.options = {"dialnorm": "-27"}
    (argv,) = command(ddp, settings).argvs
    assert "--custom-dialnorm=-27" in argv and "--custom-dialnorm=-31" not in argv
    assert settings.option_defaults(A.AAC) == {"quality": "127"}  # only DeeZy's encodes take it


def test_opusenc_pipes_ffmpeg_into_opusenc():
    p = planned(C.TRUEHD, "7.1", A.OPUSENC, "5.1", 384, index=1)
    cmd = command(p)
    ffmpeg, opusenc = cmd.argvs
    assert ffmpeg[ffmpeg.index("-map") + 1] == "0:a:1" and ffmpeg[-1] == "-"
    assert ffmpeg[ffmpeg.index("-af") + 1] == "aformat=channel_layouts=5.1"
    assert opusenc[0] == "opusenc" and opusenc[-2:] == ("-", str(cmd.output)) and cmd.output.suffix == ".opus"
    assert opusenc[opusenc.index("--bitrate") + 1] == "384" and "--vbr" in opusenc
    assert opusenc[opusenc.index("--comp") + 1] == "10" and "--music" not in opusenc and "--speech" not in opusenc
    p.options = {"mode": "hard-cbr", "tune": "speech", "comp": "6", "extra": "--framesize 40"}
    _, opusenc = command(p).argvs
    assert "--hard-cbr" in opusenc and "--speech" in opusenc and opusenc[opusenc.index("--comp") + 1] == "6"
    assert opusenc[-4:-2] == ("--framesize", "40")


OPUSENC = Path(__file__).resolve().parents[1] / "tools" / "opus-tools" / "opusenc.exe"


@pytest.mark.skipif(FFMPEG is None or not OPUSENC.exists(), reason="needs ffmpeg and tools/opus-tools")
@pytest.mark.parametrize(("out_layout", "channels"), [("5.1", 6), ("2.0", 2)])
def test_opusenc_for_real(tmp_path, out_layout, channels):
    src = tmp_path / "src.mka"
    subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "sine=f=440:d=1", "-filter_complex",
                    "[0]asplit=6[a][b][c][d][e][f];[a][b][c][d][e][f]join=inputs=6:channel_layout=5.1(side)",
                    "-c:a", "pcm_s24le", str(src)], check=True)  # fmt: skip
    p = planned(C.LPCM, "5.1", A.OPUSENC, out_layout=out_layout, bitrate=192)
    tools = Tools(mkvmerge="", deezy="", dee="", truehdd="", qaac="", ffmpeg=FFMPEG, opusenc=str(OPUSENC))
    cmd = audio_command(p, 1, src, tmp_path, AudioSettings(), tools)
    decode = subprocess.Popen(cmd.argvs[0], stdout=subprocess.PIPE)
    encode = subprocess.run(cmd.argvs[1], stdin=decode.stdout, capture_output=True, text=True, check=False)
    decode.wait()
    assert encode.returncode == 0 and not encode.stderr  # no warnings about the WAV
    probe = subprocess.run(
        [FFMPEG, "-hide_banner", "-i", str(cmd.output)], capture_output=True, text=True, check=False
    ).stderr
    assert "Audio: opus" in probe and ("5.1" if channels == 6 else "stereo") in probe
