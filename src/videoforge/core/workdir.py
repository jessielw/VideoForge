"""Working folders: `<source>_tmp/` next to the source, with a folder per job in it.

StaxRip's folder is `<source>_temp/`; ours has its own name so neither tool
touches the other's files. Its top holds what comes from the source alone (the
index, an enhancement layer, HDR metadata, burn-in extracts), which every job on
the source shares. Each job's own files are in `<label>/` (`main/` without a
label): its script, encodes, chapters, log and records, so the jobs of one source
(dubbed, subbed, 720p) keep theirs apart. The folder is kept after the job until
the user removes it (or a finished job's
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
MAIN = "main"  # the job folder of a job without a label
LOG_NAME = "videoforge.log"
FINISHED_NAME = "finished-steps.json"  # finished files, for any job on the source (note_finished)
RECORD_GLOB = "*.videoforge.json"  # record.RECORD_SUFFIX
KEPT_LOG_SUFFIX = ".videoforge.log"
KEEP_RECORDS = 100  # of each kind (records, logs) in the folder keep_records copies to


def work_dir(source: Path) -> Path:
    return source.with_name(source.name + SUFFIX)


def job_dir(source: Path, label: str) -> Path:
    """A job's own folder in its source's work folder: by its label (a file name already: clean_label)."""
    return work_dir(source) / (label or MAIN)


def remove_work_dir(source: Path) -> bool:
    """Delete a source's working folder; False if there was none. Raises OSError when a file can't go."""
    folder = work_dir(source)
    if not folder.is_dir():
        return False
    shutil.rmtree(folder)
    return True


def clean_work_dir(source: Path, records_dir: Path | None) -> dict[Path, Path]:
    """Archive provenance before deleting working files. An archive failure leaves the folder intact."""
    if records_dir is None:
        raise OSError("No records folder configured; working files were kept")
    kept = keep_records(source, records_dir)
    remove_work_dir(source)
    return kept


def work_dir_size(source: Path) -> int:
    """Size for the cleanup confirmation; never descend into linked folders."""

    def failed(error: OSError) -> None:
        raise error

    if not work_dir(source).exists():
        return 0
    size = 0
    for here, dirs, files in os.walk(work_dir(source), onerror=failed):
        dirs[:] = [d for d in dirs if not (p := Path(here, d)).is_symlink() and not p.is_junction()]
        size += sum(Path(here, name).lstat().st_size for name in files)
    return size


@dataclass(frozen=True, slots=True)
class FinishedFile:
    """A file a step wrote and finished, as it was then: a file whose size or mtime changed since doesn't count."""

    step: str  # the step id that wrote it
    fingerprint: str  # that step's fingerprint (same as a step now = made with the same settings)
    size: int
    mtime_ns: int
    seconds: float  # how long the step took
    at: float  # when it finished (epoch seconds)
    portable: str = ""  # Step.portable_fingerprint: the same in any job's folder (pipeline/share.py)


_finished_lock = threading.Lock()  # audio steps finish on several threads


def note_finished(
    folder: Path, step: str, fingerprint: str, outputs: list[Path], seconds: float, portable: str = ""
) -> None:
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
                        "portable": portable,
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
            f = FinishedFile(
                d["step"], d["fingerprint"], d["size"], d["mtime_ns"], d["seconds"], d["at"], d.get("portable", "")
            )
            st = (folder / name).stat()
        except (OSError, KeyError, TypeError):
            continue
        if (st.st_size, st.st_mtime_ns) == (f.size, f.mtime_ns):
            found[name] = f
    return found


def forget_finished(outputs: tuple[Path, ...]) -> None:
    """Invalidate completion before a step replaces files, including a run that later fails."""
    with _finished_lock:
        for folder in {p.parent for p in outputs}:
            path = folder / FINISHED_NAME
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(doc, dict):
                    continue
                for out in outputs:
                    if out.parent == folder:
                        doc.pop(out.name, None)
                tmp = path.with_name(path.name + ".tmp")
                tmp.write_text(json.dumps(doc, indent=1), encoding="utf-8")
                os.replace(tmp, path)
            except (OSError, ValueError):
                continue


def keep_records(source: Path, dest: Path, keep: int = KEEP_RECORDS) -> dict[Path, Path]:
    """Copy a work folder's job records and logs into dest before the folder is deleted: the records
    by their own names, a job folder's log as `<source name>.<label>.videoforge.log` (`main`'s, and one
    at the top from before job folders, as `<source name>.videoforge.log`). dest keeps the newest `keep`
    of each. Returns {original file: its copy}."""
    folder = work_dir(source)
    files = [(p, p.name) for p in sorted([*folder.glob(RECORD_GLOB), *folder.glob("*/" + RECORD_GLOB)])]
    for log in sorted([*folder.glob(LOG_NAME), *folder.glob("*/" + LOG_NAME)]):
        label = "" if log.parent in (folder, folder / MAIN) else f".{log.parent.name}"
        files.append((log, source.name + label + KEPT_LOG_SUFFIX))
    if not files:
        return {}
    dest.mkdir(parents=True, exist_ok=True)
    copied = {}
    for path, name in files:
        shutil.copyfile(path, dest / name)  # a fresh mtime: the newest copies are the ones kept
        copied[path] = dest / name
    for pattern in (RECORD_GLOB, "*" + KEPT_LOG_SUFFIX):
        old = sorted(dest.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)[keep:]
        for path in old:
            path.unlink(missing_ok=True)
    return copied
