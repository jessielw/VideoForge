"""Per-job working folders: `<source>_tmp/` next to the source.

StaxRip's folder is `<source>_temp/`; ours has its own name so neither tool
touches the other's files. It holds the encoded audio and the encoders' scratch
files, and is kept after the job until the user removes it.
"""

from __future__ import annotations

import shutil
from pathlib import Path

SUFFIX = "_tmp"


def work_dir(source: Path) -> Path:
    return source.with_name(source.name + SUFFIX)


def remove_work_dir(source: Path) -> bool:
    """Delete a source's working folder; False if there was none."""
    folder = work_dir(source)
    if not folder.is_dir():
        return False
    shutil.rmtree(folder)
    return True
