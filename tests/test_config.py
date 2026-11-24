"""The app folder (VIDEOFORGE_ROOT) and `python -m videoforge`, which the portable build's launcher relies on."""

import os
import subprocess
import sys


def test_videoforge_root_moves_the_app_folder(tmp_path):
    code = "from videoforge.core.config import PROJECT_ROOT; print(PROJECT_ROOT)"
    env = {**os.environ, "VIDEOFORGE_ROOT": str(tmp_path)}
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == str(tmp_path)


def test_python_m_videoforge_runs_the_cli():
    out = subprocess.run([sys.executable, "-m", "videoforge", "--help"], capture_output=True, text=True, check=False)
    assert out.returncode == 0, out.stderr
    assert "serve" in out.stdout


def test_exe_path_runs_through_wine_on_linux(tmp_path, monkeypatch):
    import sys

    from videoforge.core import config

    exe = tmp_path / "qaac64.exe"
    exe.write_bytes(b"MZ")
    wine = tmp_path / "wine-run"
    wine.write_text("#!/bin/sh\n")
    monkeypatch.setattr(config, "WINE_RUN", str(wine))
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(config.os, "getuid", lambda: 1000, raising=False)
    monkeypatch.setattr(config.tempfile, "gettempdir", lambda: str(tmp_path))
    out = config._resolve_tool("qaac", str(exe), tmp_path)
    assert out != str(exe)
    assert str(exe) in open(out).read()
    monkeypatch.setattr(sys, "platform", "win32")
    assert config._resolve_tool("qaac", str(exe), tmp_path) == str(exe)


def test_wine_launcher_shows_the_exe_and_tools_folder_is_found(tmp_path, monkeypatch):
    import sys

    from videoforge.core import config

    exe = tmp_path / "tools" / "qaac64.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"MZ")
    wine = tmp_path / "wine-run"
    wine.write_text("#!/bin/sh\n")
    monkeypatch.setattr(config, "WINE_RUN", str(wine))
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(config.os, "getuid", lambda: 1000, raising=False)
    monkeypatch.setattr(config.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(config.shutil, "which", lambda name: None)
    monkeypatch.setattr(config, "_TOOLS_FOLDER", {"qaac": (str(exe),)})
    launcher = config._resolve_tool("qaac", "qaac", tmp_path)  # not on PATH: found in the tools folder
    assert launcher != "qaac"
    assert config.wine_target(launcher) == str(exe)
    assert config.wine_target(str(exe)) == ""


def test_mkvtoolnix_english_is_named_by_its_platform(tmp_path, monkeypatch):
    from videoforge.core import config

    monkeypatch.setattr(config.sys, "platform", "linux")
    monkeypatch.setattr(config.shutil, "which", lambda name: None)
    assert config.mkv_ui("/usr/bin/mkvextract") == ("--ui-language", "en_US")  # native Linux refuses "en"
    assert config.mkv_ui("/tools/wine/mkvextract.exe") == ("--ui-language", "en")
    launcher = tmp_path / "videoforge-wine-1000" / "mkvextract"
    launcher.parent.mkdir()
    launcher.write_text('#!/bin/sh\nexec wine "C:/MKVToolNix/mkvextract.exe" "$@"\n')
    assert config.mkv_ui(str(launcher)) == ("--ui-language", "en")  # a Windows build under Wine
    monkeypatch.setattr(config.sys, "platform", "win32")
    assert config.mkv_ui("mkvextract") == ("--ui-language", "en")


def test_dee_is_its_tools_folder_also_from_an_old_dee_exe_path(tmp_path):
    """DEE 6.7 is a folder of tools: a config naming one of them, or the dee.exe an older DEE had, means the folder."""
    from videoforge.core import config

    folder = tmp_path / "tools" / "DEE"
    folder.mkdir(parents=True)
    (folder / "dee_ddp_encoder.exe").write_bytes(b"")
    for value in ("tools/DEE", "tools/DEE/dee.exe", "tools/DEE/dee_ddp_encoder.exe"):
        assert config._resolve_tool("dee", value, tmp_path) == str(folder)
    assert config._resolve_tool("dee", "tools/none/dee.exe", tmp_path) == "tools/none/dee.exe"  # missing: as given
