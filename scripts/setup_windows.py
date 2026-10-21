"""Set up a Windows x64 development checkout and verify its bundled toolchain.

    uv run python scripts/setup_windows.py [--skip-frontend]

Requires uv and Node.js/npm. Uses the same pinned tool/plugin fetchers as the release.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess

from artifacts import ROOT
from fetch_tools import require_windows


def run(*argv: str | Path, cwd: Path = ROOT) -> None:
    print(">", " ".join(str(a) for a in argv), flush=True)
    subprocess.run([str(a) for a in argv], cwd=cwd, check=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skip-frontend", action="store_true", help="keep the existing frontend build")
    args = ap.parse_args()
    try:
        require_windows()
        uv = shutil.which("uv")
        npm = shutil.which("npm")
        if not uv or (not args.skip_frontend and not npm):
            raise ValueError("install uv and Node.js/npm first (or --skip-frontend for an existing frontend build)")
        run(uv, "sync", "--frozen", "--extra", "desktop", "--extra", "filters")
        python = ROOT / ".venv" / "Scripts" / "python.exe"
        run(python, ROOT / "scripts" / "fetch_tools.py", "--runtime-dir", ROOT / ".venv" / "Scripts")
        run(python, ROOT / "scripts" / "fetch_plugins.py")
        if not args.skip_frontend:
            run(npm, "ci", cwd=ROOT / "frontend")
            run(npm, "run", "build", cwd=ROOT / "frontend")
        if not (ROOT / "frontend" / "dist" / "index.html").is_file():
            raise ValueError("no built frontend; rerun without --skip-frontend")
        run(python, ROOT / "scripts" / "verify_toolchain.py", "--smoke")
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        ap.exit(1, f"Windows setup failed: {error}\n")
    print("Setup verified. Start VideoForge: uv run videoforge serve --window")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
