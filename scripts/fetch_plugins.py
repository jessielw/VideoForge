"""Download the Windows builds of the VapourSynth plugins in vsplugins/manifest.toml, and its Python filter scripts.

    uv run python scripts/fetch_plugins.py [--plugins DIR] [--scripts DIR] [--only NAME ...]

Plugins: each plugin's `win64` downloads, checked against their sha256, with the files named in `files` taken
out of the archive (a .dll/.bin download is the file itself), into --plugins (default tools/vs-plugins, the
folder videoforge.toml's vs_plugins points at). Scripts: each [[script]] into --scripts (default: the
site-packages of the checkout's .venv). The packaged filter scripts (awsmfunc, vsutil, ...) are the `filters`
extra: `uv sync --extra filters`. Downloads are cached in build/plugin-cache; .7z archives are
unpacked with 7-Zip's 7zr.exe (downloaded too).
"""

from __future__ import annotations

import argparse
import hashlib
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "vsplugins" / "manifest.toml"
CACHE = ROOT / "build" / "plugin-cache"
# 7-Zip's standalone console 7zr.exe (public domain), for the .7z plugin archives (some use BCJ2).
SEVENZIP = (
    "https://github.com/ip7z/7zip/releases/download/26.03/7zr.exe",
    "ad4c82fadcbdf93c03b4fc440f300509c7d60c5c2f4d183e35d9d70d6957037d",
)


def download(url: str, sha256: str) -> bytes:
    """url's bytes (from the cache when already fetched), checked against sha256."""
    cached = CACHE / sha256
    if cached.is_file():
        data = cached.read_bytes()
    else:
        print(f"  {url}", flush=True)
        with urllib.request.urlopen(url, timeout=120) as r:  # noqa: S310 - the manifest's https URLs
            data = r.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != sha256:
        sys.exit(f"{url}: sha256 {digest}, expected {sha256}")
    CACHE.mkdir(parents=True, exist_ok=True)
    cached.write_bytes(data)
    return data


def unpack(url: str, data: bytes, files: dict[str, str]) -> dict[str, bytes]:
    """{name: bytes} of the archive members files names ({name: path in the archive})."""
    name = url.rsplit("/", 1)[-1]
    if not name.endswith((".zip", ".whl", ".7z")):  # the download is the file
        return {name: data}
    if name.endswith((".zip", ".whl")):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            return {dest: z.read(member) for dest, member in files.items()}
    with tempfile.TemporaryDirectory() as tmp:
        exe = Path(tmp) / "7zr.exe"
        exe.write_bytes(download(*SEVENZIP))
        archive = Path(tmp) / "archive.7z"
        archive.write_bytes(data)
        out = Path(tmp) / "out"
        subprocess.run([exe, "x", "-y", f"-o{out}", archive, *files.values()], check=True, capture_output=True)
        missing = [m for m in files.values() if not (out / m).is_file()]
        if missing:
            sys.exit(f"{url}: not in the archive: {', '.join(missing)}")
        return {dest: (out / member).read_bytes() for dest, member in files.items()}


def fetch_plugins(manifest: dict, dest: Path, only: set[str]) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for plugin in manifest["plugin"]:
        if only and plugin["name"] not in only:
            continue
        downloads = plugin.get("win64")
        if not downloads:
            print(f"{plugin['name']}: no Windows build in the manifest")
            continue
        if isinstance(downloads, dict):
            downloads = [downloads]
        print(plugin["name"], flush=True)
        for d in downloads:
            for name, content in unpack(d["url"], download(d["url"], d["sha256"]), d.get("files", {})).items():
                (dest / name).parent.mkdir(parents=True, exist_ok=True)
                (dest / name).write_bytes(content)
                print(f"  -> {name}")


def fetch_scripts(manifest: dict, dest: Path, only: set[str]) -> None:
    if not dest.is_dir():
        sys.exit(f"no such folder: {dest} (run `uv sync` first, or pass --scripts)")
    for script in manifest.get("script", []):
        if only and script["name"] not in only:
            continue
        text = download(script["url"], script["sha256"]).decode("utf-8")
        for old, new in script.get("replace", {}).items():
            text = text.replace(old, new)
        (dest / f"{script['name']}.py").write_text(text, encoding="utf-8", newline="")
        print(f"{script['name']} -> {dest / script['name']}.py")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plugins", type=Path, default=ROOT / "tools" / "vs-plugins", help="where the plugins go")
    ap.add_argument("--scripts", type=Path, default=ROOT / ".venv" / "Lib" / "site-packages",
                    help="where the filter scripts go (a site-packages folder)")  # fmt: skip
    ap.add_argument("--no-plugins", action="store_true", help="only the scripts")
    ap.add_argument("--no-scripts", action="store_true", help="only the plugins")
    ap.add_argument("--only", nargs="+", default=[], metavar="NAME", help="just these plugins/scripts")
    args = ap.parse_args()

    manifest = tomllib.loads(MANIFEST.read_text(encoding="utf-8"))
    only = set(args.only)
    known = {e["name"] for e in manifest["plugin"] + manifest.get("script", [])}
    if unknown := only - known:
        sys.exit(f"not in the manifest: {', '.join(sorted(unknown))}")
    if not args.no_plugins:
        fetch_plugins(manifest, args.plugins.resolve(), only)
    if not args.no_scripts:
        fetch_scripts(manifest, args.scripts.resolve(), only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
