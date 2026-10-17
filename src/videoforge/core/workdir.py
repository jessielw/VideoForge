"""Per-job working folders: `<source>_tmp/` next to the source.

StaxRip's folder is `<source>_temp/`; ours has its own name so neither tool
touches the other's files. It holds the encoded audio and the encoders' scratch
files, and is kept after the job until the user removes it (or a finished job's
is deleted: AppConfig.delete_work_dir; its records are kept first, keep_records).
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import threading
import time

SUFFIX = "_tmp"
LOG_NAME = "videoforge.log"
FINISHED_NAME = "finished-steps.json"  # finished files, for any job on the source (note_finished)
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


@dataclass(frozen=True, slots=True)
class FinishedFile:
    """A file a step wrote and finished, as it was then: a file whose size or mtime changed since doesn't count."""

    step: str  # the step id that wrote it
    fingerprint: str  # that step's fingerprint (same as a step now = made with the same settings)
    size: int
    mtime_ns: int
    seconds: float  # how long the step took
    at: float  # when it finished (epoch seconds)


_finished_lock = threading.Lock()  # audio steps finish on several threads


def note_finished(folder: Path, step: str, fingerprint: str, outputs: list[Path], seconds: float) -> None:
    """Note a finished step's outputs in the folder's finished-steps.json, so any job on the source (a rerun,
    a re-added job, a variant with another label) can offer them for reuse. Never raises."""
    try:
        with _finished_lock:
            path = folder / FINISHED_NAME
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                doc = {}
            for out in outputs:
                if out.parent == folder and out.is_file():
                    st = out.stat()
                    doc[out.name] = {
                        "step": step,
                        "fingerprint": fingerprint,
                        "size": st.st_size,
                        "mtime_ns": st.st_mtime_ns,
                        "seconds": seconds,
                        "at": time.time(),
                    }
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(json.dumps(doc, indent=1), encoding="utf-8")
            os.replace(tmp, path)
    except OSError:
        pass


def finished_files(folder: Path) -> dict[str, FinishedFile]:
    """The folder's finished files that are still as their step left them, by file name."""
    try:
        doc = json.loads((folder / FINISHED_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    found = {}
    for name, d in doc.items() if isinstance(doc, dict) else ():
        try:
            f = FinishedFile(d["step"], d["fingerprint"], d["size"], d["mtime_ns"], d["seconds"], d["at"])
            st = (folder / name).stat()
        except (OSError, KeyError, TypeError):
            continue
        if (st.st_size, st.st_mtime_ns) == (f.size, f.mtime_ns):
            found[name] = f
    return found


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
