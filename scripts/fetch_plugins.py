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
from pathlib import Path
import sys
import sysconfig
import tomllib

from artifacts import ROOT, download, unpack

MANIFEST = ROOT / "vsplugins" / "manifest.toml"


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
    ap.add_argument("--scripts", type=Path, default=Path(sysconfig.get_path("purelib")),
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
