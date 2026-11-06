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
    out = config._resolve_tool(str(exe), tmp_path)
    assert out != str(exe)
    assert str(exe) in open(out).read()
    monkeypatch.setattr(sys, "platform", "win32")
    assert config._resolve_tool(str(exe), tmp_path) == str(exe)
