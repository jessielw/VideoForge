"""Finding Dolby Encoding Engine (DEE) in either of its shapes.

Older DEE is one program (`dee`). Newer releases and Dolby Media Encoder ship a folder of encoders instead
(`dee_ddp_encoder`, `dee_ddpjoc_encoder`, ...), and DeeZy's --dee takes that folder. Under Wine the same folder
holds launchers (Docker) or `.exe` files (Windows), so both spellings count.
"""

from __future__ import annotations

from pathlib import Path
import shutil

# DeeZy's own marker: always present in a split set
SPLIT_MARKER = "dee_ddp_encoder"


def _marker(folder: Path) -> Path | None:
    for name in (SPLIT_MARKER, f"{SPLIT_MARKER}.exe"):
        if (folder / name).is_file():
            return folder / name
    return None


def split_folder(path: str) -> str:
    """The folder of split encoders a configured `dee` value means: the folder itself, or, for a bare `dee`
    with no single program by that name, wherever the split encoders are on PATH. "" when neither."""
    if not path:
        return ""
    p = Path(path)
    if p.is_file() and p.stem.lower().startswith("dee_") and p.stem.lower().endswith("_encoder"):
        return str(p.parent)  # one split encoder picked: DeeZy needs the set, or it runs it as the single dee
    if p.is_dir():
        return str(p) if _marker(p) else ""
    if p.name.lower() in ("dee", "dee.exe") and not p.is_file() and not shutil.which(path):
        for name in (SPLIT_MARKER, f"{SPLIT_MARKER}.exe"):
            if found := shutil.which(name):
                return str(Path(found).parent)
    return ""


def program(found: str) -> str:
    """What to run to ask DEE about itself: the file, or one encoder from a split folder."""
    p = Path(found)
    if p.is_dir() and (marker := _marker(p)):
        return str(marker)
    return found
