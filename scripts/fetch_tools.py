"""Download the Windows builds of the free tools VideoForge bundles (dovi_tool, hdr10plus_tool) into tools/.

    uv run python scripts/fetch_tools.py [--tools DIR] [--only NAME ...]

Each tool's pinned release zip, checked against its sha256 (cached in build/plugin-cache, as
scripts/fetch_plugins.py does), with its files taken out into --tools (default tools/, where
videoforge.toml points). The Docker image takes the same versions' Linux builds (Dockerfile).
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from fetch_plugins import ROOT, download, unpack

# name: (url, sha256, {path in the tools folder: path in the archive})
TOOLS = {
    "dovi_tool": (  # quietvoid/dovi_tool, MIT: Dolby Vision RPU extract / edit / demux
        "https://github.com/quietvoid/dovi_tool/releases/download/2.3.4/dovi_tool-2.3.4-x86_64-pc-windows-msvc.zip",
        "0d9733d311dfe49f9dca0c350f7e6d978182673d333c6f07f7365daf9e6c81eb",
        {"dovi_tool/dovi_tool.exe": "dovi_tool.exe"},
    ),
    "hdr10plus_tool": (  # quietvoid/hdr10plus_tool, MIT: HDR10+ metadata extract
        "https://github.com/quietvoid/hdr10plus_tool/releases/download/1.7.2/hdr10plus_tool-1.7.2-x86_64-pc-windows-msvc.zip",
        "82b2d560073941b14c6511a431f429e33e134e5caefb60d7e8f6f6e6da8e16ba",
        {"hdr10plus_tool/hdr10plus_tool.exe": "hdr10plus_tool.exe"},
    ),
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tools", type=Path, default=ROOT / "tools", help="the tools folder")
    ap.add_argument("--only", nargs="+", default=[], metavar="NAME", help="just these tools")
    args = ap.parse_args()
    if unknown := set(args.only) - TOOLS.keys():
        sys.exit(f"unknown tools: {', '.join(sorted(unknown))}")
    dest: Path = args.tools.resolve()
    for name, (url, sha256, files) in TOOLS.items():
        if args.only and name not in args.only:
            continue
        print(name, flush=True)
        for path, content in unpack(url, download(url, sha256), files).items():
            (dest / path).parent.mkdir(parents=True, exist_ok=True)
            (dest / path).write_bytes(content)
            print(f"  -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
