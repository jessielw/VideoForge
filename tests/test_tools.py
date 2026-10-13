"""Tool detection for the Settings page, and tool paths layered over videoforge.toml."""

from __future__ import annotations

import sys
from pathlib import Path

from videoforge.core.config import AppConfig, Tools, with_tools
from videoforge.core.tools import TOOL_NAMES, TOOLS, ToolStatus, check, detect, version_line

INFO = {t.name: t for t in TOOLS}


def test_version_lines_from_real_tool_output():
    assert version_line("mkvmerge v100.0 ('Do Hot Girls Like Chords') 64-bit\n") == (
        "mkvmerge v100.0 ('Do Hot Girls Like Chords') 64-bit")
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


def test_a_real_program_on_path():
    c = check(INFO["ffmpeg"], sys.executable, runner=lambda argv, t: __import__("subprocess").run(
        [argv[0], "--version"], capture_output=True, text=True, timeout=t).stdout)
    assert c.status is ToolStatus.OK and c.version.startswith("Python 3.")


def test_plugin_folder(tmp_path):
    assert check(INFO["vs_plugins"], str(tmp_path / "none")).status is ToolStatus.MISSING
    (tmp_path / "BestSource.dll").write_bytes(b"")
    (tmp_path / "ffms2.dll").write_bytes(b"")
    (tmp_path / "readme.txt").write_bytes(b"")
    c = check(INFO["vs_plugins"], str(tmp_path))
    assert c.status is ToolStatus.OK and c.detail == "2 plugins; source filters: BestSource, FFMS2"
    empty = tmp_path / "empty"
    empty.mkdir()
    assert check(INFO["vs_plugins"], str(empty)).status is ToolStatus.UNKNOWN


def test_detect_covers_every_tool_in_order(tmp_path):
    tools = Tools(**{name: str(tmp_path / name) for name in TOOL_NAMES})
    assert [c.name for c in detect(tools, runner=lambda *_: "v1")] == list(TOOL_NAMES)


def test_with_tools_layers_paths_and_brings_mkvpropedit(tmp_path):
    (tmp_path / "mkv").mkdir()
    for exe in ("mkvmerge.exe", "mkvpropedit.exe"):
        (tmp_path / "mkv" / exe).write_bytes(b"")
    base = AppConfig(tools=Tools(mkvmerge="mkvmerge", deezy="deezy", dee="dee", truehdd="truehdd", qaac="qaac",
                                 ffmpeg="ffmpeg"))
    cfg = with_tools(base, {"mkvmerge": "mkv/mkvmerge.exe", "x264": "", "qaac": str(tmp_path / "q.exe")}, tmp_path)
    assert cfg.tools.mkvmerge == str(tmp_path / "mkv" / "mkvmerge.exe")
    assert cfg.tools.mkvpropedit == str(tmp_path / "mkv" / "mkvpropedit.exe")  # came along
    assert cfg.tools.x264 == "x264"  # an empty value keeps the base
    assert cfg.tools.qaac == str(Path(tmp_path / "q.exe"))
    assert base.tools.mkvmerge == "mkvmerge"  # the base is untouched
