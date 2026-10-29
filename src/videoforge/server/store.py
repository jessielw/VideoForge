"""SQLite persistence: the queue's jobs (spec + state as JSON, their order) and small settings.

The queue survives restarts: on load, a job that was running is marked
interrupted and queued again; its finished steps are kept, so it resumes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import threading
from typing import Any
from uuid import uuid4

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
            position = (
                row[0] if row else (self._db.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM jobs").fetchone()[0])
            )
            self._db.execute(
                "INSERT OR REPLACE INTO jobs (id, position, spec, state, queued, running, updated)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    spec.id,
                    position,
                    json.dumps(to_json(spec)),
                    json.dumps(to_json(state)),
                    int(queued),
                    int(running),
                    now,
                ),
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

    def set_settings(self, settings: dict[str, Any]) -> None:
        rows = [(key, json.dumps(value)) for key, value in settings.items()]
        with self._lock:
            self._db.execute("BEGIN")
            try:
                self._db.executemany("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", rows)
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise

    def configuration_snapshot(self, keys: tuple[str, ...], kinds: tuple[str, ...]) -> dict[str, Any]:
        """Read a consistent settings/library snapshot without queue data."""
        with self._lock:
            settings = dict(self._db.execute("SELECT key, value FROM settings"))
            presets = {kind: {} for kind in kinds}
            for kind, name, data in self._db.execute("SELECT kind, name, data FROM presets ORDER BY kind, name"):
                if kind in presets:
                    presets[kind][name] = json.loads(data)
            return {"settings": {k: json.loads(settings[k]) for k in keys if k in settings}, "presets": presets}

    def restore_configuration(self, settings: dict[str, Any], presets: dict[str, dict[str, Any]]) -> None:
        """Replace the represented configuration atomically; preserve jobs and queue bookkeeping."""
        setting_rows = [(key, json.dumps(value)) for key, value in settings.items()]
        preset_rows = [
            (kind, name, json.dumps(data)) for kind, entries in presets.items() for name, data in entries.items()
        ]
        with self._lock:
            self._db.execute("BEGIN")
            try:
                self._db.executemany("DELETE FROM presets WHERE kind = ?", [(kind,) for kind in presets])
                self._db.executemany("INSERT INTO presets (kind, name, data) VALUES (?, ?, ?)", preset_rows)
                self._db.executemany("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", setting_rows)
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise

    def presets(self, kind: str) -> dict[str, Any]:
        with self._lock:
            rows = self._db.execute("SELECT name, data FROM presets WHERE kind = ? ORDER BY name", (kind,)).fetchall()
        return {name: json.loads(data) for name, data in rows}

    def save_preset(self, kind: str, name: str, data: Any) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO presets (kind, name, data) VALUES (?, ?, ?)", (kind, name, json.dumps(data))
            )

    def delete_preset(self, kind: str, name: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM presets WHERE kind = ? AND name = ?", (kind, name))

    def delete_presets(self, kind: str, names: list[str]) -> None:
        """Several at once, in one transaction."""
        with self._lock:
            self._db.execute("BEGIN")
            try:
                self._db.executemany("DELETE FROM presets WHERE kind = ? AND name = ?", [(kind, n) for n in names])
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise

    def import_presets(
        self,
        kind: str,
        entries: list[dict[str, Any]],
        *,
        max_name: int,
        preview: bool = False,
        reserved: tuple[str, ...] = (),
        keep_both: bool = True,
    ) -> tuple[list[str], list[str]]:
        """One library's import_preset_pack: (the names, what happened to each)."""
        names, actions = self.import_preset_pack(
            {kind: entries}, max_name=max_name, preview=preview, reserved={kind: reserved}, keep_both=keep_both
        )
        return names[kind], actions[kind]

    def import_encoder_presets(
        self, entries: list[dict[str, Any]], *, max_name: int, preview: bool = False, keep_both: bool = True
    ) -> tuple[list[str], list[str]]:
        return self.import_presets("encoder", entries, max_name=max_name, preview=preview, keep_both=keep_both)

    def import_preset_pack(
        self,
        libraries: dict[str, list[dict[str, Any]]],
        *,
        max_name: int,
        preview: bool = False,
        reserved: dict[str, tuple[str, ...]] | None = None,
        keep_both: bool = True,
    ) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
        """Import every library atomically: (the names, by kind; what happened to each entry, by kind).

        A preset matches a saved one by name (an encoder or audio preset: by label within its encoder or
        action and folder). keep_both: a match is kept and the import gets a numbered copy ("copy"); else
        the match is replaced in place ("replaced", keeping its identity, so a default stays one) or left
        alone when it already holds the same settings ("unchanged"). A reserved name, or a second entry
        of the same name, always gets a copy. Names are allocated under the write lock as well as during
        preview: another browser may have saved a preset since the preview.
        """
        with self._lock:
            names: dict[str, list[str]] = {}
            actions: dict[str, list[str]] = {}
            rows, updates = [], []
            for kind, entries in libraries.items():
                grouped = kind in ("encoder", "audio")
                parent = "encoder" if kind == "encoder" else "action"
                records = self._db.execute("SELECT name, data FROM presets WHERE kind = ?", (kind,)).fetchall()
                saved: dict[tuple, tuple[str, Any]] = {}
                for name, raw in records:
                    record = json.loads(raw)
                    settings = record.get("settings", record)
                    scope = (
                        (settings.get(parent, "x264" if kind == "encoder" else "copy"), tuple(record.get("group", [])))
                        if grouped
                        else ()
                    )
                    saved[(*scope, record.get("label", name) if grouped else name)] = (name, record)
                used = set(saved)
                used.update((name,) for name in (reserved or {}).get(kind, ()))
                names[kind], actions[kind] = [], []
                replaced: set[tuple] = set()
                for entry in entries:
                    base, data = entry["label" if grouped else "name"], entry["data"]
                    group = entry.get("group", [])
                    scope = (data[parent], tuple(group)) if grouped else ()
                    match = saved.get((*scope, base))
                    if not keep_both and match is not None and (*scope, base) not in replaced:
                        replaced.add((*scope, base))
                        name, old = match
                        record = {**old, "label": base, "group": group, "settings": data} if grouped else data
                        same = json.dumps(record, sort_keys=True) == json.dumps(old, sort_keys=True)
                        if not same:
                            updates.append((json.dumps(record), kind, name))
                        names[kind].append(base)
                        actions[kind].append("unchanged" if same else "replaced")
                        continue
                    label, i = base, 2
                    while (*scope, label) in used:
                        suffix = f" ({i})"
                        label = base[: max_name - len(suffix)] + suffix
                        i += 1
                    used.add((*scope, label))
                    names[kind].append(label)
                    actions[kind].append("new" if label == base else "copy")
                    record = {"label": label, "group": group, "settings": data} if grouped else data
                    rows.append((kind, uuid4().hex if grouped else label, json.dumps(record)))
            if not preview:
                self._db.execute("BEGIN")
                try:
                    self._db.executemany("INSERT INTO presets (kind, name, data) VALUES (?, ?, ?)", rows)
                    self._db.executemany("UPDATE presets SET data = ? WHERE kind = ? AND name = ?", updates)
                    self._db.execute("COMMIT")
                except Exception:
                    self._db.execute("ROLLBACK")
                    raise
        return names, actions
