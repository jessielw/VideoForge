"""Per-job working folders: `<source>_tmp/` next to the source.

StaxRip's folder is `<source>_temp/`; ours has its own name so neither tool
touches the other's files. It holds the encoded audio and the encoders' scratch
files, and is kept after the job until the user removes it (or a finished job's
is deleted: AppConfig.delete_work_dir; its records are kept first, keep_records).
"""

from __future__ import annotations

from pathlib import Path
import shutil

SUFFIX = "_tmp"
LOG_NAME = "videoforge.log"
RECORD_GLOB = "*.videoforge.json"  # record.RECORD_SUFFIX
KEPT_LOG_SUFFIX = ".videoforge.log"
KEEP_RECORDS = 100  # of each kind (records, logs) in the folder keep_records copies to


def work_dir(source: Path) -> Path:
    return source.with_name(source.name + SUFFIX)


def remove_work_dir(source: Path) -> bool:
    """Delete a source's working folder; False if there was none. Raises OSError when a file can't go."""
    folder = work_dir(source)
    if not folder.is_dir():
        return False
    shutil.rmtree(folder)
    return True


def keep_records(source: Path, dest: Path, keep: int = KEEP_RECORDS) -> dict[str, Path]:
    """Copy a work folder's job records and its log into dest before the folder is deleted: the records
    by their own names, the log as `<source name>.videoforge.log`. dest keeps the newest `keep` of each.
    Returns {original file name: its copy}."""
    folder = work_dir(source)
    files = [(p, p.name) for p in sorted(folder.glob(RECORD_GLOB))]
    if (folder / LOG_NAME).is_file():
        files.append((folder / LOG_NAME, source.name + KEPT_LOG_SUFFIX))
    if not files:
        return {}
    dest.mkdir(parents=True, exist_ok=True)
    copied = {}
    for path, name in files:
        shutil.copyfile(path, dest / name)  # a fresh mtime: the newest copies are the ones kept
        copied[path.name] = dest / name
    for pattern in (RECORD_GLOB, "*" + KEPT_LOG_SUFFIX):
        old = sorted(dest.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)[keep:]
        for path in old:
            path.unlink(missing_ok=True)
    return copied
