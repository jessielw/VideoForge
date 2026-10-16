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
