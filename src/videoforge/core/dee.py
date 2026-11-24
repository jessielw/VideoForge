"""Finding Dolby Encoding Engine (DEE) 6.7, the only DEE DeeZy 2 runs.

DEE 6.7 is a folder of command-line tools, one per job (`dee_ddp_encoder`, `dee_ddpjoc_encoder`, ...), and DeeZy's
--dee takes that folder. The configured `dee` value may name the folder, one of its tools, a `dee.exe` left from an
older DEE's config, or (Docker) a bare name with the folder on PATH. The tools are `.exe` files on Windows.
"""

from __future__ import annotations

from pathlib import Path
import re
import shutil

MARKER = "dee_ddp_encoder"  # in every DEE 6.7 folder; DeeZy finds the folder by it too
SUPPORTED = "6.7"  # DeeZy 2 refuses any other DEE version
VERSION = re.compile(r"Dolby Encoding Engine version (\S+)")  # `dee_ddp_encoder --help`: "... version 6.7.0+8e353f99"


def marker(folder: Path) -> Path | None:
    """The folder's dee_ddp_encoder, or None when it isn't a DEE tools folder."""
    for name in (MARKER, f"{MARKER}.exe"):
        if (folder / name).is_file():
            return folder / name
    return None


def folder(path: str) -> str:
    """The DEE tools folder a configured `dee` value means: the folder itself; the folder of a path in it (one of
    its tools, or an old `dee.exe` that may be gone); for a bare name, wherever dee_ddp_encoder is on PATH.
    "" when none of these is a DEE tools folder."""
    if not path:
        return ""
    p = Path(path)
    if p.is_dir():
        return str(p) if marker(p) else ""
    if len(p.parts) > 1:
        return str(p.parent) if p.parent.is_dir() and marker(p.parent) else ""
    found = shutil.which(MARKER)
    return str(Path(found).parent) if found else ""


def program(found: str) -> str:
    """What to run to ask DEE about itself: the folder's dee_ddp_encoder (`--help` prints the version)."""
    p = Path(found)
    return str(marker(p) or found) if p.is_dir() else found


def version(output: str) -> str:
    """DEE's version in a tool's `--help` output ("6.7.0+8e353f99"), or "" when it prints none."""
    match = VERSION.search(output)
    return match.group(1) if match else ""


def supported(version_text: str) -> bool:
    """True for a DEE version DeeZy 2 runs (6.7.x)."""
    return version_text.startswith(f"{SUPPORTED}.")
