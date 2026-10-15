"""Job history: how each finished output was built, as one JSON file per output.

Records live in the app data folder, never next to the release, keyed by the
output path (a re-run replaces the record). Fix mode reads them back to recover
the plan, overrides and the kept encodes; it must still work without one (old
releases, or a moved file), so nothing depends on a record existing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path

from videoforge.core.job import JobResult, JobStatus
from videoforge.core.models import Issue, Plan
from videoforge.core.plan_io import from_json, to_json

FORMAT_VERSION = 1


def app_data_dir() -> Path:
    base = os.environ.get("APPDATA") or os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "VideoForge"


@dataclass(slots=True)
class JobRecord:
    output: Path
    status: JobStatus
    finished: str  # ISO timestamp, local time
    plan: Plan
    issues: list[Issue] = field(default_factory=list)
    work_dir: Path | None = None
    encoded_audio: dict[int, Path] = field(default_factory=dict)  # plan.audio position -> encode in work_dir


class JobHistory:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or app_data_dir() / "history"

    def _path(self, output: Path) -> Path:
        key = os.path.normcase(str(output.resolve()))
        return self.root / (hashlib.sha1(key.encode("utf-8"), usedforsecurity=False).hexdigest()[:16] + ".json")

    def record(self, result: JobResult) -> JobRecord | None:
        """Save a finished job; only jobs that wrote an output (done or invalid) are kept."""
        if result.output is None or result.status not in (JobStatus.DONE, JobStatus.INVALID):
            return None
        rec = JobRecord(
            output=result.output,
            status=result.status,
            finished=datetime.now().isoformat(timespec="seconds"),
            plan=result.plan,
            issues=list(result.issues),
            work_dir=result.work_dir,
            encoded_audio=dict(result.encoded_audio),
        )
        self.root.mkdir(parents=True, exist_ok=True)
        doc = {"version": FORMAT_VERSION, "record": to_json(rec)}
        path = self._path(result.output)
        tmp = path.with_suffix(".json.partial")
        tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
        return rec

    def find(self, output: Path) -> JobRecord | None:
        """The record for an output path, or None (never recorded, unreadable, or another version)."""
        try:
            doc = json.loads(self._path(output).read_text(encoding="utf-8"))
            if doc.get("version") != FORMAT_VERSION:
                return None
            return from_json(JobRecord, doc["record"])
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return None
