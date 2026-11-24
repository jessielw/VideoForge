"""Tool detection for the Settings page, and tool paths layered over videoforge.toml."""

from __future__ import annotations

from pathlib import Path
import sys

from conftest import audio, plan_for, source, sub

from videoforge.core import tools
from videoforge.core.config import AppConfig, Tools, with_tools
from videoforge.core.dee import folder as dee_folder
from videoforge.core.models import AudioAction, AudioCodec as C, Severity, SubFormat
from videoforge.core.tools import (
    TOOL_NAMES,
    TOOLS,
    ToolInfo,
    ToolStatus,
    check,
    detect,
    missing_for_encodes,
    tool_issues,
    unsupported,
    version_line,
)

INFO = {t.name: t for t in TOOLS}


def test_version_lines_from_real_tool_output():
    assert version_line("mkvmerge v100.0 ('Do Hot Girls Like Chords') 64-bit\n") == (
        "mkvmerge v100.0 ('Do Hot Girls Like Chords') 64-bit"
    )
    assert version_line("x264 0.165.3222 b35605a\nbuilt on ...") == "x264 0.165.3222 b35605a"
    assert version_line("\nx265 [info]: HEVC encoder version 3.6+35\n") == "HEVC encoder version 3.6+35"
    assert version_line("qaac 2.82, CoreAudioToolbox 7.10.9.0\n") == "qaac 2.82, CoreAudioToolbox 7.10.9.0"
    assert version_line("VapourSynth Video Processing Library\nCore R72\n") == "Core R72"
    assert version_line("Usage: tool [options]\n") == ""
    assert version_line('[2026-10-13 15:28:38.673] ERROR: Unknown option: "--version"\n') == ""
    assert version_line("dee.exe, Version 5.2.1, Jun 10 2022\nOptions:\n") == "dee.exe, Version 5.2.1, Jun 10 2022"


def test_check_tries_each_command_until_a_version(tmp_path):
    exe = tmp_path / "tool.exe"
    exe.write_bytes(b"")
    calls = []

    def runner(argv, _timeout):
        calls.append(list(argv[1:]))
        return "Unknown option --version" if argv[1:] else "Some Tool\nVersion 5.2.1\n"

    c = check(ToolInfo("tool", "Tool", "", (("--help",), ())), str(exe), runner=runner)
    assert calls == [["--help"], []]
    assert (c.status, c.version, c.found) == (ToolStatus.OK, "Version 5.2.1", str(exe))


def test_x265_avx512_looks_at_the_selected_cpu_flags(tmp_path, monkeypatch):
    exe = tmp_path / "x265"
    exe.touch()
    output = ["x265 [INFO]: using cpu capabilities: SSE2 AVX2 AVX512\n"]
    calls = []

    def runner(argv, _timeout):
        calls.append(argv)
        return output[0]

    monkeypatch.setattr(tools, "_run", runner)
    assert tools.x265_avx512(str(exe)) is True
    assert tools.x265_avx512(str(exe)) is True
    assert calls == [[str(exe), "--asm", "avx512", "--version"]]

    output[0] = "x265 [WARN]: AVX512 is not supported\nx265 [INFO]: using cpu capabilities: AVX2\n"
    assert tools._x265_avx512(str(exe), 0) is False
    output[0] = "Usage: x265 [options]"
    assert tools._x265_avx512(str(exe), 1) is None
    assert tools.x265_avx512(str(tmp_path / "missing")) is None


def test_missing_broken_and_unknown(tmp_path):
    assert check(INFO["x264"], str(tmp_path / "nope.exe")).status is ToolStatus.MISSING
    exe = tmp_path / "x264.exe"
    exe.write_bytes(b"")

    def broken(_argv, _timeout):
        raise OSError("not a program")

    c = check(INFO["x264"], str(exe), runner=broken)
    assert c.status is ToolStatus.BROKEN and "not a program" in c.detail
    c = check(INFO["x264"], str(exe), runner=lambda *_: "hello\n")
    assert (c.status, c.detail) == (ToolStatus.UNKNOWN, "hello")


def test_a_folder_or_a_file_that_cant_run_says_why(tmp_path):
    c = check(INFO["x264"], str(tmp_path))
    assert (c.status, c.detail) == (ToolStatus.MISSING, "This is a folder. Choose the program in it")
    c = check(INFO["dee"], str(tmp_path))
    assert (c.status, c.detail) == (ToolStatus.MISSING, "No DEE 6.7 tools (dee_ddp_encoder) in this folder")
    exe = tmp_path / "x264"
    exe.write_bytes(b"")
    c = check(INFO["dee"], str(exe))  # a program, but not in a DEE tools folder
    assert (c.status, c.detail) == (
        ToolStatus.MISSING,
        "Choose the DEE 6.7 tools folder (the one with dee_ddp_encoder)",
    )

    def denied(_argv, _timeout):
        raise PermissionError(13, "Permission denied")

    c = check(INFO["x264"], str(exe), runner=denied)
    assert c.status is ToolStatus.BROKEN
    assert ("Permission denied" in c.detail) is (sys.platform == "win32")  # elsewhere it's put in plain words
    assert ("chmod" in c.detail) is (sys.platform != "win32")


def test_a_real_program_on_path():
    c = check(
        INFO["ffmpeg"],
        sys.executable,
        runner=lambda argv, t: (
            __import__("subprocess").run([argv[0], "--version"], capture_output=True, text=True, timeout=t).stdout
        ),
    )
    assert c.status is ToolStatus.OK and c.version.startswith("Python 3.")


def test_plugin_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "bundled_plugin_folder", lambda: None)
    assert check(INFO["vs_plugins"], str(tmp_path / "none")).status is ToolStatus.MISSING
    (tmp_path / "libbestsource.dll").write_bytes(b"")
    (tmp_path / "ffms2.dll").write_bytes(b"")
    (tmp_path / "readme.txt").write_bytes(b"")
    (tmp_path / "zsmooth").mkdir()  # one plugin, several CPU builds
    (tmp_path / "zsmooth" / "manifest.vs").write_text("[VapourSynth Manifest V1]\nzsmooth\n")
    (tmp_path / "zsmooth" / "zsmooth.dll").write_bytes(b"")
    c = check(INFO["vs_plugins"], str(tmp_path))
    assert c.status is ToolStatus.OK and c.detail == "3 plugins; source filters: BestSource, FFMS2"
    empty = tmp_path / "empty"
    empty.mkdir()
    assert check(INFO["vs_plugins"], str(empty)).status is ToolStatus.UNKNOWN


def test_plugin_folder_counts_the_bundled_plugins(tmp_path, monkeypatch):
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    (bundled / "libvslsmashsource.so").write_bytes(b"")
    (bundled / "libmvtools.so").write_bytes(b"")
    monkeypatch.setattr(tools, "bundled_plugin_folder", lambda: bundled)
    c = check(INFO["vs_plugins"], str(tmp_path / "none"))  # the extra folder isn't there: the bundled ones are
    assert c.status is ToolStatus.OK and c.detail == "2 plugins (2 bundled); source filters: L-SMASH"
    assert c.found == str(bundled)
    (tmp_path / "BestSource.dll").write_bytes(b"")
    c = check(INFO["vs_plugins"], str(tmp_path))
    assert c.detail == "3 plugins (2 bundled); source filters: BestSource, L-SMASH" and c.found == str(tmp_path)


def test_detect_covers_every_tool_in_order(tmp_path):
    tools = Tools(**{name: str(tmp_path / name) for name in TOOL_NAMES})
    assert [c.name for c in detect(tools, runner=lambda *_: "v1")] == list(TOOL_NAMES)


def test_encodes_need_their_tools(tmp_path):
    for exe in ("mkvmerge.exe", "deezy.exe", "ffmpeg.exe", "qaac.exe", "truehdd.exe"):
        (tmp_path / exe).write_bytes(b"")
    tools = Tools(
        mkvmerge=str(tmp_path / "mkvmerge.exe"),
        deezy=str(tmp_path / "deezy.exe"),
        dee=str(tmp_path / "no-dee.exe"),
        truehdd=str(tmp_path / "truehdd.exe"),
        qaac=str(tmp_path / "qaac.exe"),
        ffmpeg=str(tmp_path / "ffmpeg.exe"),
    )
    missing = missing_for_encodes(tools)
    assert missing == {
        AudioAction.DDP: ["Dolby Encoding Engine"],
        AudioAction.ATMOS: ["Dolby Encoding Engine"],
        AudioAction.AAC: [],
        AudioAction.FLAC: [],
        AudioAction.OPUS: [],
        AudioAction.OPUSENC: ["opusenc"],
        AudioAction.AAC_FFMPEG: [],
        AudioAction.AC3: [],
        AudioAction.EAC3: [],
        AudioAction.MP3: [],
        AudioAction.VORBIS: [],
    }  # a fake ffmpeg can't be asked for its encoders

    plan = plan_for(source([audio(C.FLAC, "2.0", index=0), audio(C.TRUEHD, "5.1", index=1)]), source(name="E.mkv"))
    plan.audio[0].action, plan.audio[1].action = AudioAction.AAC, AudioAction.DDP
    issues = tool_issues(plan, tools)
    assert [(i.severity, i.code) for i in issues] == [(Severity.BLOCK, "tools.missing")]
    assert issues[0].message == "DDP (DEE) needs Dolby Encoding Engine. Set it in Settings › Tools"
    plan.audio[1].action = AudioAction.COPY
    assert tool_issues(plan, tools) == []


def test_mp4_source_srt_requires_extraction_tools(tmp_path, monkeypatch):
    cfg = Tools(
        mkvmerge="mkvmerge",
        mkvextract="mkvextract",
        mp4box="MP4Box",
        deezy="deezy",
        dee="dee",
        truehdd="truehdd",
        qaac="qaac",
        ffmpeg="ffmpeg",
    )
    monkeypatch.setattr(tools, "locate", lambda name: "" if name == "mkvextract" else name)
    plan = plan_for(source(subs=[sub(SubFormat.SRT, "en")]), source(name="E.mkv"))
    issues = tool_issues(plan, cfg, "mp4")
    assert len(issues) == 1 and issues[0].severity is Severity.BLOCK
    assert "mkvextract" in issues[0].message
    assert tool_issues(plan, cfg, "mkv") == []
    plan.subs[0].source.external_path = tmp_path / "subtitle.srt"
    assert tool_issues(plan, cfg, "mp4") == []


def test_with_tools_layers_paths_and_brings_mkvpropedit(tmp_path):
    (tmp_path / "mkv").mkdir()
    for exe in ("mkvmerge.exe", "mkvpropedit.exe", "mkvextract.exe"):
        (tmp_path / "mkv" / exe).write_bytes(b"")
    base = AppConfig(
        tools=Tools(mkvmerge="mkvmerge", deezy="deezy", dee="dee", truehdd="truehdd", qaac="qaac", ffmpeg="ffmpeg")
    )
    cfg = with_tools(base, {"mkvmerge": "mkv/mkvmerge.exe", "x264": "", "qaac": str(tmp_path / "q.exe")}, tmp_path)
    assert cfg.tools.mkvmerge == str(tmp_path / "mkv" / "mkvmerge.exe")
    assert cfg.tools.mkvpropedit == str(tmp_path / "mkv" / "mkvpropedit.exe")  # came along
    assert cfg.tools.mkvextract == str(tmp_path / "mkv" / "mkvextract.exe")
    assert cfg.tools.x264 == "x264"  # an empty value keeps the base
    assert cfg.tools.qaac == str(Path(tmp_path / "q.exe"))
    assert base.tools.mkvmerge == "mkvmerge"  # the base is untouched

    (tmp_path / "ff").mkdir()
    for exe in ("ffmpeg.exe", "ffprobe.exe"):
        (tmp_path / "ff" / exe).write_bytes(b"")
    cfg = with_tools(base, {"ffmpeg": "ff/ffmpeg.exe"}, tmp_path)
    assert cfg.tools.ffprobe == str(tmp_path / "ff" / "ffprobe.exe")  # ffmpeg's comes along
    assert with_tools(base, {"ffmpeg": "ff/ffmpeg.exe", "ffprobe": "fp"}, tmp_path).tools.ffprobe == "fp"


DEE_HELP = (
    "Dolby Digital Plus encoder.\nSupported channel configurations: 1.0, 2.0, 5.1 and 7.1.\n\n"
    "This tool belongs to the Dolby Encoding Engine version {}\nInterface version: 2.0.0 (Oct 27 2026):\n"
)


def _dee(tmp_path):
    folder = tmp_path / "dee"
    folder.mkdir()
    (folder / "dee_ddp_encoder.exe").write_bytes(b"")
    return folder


def test_dee_is_a_tools_folder_asked_for_its_version(tmp_path, monkeypatch):
    folder = _dee(tmp_path)
    calls = []

    def runner(argv, _timeout):
        calls.append(argv)
        return DEE_HELP.format("6.7.0+8e353f99")

    c = check(INFO["dee"], str(folder), runner=runner)
    assert (c.status, c.found, c.version) == (
        ToolStatus.OK,
        str(folder),
        "Dolby Encoding Engine version 6.7.0+8e353f99",  # not the channel line, which also has numbers
    )
    assert calls == [[str(folder / "dee_ddp_encoder.exe"), "--help"]]
    c = check(INFO["dee"], str(folder), runner=lambda *_: DEE_HELP.format("5.7.2.aec4fa9c-master"))
    assert (c.status, c.detail) == (ToolStatus.UNSUPPORTED, "DeeZy 2 needs DEE 6.7")

    # one of its tools, or an old dee.exe that isn't there any more, means the folder
    assert dee_folder(str(folder / "dee_ddp_encoder.exe")) == str(folder)
    assert dee_folder(str(folder / "dee.exe")) == str(folder)
    assert dee_folder(str(tmp_path / "dee.exe")) == ""
    # a bare "dee" (Docker) finds the folder on PATH by its dee_ddp_encoder
    marker = folder / "dee_ddp_encoder"
    marker.write_bytes(b"")
    marker.chmod(0o755)  # PATH lookup wants an executable file on POSIX
    monkeypatch.setenv("PATH", str(folder))
    assert dee_folder("dee") == str(folder)


def test_versions_deezy_2_wont_run():
    assert unsupported("deezy", "DeeZy 1.5.0") == "VideoForge needs DeeZy 2.0 or newer"
    assert unsupported("deezy", "DeeZy 2.0.0b2") == ""
    assert unsupported("dee_shim", "dee_shim v0.2.1+gc1141a0") == "DeeZy needs dee_shim 0.3.0 or newer"
    assert unsupported("dee_shim", "dee_shim v0.3.0+g2ae7f95") == ""
    assert unsupported("dee", "Dolby Encoding Engine version 6.7.1+0") == ""
    assert unsupported("dee", "Dolby Encoding Engine version 5.7.2.aec4fa9c-master") == "DeeZy 2 needs DEE 6.7"
    assert unsupported("deezy", "no version") == "" and unsupported("x264", "x264 0.1") == ""


def test_dee_issues_block_unsupported_versions_and_loudness_mixes(tmp_path, monkeypatch):
    from dataclasses import replace
    from types import SimpleNamespace as NS

    from videoforge.core.tools import _dee_issues

    folder = _dee(tmp_path)
    deezy, shim = tmp_path / "deezy.exe", tmp_path / "dee_shim.exe"
    deezy.write_bytes(b"")
    shim.write_bytes(b"")
    said = {
        str(deezy): "DeeZy 2.0.0b2",
        str(folder / "dee_ddp_encoder.exe"): DEE_HELP.format("6.7.0+8e353f99"),
        str(shim): "dee_shim v0.3.0+g2ae7f95",
    }
    monkeypatch.setattr(tools, "_run", lambda argv, _t: said[argv[0]])
    cfg = Tools(mkvmerge="", deezy=str(deezy), dee=str(folder), truehdd="", qaac="", ffmpeg="", dee_shim=str(shim))
    ddp = NS(action=AudioAction.DDP, options={"loudness_target": "-24"}, out_layout=NS(channels=6))
    assert _dee_issues(NS(audio=[ddp]), cfg) == []
    bad = NS(
        action=AudioAction.DDP,
        options={"loudness_target": "-24", "dialnorm": "-27", "ddp_mode": "bluray"},
        out_layout=NS(channels=8),
    )
    assert [i.severity for i in _dee_issues(NS(audio=[bad]), cfg)] == [Severity.BLOCK] * 2

    old = tmp_path / "old_shim.exe"
    old.write_bytes(b"")
    said[str(old)] = "dee_shim v0.2.1+gc1141a0"
    issues = _dee_issues(NS(audio=[ddp]), replace(cfg, dee_shim=str(old)))
    assert [(i.severity, i.code) for i in issues] == [(Severity.BLOCK, "tools.version")]
    assert issues[0].message == (
        "DDP (DEE): DeeZy needs dee_shim 0.3.0 or newer, not dee_shim v0.2.1+gc1141a0. Set dee_shim in Settings › Tools"
    )
    copy = NS(action=AudioAction.COPY, options={}, out_layout=NS(channels=6))
    assert _dee_issues(NS(audio=[copy]), replace(cfg, dee_shim=str(old))) == []  # no DeeZy encode


def test_friendly_errors_for_tools_that_cannot_start(monkeypatch):
    import errno

    from videoforge.core import tools

    monkeypatch.setattr(tools.os, "name", "posix")
    assert "Wine" in tools._friendly_error(OSError(errno.ENOEXEC, "x"), "/tools/wine/qaac/qaac64.exe")
    assert "PUID" in tools._friendly_error(PermissionError(errno.EACCES, "x"), "/tools/dee/dee")
    assert tools._friendly_error(OSError(errno.ENOENT, "x"), "/x") == ""


def test_ddp_71_and_the_71_atmos_modes_need_dee_shim(tmp_path, monkeypatch):
    from dataclasses import replace
    from types import SimpleNamespace as NS

    from videoforge.core.execute.audio import AudioSettings
    from videoforge.core.tools import _dee_issues

    monkeypatch.setattr(tools, "checks", lambda *_a, **_k: {})  # versions aren't the point here
    cfg = Tools(mkvmerge="", deezy="", dee="", truehdd="", qaac="", ffmpeg="", dee_shim=str(tmp_path / "none.exe"))
    ddp71 = NS(action=AudioAction.DDP, options={}, out_layout=NS(channels=8))
    bluray = NS(action=AudioAction.DDP, options={"ddp_mode": "bluray"}, out_layout=NS(channels=8))
    atmos = NS(action=AudioAction.ATMOS, options={"atmos_mode": "standard"}, out_layout=NS(channels=8))
    streaming = NS(action=AudioAction.ATMOS, options={}, out_layout=NS(channels=6))
    issues = _dee_issues(NS(audio=[ddp71, bluray, atmos, streaming]), cfg)
    assert [i.code for i in issues] == ["tools.dee_shim", "tools.dee_shim"]
    assert issues[0].message.startswith("DDP (DEE) 7.1 needs dee_shim")
    assert issues[1].message.startswith("DDP Atmos (DEE) standard mode (7.1) needs dee_shim")
    # a rule set's Atmos mode counts too
    blocked = _dee_issues(NS(audio=[streaming]), cfg, AudioSettings(atmos_mode="bluray"))
    assert [i.code for i in blocked] == ["tools.dee_shim"]
    shim = tmp_path / "dee_shim.exe"
    shim.write_bytes(b"")
    assert _dee_issues(NS(audio=[ddp71, bluray, atmos, streaming]), replace(cfg, dee_shim=str(shim))) == []
