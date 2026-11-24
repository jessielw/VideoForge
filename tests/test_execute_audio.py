"""Encode commands built from planned tracks."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import shutil
import subprocess

from conftest import audio
import pytest

from videoforge.core.config import Tools
from videoforge.core.execute.audio import (
    DEEZY_CONFIG,
    ENCODES,
    AudioSettings,
    audio_command,
    downmix_argv,
    downmix_path,
    needs_downmix,
)
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


def deezy(*encode: str) -> tuple[str, ...]:
    """How a DeeZy command starts: VideoForge's own empty config, then the encode."""
    return ("deezy", "--config", str(DEEZY_CONFIG), "encode", *encode)


def test_copy_has_no_command():
    assert command(planned(C.AC3, "5.1", A.COPY)) is None


def test_ddp_51():
    cmd = command(planned(C.TRUEHD, "5.1", A.DDP, bitrate=640, index=1))
    (argv,) = cmd.argvs
    assert argv[:5] == deezy("ddp")
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


@pytest.mark.parametrize("deep", [False, True])
def test_deezy_temp_dir_is_left_to_deezy_when_too_deep_for_dee(deep, monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setattr("videoforge.core.dee.shutil.which", lambda _name: None)  # shutil.which needs a real Windows
    work = Path("C:/") / ("x" * 150 if deep else "work")
    p = planned(C.TRUEHD, "7.1", A.DDP, "5.1", 640)
    (argv,) = audio_command(p, 1, SRC, work, AudioSettings(), TOOLS).argvs
    assert ("--temp-dir" in argv) is not deep


def test_deezy_working_dir_is_in_the_job_folder():
    # DeeZy's default is beside its exe, which fails when that isn't writable (/usr/local/bin)
    (argv,) = command(planned(C.TRUEHD, "7.1", A.DDP, "5.1", 640)).argvs
    assert argv[argv.index("--working-dir") + 1] == str(TMP / "deezy-work")


def test_ddp_50_upmixes():
    (argv,) = command(planned(C.DTS_HD_MA, "5.0", A.DDP, "5.1", 640, upmix=True)).argvs
    assert "--upmix-50-to-51" in argv and "--channels=6" in argv


def test_ddp_50_upmix_reads_the_source():
    p = planned(C.DTS_HD_MA, "5.0", A.DDP, "5.1", 640, upmix=True, index=2)
    (argv,) = command(p).argvs
    assert not needs_downmix(p) and argv[-1] == str(SRC) and "--track-index=2" in argv


@pytest.mark.parametrize("source", ["6.0", "7.0"])
def test_ddp_51_from_60_or_70_upmixes_a_50_downmix(source):
    """DeeZy adds an LFE to a 5.0 source alone (it codes 6.0 and 7.0 as 5.0): ffmpeg makes the 5.0 first."""
    assert ENCODES[A.DDP].upmix_50(Layout.parse(source), Layout(5, 1))
    p = planned(C.DTS_HD_MA, source, A.DDP, "5.1", 640, upmix=True, index=2)
    mixed = downmix_path(p, 1, TMP)
    (argv,) = command(p).argvs
    assert needs_downmix(p) and mixed == TMP / "audio1_en.5.0.flac"
    assert argv[-1] == str(mixed) and "--track-index=0" in argv  # its only track
    assert "--upmix-50-to-51" in argv and "--channels=6" in argv
    dm = downmix_argv(p, SRC, mixed, TOOLS)
    assert dm[dm.index("-i") + 1] == str(SRC) and dm[dm.index("-map") + 1] == "0:a:2"
    # float, so the fronts keep their level (an integer downmix turns every channel down)
    assert dm[dm.index("-af") + 1] == "aformat=sample_fmts=flt:channel_layouts=5.0(side)"
    assert dm[-5:] == ("-c:a", "flac", "-sample_fmt", "s32", str(mixed))


def test_ddp_71():
    (argv,) = command(planned(C.DTS_HD_MA, "7.1", A.DDP, bitrate=1280)).argvs
    assert "--channels=8" in argv and "--bitrate=1280" in argv


@pytest.mark.parametrize(
    ("source", "out", "flags"),
    [
        ("5.0", "5.0", ["--channels=6", "--disable-lfe"]),  # DEE 6.7 codes 5.0 as it is
        ("5.1", "5.0", ["--channels=6", "--disable-lfe"]),
        ("5.0", "5.1", ["--channels=6", "--upmix-50-to-51"]),
        ("5.1", "5.1", ["--channels=6"]),
    ],
)
def test_ddp_lfe(source, out, flags):
    (argv,) = command(planned(C.DTS_HD_MA, source, A.DDP, out, 640, upmix=(source, out) == ("5.0", "5.1"))).argvs
    deezy_flags = [a for a in argv if a.startswith(("--channels", "--disable-lfe", "--upmix"))]
    assert deezy_flags == flags


def test_ddp_surround_3db_is_off_unless_set():
    p = planned(C.TRUEHD, "5.1", A.DDP, bitrate=640)
    assert "--surround-3db" not in command(p).argvs[0]
    p.options = {"surround_3db": "on"}
    assert "--surround-3db" in command(p).argvs[0]


@pytest.mark.parametrize(
    "mode, shim, encoder",
    [
        (None, True, "ddp"),
        ("standard", True, "ddp"),
        ("standard", False, "ddp"),  # DeeZy refuses it without dee_shim: the plan blocks it (tool_issues)
        ("bluray", True, "ddp-bluray"),
    ],
)
def test_ddp_mode_selects_command_independently_of_bitrate(mode, shim, encoder, tmp_path):
    p = planned(C.TRUEHD, "7.1", A.DDP, bitrate=1536)
    if mode:
        p.options = {"ddp_mode": mode}
    exe = tmp_path / "dee_shim.exe"
    exe.write_bytes(b"")
    tools = replace(TOOLS, dee_shim=str(exe) if shim else "")
    (argv,) = audio_command(p, 1, SRC, TMP, AudioSettings(), tools).argvs
    assert argv[:5] == deezy(encoder)
    assert "--channels=8" in argv and "--bitrate=1536" in argv
    assert "--upmix-50-to-51" not in argv
    assert not any(a.startswith("--ddp-mode") for a in argv)


def test_deezy_is_given_the_dee_folder_and_the_dee_shim_videoforge_found(tmp_path):
    dee = tmp_path / "DEE"
    dee.mkdir()
    (dee / "dee_ddp_encoder.exe").write_bytes(b"")
    shim = tmp_path / "dee_shim.exe"
    shim.write_bytes(b"")
    p = planned(C.TRUEHD, "5.1", A.DDP, bitrate=640)
    tools = replace(TOOLS, dee=str(dee / "dee.exe"), dee_shim=str(shim))  # an old config's dee.exe: its folder
    (argv,) = audio_command(p, 1, SRC, TMP, AudioSettings(), tools).argvs
    assert argv[argv.index("--dee") + 1] == str(dee)
    assert argv[argv.index("--dee-shim") + 1] == str(shim) and "--no-shim" not in argv
    (argv,) = audio_command(p, 1, SRC, TMP, AudioSettings(), replace(tools, dee_shim=str(tmp_path / "no.exe"))).argvs
    assert "--no-shim" in argv and "--dee-shim" not in argv  # never one DeeZy finds by itself


def test_atmos():
    (argv,) = command(planned(C.TRUEHD, "7.1", A.ATMOS, "5.1", 1024, atmos=True)).argvs
    assert argv[:5] == deezy("ddp-atmos")
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
        "extra": "--no-low-pass-filter --lo-ro-center -3",
    }
    (argv,) = command(ddp, AudioSettings(deezy_extra_args=("--x",))).argvs
    assert {
        "--drc-line-mode=film_light",
        "--drc-rf-mode=speech",
        "--custom-dialnorm=-27",
        "--stereo-down-mix=dpl2",
    } <= set(argv)
    # the rule set's extras, then the track's
    assert argv[-5:] == ("--x", "--no-low-pass-filter", "--lo-ro-center", "-3", str(SRC))
    ddp.options = {"drc_line": "none"}
    assert "--drc-line-mode=none" in command(ddp).argvs[0]

    atmos = planned(C.TRUEHD, "7.1", A.ATMOS, "7.1", 1280, atmos=True)
    atmos.options = {"atmos_mode": "bluray", "warp": "loro", "bed_conform": "on"}  # bed conformance: gone in DeeZy 2
    (argv,) = command(atmos).argvs
    assert {"--atmos-mode=bluray", "--thd-warp-mode=loro"} <= set(argv) and "--bed-conform" not in argv


@pytest.mark.parametrize(
    ("action", "options", "encoder"),
    [(A.DDP, {}, "ddp"), (A.DDP, {"ddp_mode": "bluray"}, "ddp-bluray"), (A.ATMOS, {}, "ddp-atmos")],
)
def test_deezy_debug_is_a_global_option(action, options, encoder):
    p = planned(C.TRUEHD, "7.1", action, bitrate=1280, atmos=action is A.ATMOS)
    p.options = options
    (argv,) = command(p).argvs
    assert "--log-level" not in argv

    p.options = {**options, "deezy_debug": "on"}
    (argv,) = command(p).argvs
    assert argv[:7] == ("deezy", "--config", str(DEEZY_CONFIG), "--log-level", "debug", "encode", encoder)


def test_deezy_runs_with_videoforges_empty_config():
    """A deezy-conf.toml of the user's (2.0 applies its [global_defaults]) mustn't change an encode."""
    assert DEEZY_CONFIG.is_file()
    assert all(line.startswith("#") for line in DEEZY_CONFIG.read_text(encoding="utf-8").splitlines() if line)


def test_deezy_rates_are_dees():
    ddp, atmos = ENCODES[A.DDP], ENCODES[A.ATMOS]
    assert ddp.bitrate_problem(640, Layout(5, 1)) == ""
    assert ddp.bitrate_problem(650, Layout(5, 1)) == "DDP (DEE) at 5.1 takes 640 or 704 kb/s, not 650 (DEE's rates)"
    assert ddp.bitrate_problem(1792, Layout(7, 1)) == ""  # through dee_shim
    assert ddp.bitrate_problem(2000, Layout(7, 1)) == "DDP (DEE) at 7.1 takes 1792 kb/s, not 2000 (DEE's rates)"
    bluray = ddp.configured({"ddp_mode": "bluray"})
    assert bluray.bitrate_problem(1664, Layout(7, 1)) == "" and bluray.bitrate_problem(1792, Layout(7, 1))
    assert atmos.bitrate_problem(1024, Layout(5, 1)) == "" and atmos.bitrate_problem(512, Layout(5, 1))
    standard = atmos.configured({"atmos_mode": "standard"})
    assert (standard.layouts, standard.default_bitrate(Layout(7, 1))) == ((Layout(7, 1),), 1152)
    assert standard.bitrate_problem(2048, Layout(7, 1)) == "" and standard.bitrate_problem(400, Layout(7, 1))
    assert atmos.configured({"atmos_mode": "bluray"}).default_bitrate(Layout(7, 1)) == 1280


@pytest.mark.parametrize(
    ("source", "default"),
    [("5.0", "5.0"), ("7.0", "5.0"), ("5.1", "5.1"), ("6.1", "5.1"), ("7.1", "7.1"), ("4.1", "2.0"), ("3.0", "2.0")],
)
def test_ddp_defaults_add_no_speaker(source, default):
    """DEE 6.7 codes 5.0 as 5.0, and DeeZy codes a source without an LFE without one."""
    ddp = ENCODES[A.DDP]
    assert str(ddp.default_layout(Layout.parse(source))) == default
    # 5.1 from 5.0, 6.0 or 7.0 takes the upmix (needs_downmix); a 4.1 has no center for it
    assert not any(ddp.upmixes(Layout.parse(s), Layout(5, 1)) for s in ("5.0", "6.0", "7.0"))
    assert ddp.upmixes(Layout(4, 1), Layout(5, 0)) and ddp.upmixes(Layout(7, 0), Layout(7, 1))


def test_rule_set_defaults_stand_in_for_unset_options():
    settings = AudioSettings(atmos_mode="bluray", qaac_tvbr=91)
    (argv,) = command(planned(C.TRUEHD, "7.1", A.ATMOS, "5.1", 1024, atmos=True), settings).argvs
    assert "--atmos-mode=bluray" in argv
    aac = planned(C.FLAC, "2.0", A.AAC)
    aac.options = {"quality": "100", "extra": "--lowpass 20000"}
    _, qaac = command(aac, settings).argvs
    assert qaac[qaac.index("--tvbr") + 1] == "100"  # the track's own beats the rule set's
    assert qaac[-5:] == ("--lowpass", "20000", "-o", qaac[-2], "-")


def test_a_rule_set_dialnorm_goes_to_deezy_unless_the_track_sets_one():
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


def test_standard_ddp_71_goes_past_1024_through_dee_shim():
    ddp = ENCODES[A.DDP]
    assert ddp.bitrate_problem(1280, Layout(7, 1)) == ""  # DeeZy 1.5 stopped at 1024
    assert ddp.bitrate_problem(1280, Layout(5, 1)) == "DDP (DEE) at 5.1 takes 1024 kb/s, not 1280 (DEE's rates)"
    assert ddp.configured({"ddp_mode": "bluray"}).bitrate_problem(1280, Layout(7, 1)) == ""
