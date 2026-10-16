"""Build the portable VideoForge folder and its zip (Windows x64 for now).

    uv run python scripts/build_portable.py [--skip-frontend] [--out build/portable]

The folder holds a standalone Python (the python-build-standalone build uv installs) with VideoForge and its
locked dependencies installed in it, the built frontend, videoforge.toml, an empty tools/, and VideoForge.exe,
which runs `python -m videoforge serve --window` with VIDEOFORGE_ROOT set to the folder. A real Python is the
point: vspipe embeds it, and the preview worker is `python -m`. Unpacked anywhere, it runs from there. The
VapourSynth plugins and filter scripts of vsplugins/manifest.toml come with it (scripts/fetch_plugins.py).
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
PYTHON = "3.12"
CSC = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")

TOOLS_README = """Put the tools here (or anywhere, and set their paths on the Settings page):

  MKVToolNix\\mkvmerge.exe   x264\\x264.exe   x265\\x265.exe
  vs-plugins\\ already holds the VapourSynth plugins VideoForge bundles (source filters, common filters): add yours
  DeeZy\\deezy.exe   DEE\\dee.exe   truehdd\\truehdd.exe   qaac\\qaac64.exe   opus-tools\\opusenc.exe
  ffmpeg and MP4Box are looked up on PATH unless set.

See README.md, "Tools".
"""

CONSOLE_CMD = """@echo off
rem The console way in: `videoforge serve` (logs in this window), `videoforge --help`.
set "VIDEOFORGE_ROOT=%~dp0."
"%~dp0runtime\\python.exe" -m videoforge %*
"""


def run(*cmd: str | Path, cwd: Path = ROOT) -> None:
    print(">", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], cwd=cwd, check=True)


def version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def frontend() -> Path:
    npm = shutil.which("npm")
    if not npm:
        sys.exit("npm wasn't found (needed to build the frontend; or pass --skip-frontend after building it)")
    run(npm, "ci", cwd=ROOT / "frontend")
    run(npm, "run", "build", cwd=ROOT / "frontend")
    return ROOT / "frontend" / "dist"


def standalone_python(cache: Path, dest: Path) -> Path:
    """uv's standalone CPython, copied to dest; returns its python.exe."""
    run("uv", "python", "install", PYTHON, "--install-dir", cache)
    found = sorted(p for p in cache.glob(f"cpython-{PYTHON}.*-windows-x86_64-none") if p.is_dir())
    if not found:
        sys.exit(f"no CPython {PYTHON} in {cache}")
    shutil.copytree(found[-1], dest)
    # uv marks its Pythons as externally managed; this one is ours to install into.
    (dest / "Lib" / "EXTERNALLY-MANAGED").unlink(missing_ok=True)
    return dest / "python.exe"


def install(python: Path, work: Path) -> None:
    """The locked dependencies (with the desktop and filters extras), then VideoForge itself."""
    reqs = work / "requirements.txt"
    run(
        "uv", "export", "--frozen", "--no-dev", "--extra", "desktop", "--extra", "filters", "--no-hashes",
        "--no-emit-project", "--no-header", "--output-file", reqs,
    )  # fmt: skip
    run("uv", "pip", "install", "--python", python, "--link-mode", "copy", "--requirement", reqs)
    run("uv", "pip", "install", "--python", python, "--link-mode", "copy", "--no-deps", "--reinstall-package",
        "videoforge", ROOT)  # fmt: skip


def launcher(python: Path, folder: Path, work: Path) -> None:
    if not CSC.is_file():
        sys.exit(f"csc.exe wasn't found at {CSC} (.NET Framework 4, part of Windows)")
    icon = work / "videoforge.ico"
    run(python, "-c", f"from videoforge.desktop import app_icon; app_icon().save(r'{icon}', sizes=[(16, 16), "
        "(32, 32), (48, 48), (256, 256)])")  # fmt: skip
    run(CSC, "/nologo", "/optimize", "/target:winexe", f"/win32icon:{icon}", f"/out:{folder / 'VideoForge.exe'}",
        ROOT / "scripts" / "launcher" / "VideoForge.cs")  # fmt: skip
    (folder / "videoforge.cmd").write_text(CONSOLE_CMD.replace("\n", "\r\n"), encoding="ascii")


def main() -> int:
    if sys.platform != "win32":
        sys.exit("the portable build is Windows only for now")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=ROOT / "build" / "portable", help="where the folder and zip go")
    ap.add_argument("--skip-frontend", action="store_true", help="use the frontend/dist already built")
    args = ap.parse_args()

    out: Path = args.out.resolve()
    folder = out / "VideoForge"
    work = out / "work"
    if folder.exists():
        shutil.rmtree(folder)
    work.mkdir(parents=True, exist_ok=True)

    dist = ROOT / "frontend" / "dist" if args.skip_frontend else frontend()
    if not (dist / "index.html").is_file():
        sys.exit(f"no built frontend in {dist}")

    python = standalone_python(work / "python", folder / "runtime")
    install(python, work)
    shutil.copytree(dist, folder / "frontend" / "dist")
    for name in ("videoforge.toml", "README.md", "CHANGELOG.md", "LICENSE"):
        shutil.copy2(ROOT / name, folder / name)
    (folder / "tools").mkdir()
    run(sys.executable, ROOT / "scripts" / "fetch_plugins.py", "--plugins", folder / "tools" / "vs-plugins",
        "--scripts", folder / "runtime" / "Lib" / "site-packages")  # fmt: skip
    (folder / "tools" / "README.txt").write_text(TOOLS_README.replace("\n", "\r\n"), encoding="utf-8")
    launcher(python, folder, work)

    zip_base = out / f"VideoForge-{version()}-windows-x64"
    archive = shutil.make_archive(str(zip_base), "zip", out, folder.name)
    size = Path(archive).stat().st_size / 2**20
    print(f"\n{folder}\n{archive} ({size:.0f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
