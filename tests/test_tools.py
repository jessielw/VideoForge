"""Tool detection for the Settings page, and tool paths layered over videoforge.toml."""

from __future__ import annotations

from pathlib import Path
import sys

from conftest import audio, plan_for, source, sub

from videoforge.core import tools
from videoforge.core.config import AppConfig, Tools, with_tools
from videoforge.core.dee import split_folder
from videoforge.core.models import AudioAction, AudioCodec as C, Severity, SubFormat
from videoforge.core.tools import (
    TOOL_NAMES,
    TOOLS,
    ToolStatus,
    check,
    detect,
    missing_for_encodes,
    tool_issues,
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
    exe = tmp_path / "dee.exe"
    exe.write_bytes(b"")
    calls = []

    def runner(argv, _timeout):
        calls.append(list(argv[1:]))
        return "Unknown option --version" if argv[1:] else "Dolby Encoding Engine\nVersion 5.2.1\n"

    c = check(INFO["dee"], str(exe), runner=runner)
    assert calls == [["--help"], []]
    assert (c.status, c.version, c.found) == (ToolStatus.OK, "Version 5.2.1", str(exe))


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
    c = check(INFO["dee"], str(tmp_path))
    assert (c.status, c.detail) == (ToolStatus.MISSING, "A folder: point at the program in it")
    exe = tmp_path / "dee"
    exe.write_bytes(b"")

    def denied(_argv, _timeout):
        raise PermissionError(13, "Permission denied")

    c = check(INFO["dee"], str(exe), runner=denied)
    assert c.status is ToolStatus.BROKEN and "Permission denied" in c.detail
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
    assert issues[0].message == "DDP (DEE) needs Dolby Encoding Engine: set it in Settings"
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


def test_dee_split_encoders_folder_is_found_and_asked_for_a_version(tmp_path, monkeypatch):
    marker = tmp_path / "dee_ddp_encoder.exe"
    marker.write_bytes(b"")
    calls = []

    def runner(argv, _timeout):
        calls.append(argv[0])
        return "dee_ddp_encoder Version 6.0.0\n"

    c = check(INFO["dee"], str(tmp_path), runner=runner)
    assert (c.status, c.found, calls) == (ToolStatus.OK, str(tmp_path), [str(marker)])

    # a bare "dee" with only the split encoders on PATH resolves to their folder
    marker.chmod(0o755)  # PATH lookup wants an executable file on POSIX
    monkeypatch.setenv("PATH", str(tmp_path))
    assert split_folder("dee") == str(tmp_path)
    for name in ("dee", "dee.exe"):  # PATHEXT finds the .exe on Windows, the bare name on POSIX
        single = tmp_path / name
        single.write_bytes(b"")
        single.chmod(0o755)
    assert split_folder("dee") == ""  # a single dee wins


def test_dee_split_encoder_file_means_its_folder(tmp_path):
    exe = tmp_path / "dee_ddp_encoder.exe"
    exe.write_bytes(b"")
    assert split_folder(str(exe)) == str(tmp_path)


def test_split_dee_blocks_bluray_and_warns_on_dialnorm(tmp_path):
    from types import SimpleNamespace as NS

    from videoforge.core.tools import _split_dee_issues

    (tmp_path / "dee_ddp_encoder.exe").write_bytes(b"")
    bd = NS(action=AudioAction.DDP, options={"ddp_mode": "bluray", "dialnorm": "-27"}, out_layout=NS(channels=8))
    plan = NS(audio=[bd])
    issues = _split_dee_issues(plan, NS(dee=str(tmp_path)))
    assert [i.severity for i in issues] == [Severity.BLOCK, Severity.WARN]
    single = tmp_path / "single"
    single.mkdir()
    (single / "dee.exe").write_bytes(b"")
    assert _split_dee_issues(plan, NS(dee=str(single / "dee.exe"))) == []


def test_friendly_errors_for_tools_that_cannot_start(monkeypatch):
    import errno

    from videoforge.core import tools

    monkeypatch.setattr(tools.os, "name", "posix")
    assert "Wine" in tools._friendly_error(OSError(errno.ENOEXEC, "x"), "/tools/wine/qaac/qaac64.exe")
    assert "PUID" in tools._friendly_error(PermissionError(errno.EACCES, "x"), "/tools/dee/dee")
    assert tools._friendly_error(OSError(errno.ENOENT, "x"), "/x") == ""
