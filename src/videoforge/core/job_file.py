"""A job's file (StaxRip's project file): its whole spec, saved in its folder in the source's work folder, so
the job can be added again exactly as it was. Written when a run starts (and on request), read back by an
import, which takes the file itself, a job folder, or a source's work folder (every job in it).

The spec only: a job added from a file starts fresh (probed again, planned again, its template and the
profile's defaults left alone). Its work folder is where it was, so a run reuses what it finished there."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import json
from pathlib import Path
from typing import Any
import uuid

from videoforge.core.job import JobSpec
from videoforge.core.plan_io import from_json, to_json

FILE_NAME = "videoforge-job.json"
VERSION = 1


def write(spec: JobSpec) -> Path:
    """The job's file in its own folder (made if it isn't there yet). Raises OSError."""
    path = spec.job_dir / FILE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {"videoforge_job": VERSION, "saved": datetime.now().astimezone().isoformat(timespec="seconds")}
    doc["job"] = to_json(spec)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def find(path: Path) -> list[Path]:
    """The job files at path: the file itself, or those in a folder and in its folders one level down (a
    source's work folder holds one folder per job). Raises FileNotFoundError."""
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise FileNotFoundError(path)
    found = [path / FILE_NAME] if (path / FILE_NAME).is_file() else []
    found += sorted(p / FILE_NAME for p in path.iterdir() if p.is_dir() and (p / FILE_NAME).is_file())
    return found


def read(path: Path) -> JobSpec:
    """The job a file holds, under a new id. Raises ValueError (not a job file, or from a newer version) or
    OSError."""
    try:
        doc: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as ex:
        raise ValueError(f"{path.name} is not a job file ({ex})") from None
    if not isinstance(doc, dict) or not isinstance(doc.get("job"), dict):
        raise ValueError(f"{path.name} is not a job file")
    if int(doc.get("videoforge_job", 0)) > VERSION:
        raise ValueError(f"{path.name} was saved by a newer VideoForge")
    try:
        spec: JobSpec = from_json(JobSpec, doc["job"])
    except (KeyError, TypeError, ValueError, AttributeError) as ex:
        raise ValueError(f"{path.name} could not be read ({type(ex).__name__}: {ex})") from None
    return replace(spec, id=uuid.uuid4().hex[:12])
