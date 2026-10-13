"""SQLite persistence: the queue's jobs (spec + state as JSON, their order) and small settings.

The queue survives restarts: on load, a job that was running is marked
interrupted and queued again; its finished steps are kept, so it resumes.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from videoforge.core.job import JobSpec, JobState
from videoforge.core.plan_io import from_json, to_json

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    position REAL NOT NULL,
    spec TEXT NOT NULL,
    state TEXT NOT NULL,
    queued INTEGER NOT NULL DEFAULT 0,
    running INTEGER NOT NULL DEFAULT 0,
    updated TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS presets (
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (kind, name)
);
"""


@dataclass(slots=True)
class StoredJob:
    spec: JobSpec
    state: JobState
    queued: bool
    running: bool  # true only if the server stopped mid-run


class Store:
    def __init__(self, path: Path | str) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(SCHEMA)
        self._lock = threading.Lock()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # --- jobs ---------------------------------------------------------------------

    def load_jobs(self) -> list[StoredJob]:
        with self._lock:
            rows = self._db.execute("SELECT spec, state, queued, running FROM jobs ORDER BY position").fetchall()
        return [
            StoredJob(from_json(JobSpec, json.loads(spec)), from_json(JobState, json.loads(state)), bool(q), bool(r))
            for spec, state, q, r in rows
        ]

    def save_job(self, spec: JobSpec, state: JobState, *, queued: bool = False, running: bool = False) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self._lock:
            row = self._db.execute("SELECT position FROM jobs WHERE id = ?", (spec.id,)).fetchone()
            position = row[0] if row else (self._db.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM jobs")
                                           .fetchone()[0])
            self._db.execute(
                "INSERT OR REPLACE INTO jobs (id, position, spec, state, queued, running, updated)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (spec.id, position, json.dumps(to_json(spec)), json.dumps(to_json(state)), int(queued), int(running),
                 now),
            )

    def delete_job(self, job_id: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM jobs WHERE id = ?", (job_id,))

    def reorder(self, ids: list[str]) -> None:
        with self._lock:
            self._db.execute("BEGIN")
            for i, job_id in enumerate(ids):
                self._db.execute("UPDATE jobs SET position = ? WHERE id = ?", (i + 1, job_id))
            self._db.execute("COMMIT")

    # --- settings and presets -------------------------------------------------------

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self._lock:
            row = self._db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, key: str, value: Any) -> None:
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, json.dumps(value)))

    def presets(self, kind: str) -> dict[str, Any]:
        with self._lock:
            rows = self._db.execute("SELECT name, data FROM presets WHERE kind = ? ORDER BY name", (kind,)).fetchall()
        return {name: json.loads(data) for name, data in rows}

    def save_preset(self, kind: str, name: str, data: Any) -> None:
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO presets (kind, name, data) VALUES (?, ?, ?)",
                             (kind, name, json.dumps(data)))

    def delete_preset(self, kind: str, name: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM presets WHERE kind = ? AND name = ?", (kind, name))
