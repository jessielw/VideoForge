"""The engine stays UI-free and group-neutral: profiles and the server plug into it, never the reverse."""

from __future__ import annotations

import subprocess
import sys


def test_core_imports_no_ui_and_no_profile():
    code = (
        "import pkgutil, importlib, sys, videoforge.core as core\n"
        "for m in pkgutil.walk_packages(core.__path__, 'videoforge.core.'): importlib.import_module(m.name)\n"
        "bad = sorted(m for m in sys.modules if m.startswith(('PySide6', 'fastapi', 'starlette', 'uvicorn',"
        " 'videoforge.profiles', 'videoforge.server')))\n"
        "assert not bad, bad\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_videoforge_imports_no_profile_package():
    """Group profiles are separate packages found through entry points; no module here may import one."""
    code = (
        "import pkgutil, importlib, sys, videoforge\n"
        "for m in pkgutil.walk_packages(videoforge.__path__, 'videoforge.'): importlib.import_module(m.name)\n"
        "bad = sorted(m for m in sys.modules if m.startswith('videoforge') and m.split('.')[0] != 'videoforge')\n"
        "assert not bad, bad\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
