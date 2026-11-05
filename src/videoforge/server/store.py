"""SQLite persistence: the queue's jobs (spec + state as JSON, their order), and each profile's settings
and preset libraries.

The queue survives restarts: on load, a job that was running is marked
interrupted and queued again; its finished steps are kept, so it resumes.

A profile is a whole configuration (what Settings, Templates and the preset libraries hold): the store
reads and writes the active one's. The queue is shared by every profile; a new profile starts as a fresh
install does.
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
from videoforge.server import managed_presets

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
CREATE TABLE IF NOT EXISTS profiles (id TEXT PRIMARY KEY, name TEXT NOT NULL, position REAL NOT NULL);
CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""
# A profile's configuration. Separate statements: they're also made inside the migration's transaction.
PROFILE_TABLES = (
    "CREATE TABLE IF NOT EXISTS settings ("
    " profile TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, PRIMARY KEY (profile, key))",
    "CREATE TABLE IF NOT EXISTS presets ("
    " profile TEXT NOT NULL, kind TEXT NOT NULL, name TEXT NOT NULL, data TEXT NOT NULL,"
    " PRIMARY KEY (profile, kind, name))",
    managed_presets.TABLE,
)
ACTIVE = "profile"  # app_settings: the active profile's id
GLOBAL_KEYS = ("index_lane",)  # settings the queue keeps for every profile (queue.LANE_SETTING)
FIRST_PROFILE = "Default"
MAX_PROFILE_NAME = 80


class ProfileInUse(Exception):
    """A profile that can't go: the active one, or the last."""


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
        self._migrate()
        # Saved before 0.1.0-beta.11, when the default rule set was the default profile
        self._db.execute("UPDATE OR IGNORE settings SET key = 'rule_set' WHERE key = 'profile'")
        ids = [i for (i,) in self._db.execute("SELECT id FROM profiles ORDER BY position")]
        if not ids:
            ids = [uuid4().hex]
            self._db.execute("INSERT INTO profiles (id, name, position) VALUES (?, ?, 1)", (ids[0], FIRST_PROFILE))
        row = self._db.execute("SELECT value FROM app_settings WHERE key = ?", (ACTIVE,)).fetchone()
        self._profile = json.loads(row[0]) if row and json.loads(row[0]) in ids else ids[0]
        self._lock = threading.Lock()
        self._packs: list[managed_presets.Pack] = []
        self._reserved: dict[str, tuple[str, ...]] = {}

    def _migrate(self) -> None:
        """Settings and presets saved before profiles (0.1.0-beta.11) become the first profile's."""
        columns = [row[1] for row in self._db.execute("PRAGMA table_info(settings)")]
        if not columns or "profile" in columns:
            for sql in PROFILE_TABLES:
                self._db.execute(sql)
            return
        pid = uuid4().hex
        self._db.execute("BEGIN")
        try:
            self._db.execute("ALTER TABLE settings RENAME TO settings_v1")
            self._db.execute("ALTER TABLE presets RENAME TO presets_v1")
            for sql in PROFILE_TABLES:
                self._db.execute(sql)
            self._db.execute("INSERT INTO profiles (id, name, position) VALUES (?, ?, 1)", (pid, FIRST_PROFILE))
            self._db.execute("INSERT INTO settings SELECT ?, key, value FROM settings_v1", (pid,))
            for key in GLOBAL_KEYS:
                self._db.execute("INSERT INTO app_settings SELECT key, value FROM settings_v1 WHERE key = ?", (key,))
                self._db.execute("DELETE FROM settings WHERE profile = ? AND key = ?", (pid, key))
            self._db.execute("INSERT INTO presets SELECT ?, kind, name, data FROM presets_v1", (pid,))
            self._db.execute("DROP TABLE settings_v1")
            self._db.execute("DROP TABLE presets_v1")
            self._db.execute("INSERT INTO app_settings (key, value) VALUES (?, ?)", (ACTIVE, json.dumps(pid)))
            self._db.execute("COMMIT")
        except Exception:
            self._db.execute("ROLLBACK")
            raise

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # --- profiles -------------------------------------------------------------------

    @property
    def profile(self) -> str:
        """The active profile's id: settings and presets are read and written in it."""
        return self._profile

    def profiles(self) -> list[dict[str, str]]:
        with self._lock:
            rows = self._db.execute("SELECT id, name FROM profiles ORDER BY position").fetchall()
        return [{"id": pid, "name": name} for pid, name in rows]

    def _profile_name(self, name: str, pid: str | None = None) -> str:
        name = name.strip() if isinstance(name, str) else ""
        if not 1 <= len(name) <= MAX_PROFILE_NAME:
            raise ValueError(f"A profile name is 1 to {MAX_PROFILE_NAME} characters")
        taken = self._db.execute(
            "SELECT 1 FROM profiles WHERE lower(name) = lower(?) AND id != ?", (name, pid or "")
        ).fetchone()
        if taken:
            raise ValueError(f"There's already a profile named {name!r}")
        return name

    def _known(self, pid: str) -> None:
        if not self._db.execute("SELECT 1 FROM profiles WHERE id = ?", (pid,)).fetchone():
            raise KeyError(pid)

    def create_profile(self, name: str, copy_of: str | None = None) -> str:
        """A new profile, empty (a fresh install's configuration) or with a copy of another's; its id."""
        pid = uuid4().hex
        with self._lock:
            name = self._profile_name(name)
            if copy_of is not None:
                self._known(copy_of)
            self._db.execute("BEGIN")
            try:
                self._db.execute(
                    "INSERT INTO profiles (id, name, position)"
                    " VALUES (?, ?, (SELECT COALESCE(MAX(position), 0) + 1 FROM profiles))",
                    (pid, name),
                )
                if copy_of is not None:
                    self._db.execute(
                        "INSERT INTO settings SELECT ?, key, value FROM settings WHERE profile = ?", (pid, copy_of)
                    )
                    self._db.execute(
                        "INSERT INTO presets SELECT ?, kind, name, data FROM presets WHERE profile = ?", (pid, copy_of)
                    )
                    self._db.execute(
                        "INSERT INTO managed_presets SELECT ?, plugin, kind, key, name, shipped, available, retired"
                        " FROM managed_presets WHERE profile = ?",
                        (pid, copy_of),
                    )
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise
            if copy_of is None:
                managed_presets.sync(self._db, pid, self._packs, self._reserved)  # a fresh install has the plugins' too
        return pid

    def rename_profile(self, pid: str, name: str) -> None:
        with self._lock:
            self._known(pid)
            self._db.execute("UPDATE profiles SET name = ? WHERE id = ?", (self._profile_name(name, pid), pid))

    def delete_profile(self, pid: str) -> None:
        """Remove a profile and its whole configuration; not the active one, nor the last."""
        with self._lock:
            self._known(pid)
            if self._db.execute("SELECT COUNT(*) FROM profiles").fetchone()[0] == 1:
                raise ProfileInUse("The last profile can't be deleted")
            if pid == self._profile:
                raise ProfileInUse("Switch to another profile before deleting this one")
            self._db.execute("BEGIN")
            try:
                self._db.execute("DELETE FROM settings WHERE profile = ?", (pid,))
                self._db.execute("DELETE FROM presets WHERE profile = ?", (pid,))
                self._db.execute("DELETE FROM managed_presets WHERE profile = ?", (pid,))
                self._db.execute("DELETE FROM profiles WHERE id = ?", (pid,))
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise

    def switch_profile(self, pid: str) -> None:
        """Make another profile the active one (the caller applies its settings)."""
        with self._lock:
            self._known(pid)
            self._db.execute(
                "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", (ACTIVE, json.dumps(pid))
            )
            self._profile = pid

    def get_global(self, key: str, default: Any = None) -> Any:
        """A setting every profile shares (GLOBAL_KEYS: the queue's)."""
        with self._lock:
            row = self._db.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_global(self, key: str, value: Any) -> None:
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", (key, json.dumps(value)))

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
            row = self._db.execute(
                "SELECT value FROM settings WHERE profile = ? AND key = ?", (self._profile, key)
            ).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, key: str, value: Any) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO settings (profile, key, value) VALUES (?, ?, ?)",
                (self._profile, key, json.dumps(value)),
            )

    def set_settings(self, settings: dict[str, Any]) -> None:
        with self._lock:
            rows = [(self._profile, key, json.dumps(value)) for key, value in settings.items()]
            self._db.execute("BEGIN")
            try:
                self._db.executemany("INSERT OR REPLACE INTO settings (profile, key, value) VALUES (?, ?, ?)", rows)
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise

    def configuration_snapshot(self, keys: tuple[str, ...], kinds: tuple[str, ...]) -> dict[str, Any]:
        """Read a consistent settings/library snapshot of the active profile, without queue data."""
        with self._lock:
            settings = dict(self._db.execute("SELECT key, value FROM settings WHERE profile = ?", (self._profile,)))
            presets = {kind: {} for kind in kinds}
            rows = self._db.execute(
                "SELECT kind, name, data FROM presets WHERE profile = ? ORDER BY kind, name", (self._profile,)
            )
            for kind, name, data in rows:
                if kind in presets:
                    presets[kind][name] = json.loads(data)
            return {"settings": {k: json.loads(settings[k]) for k in keys if k in settings}, "presets": presets}

    def restore_configuration(
        self, settings: dict[str, Any], presets: dict[str, dict[str, Any]], profile: str | None = None
    ) -> None:
        """Replace a profile's (default: the active one's) represented configuration atomically; preserve jobs
        and queue bookkeeping."""
        with self._lock:
            p = self._profile if profile is None else profile
            self._known(p)
            setting_rows = [(p, key, json.dumps(value)) for key, value in settings.items()]
            preset_rows = [
                (p, kind, name, json.dumps(data)) for kind, entries in presets.items() for name, data in entries.items()
            ]
            self._db.execute("BEGIN")
            try:
                self._db.executemany(
                    "DELETE FROM presets WHERE profile = ? AND kind = ?", [(p, kind) for kind in presets]
                )
                self._db.executemany("INSERT INTO presets (profile, kind, name, data) VALUES (?, ?, ?, ?)", preset_rows)
                self._db.executemany(
                    "INSERT OR REPLACE INTO settings (profile, key, value) VALUES (?, ?, ?)", setting_rows
                )
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise

    # --- presets a plugin ships (server/managed_presets.py) ------------------------------------

    def use_packs(self, packs: list[managed_presets.Pack], reserved: dict[str, tuple[str, ...]]) -> list[dict]:
        """Keep every profile's presets in line with the installed plugins' packs; what changed."""
        with self._lock:
            self._packs, self._reserved = packs, reserved
            ids = [i for (i,) in self._db.execute("SELECT id FROM profiles ORDER BY position")]
            return [
                {"profile": pid, **change}
                for pid in ids
                for change in managed_presets.sync(self._db, pid, packs, reserved)
            ]

    def managed_presets(self) -> list[dict]:
        """The active profile's managed presets and where each stands."""
        with self._lock:
            return managed_presets.status(self._db, self._profile)

    def reset_managed(self, plugin: str, kind: str, key: str) -> str:
        """Put one managed preset back as its plugin ships it; its name. KeyError: no such preset."""
        with self._lock:
            for pack in self._packs:
                for e in pack.entries:
                    if (e.plugin, e.kind, e.key) == (plugin, kind, key):
                        return managed_presets.reset(self._db, self._profile, e, self._reserved.get(kind, ()))
        raise KeyError(key)

    def preset_counts(self) -> dict[str, dict[str, int]]:
        """How many presets of each kind every profile has (a kind it has none of is left out)."""
        with self._lock:
            rows = self._db.execute("SELECT profile, kind, COUNT(*) FROM presets GROUP BY profile, kind").fetchall()
        counts: dict[str, dict[str, int]] = {}
        for pid, kind, n in rows:
            counts.setdefault(pid, {})[kind] = n
        return counts

    def reset_configuration(self, keys: tuple[str, ...], kinds: tuple[str, ...]) -> None:
        """Delete the active profile's settings and whole preset libraries atomically; jobs and other settings stay."""
        with self._lock:
            p = self._profile
            self._db.execute("BEGIN")
            try:
                self._db.executemany("DELETE FROM settings WHERE profile = ? AND key = ?", [(p, key) for key in keys])
                self._db.executemany(
                    "DELETE FROM presets WHERE profile = ? AND kind = ?", [(p, kind) for kind in kinds]
                )
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise

    def presets(self, kind: str) -> dict[str, Any]:
        with self._lock:
            rows = self._db.execute(
                "SELECT name, data FROM presets WHERE profile = ? AND kind = ? ORDER BY name", (self._profile, kind)
            ).fetchall()
        return {name: json.loads(data) for name, data in rows}

    def save_preset(self, kind: str, name: str, data: Any) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO presets (profile, kind, name, data) VALUES (?, ?, ?, ?)",
                (self._profile, kind, name, json.dumps(data)),
            )

    def delete_preset(self, kind: str, name: str) -> None:
        with self._lock:
            self._db.execute(
                "DELETE FROM presets WHERE profile = ? AND kind = ? AND name = ?", (self._profile, kind, name)
            )

    def delete_presets(self, kind: str, names: list[str]) -> None:
        """Several at once, in one transaction."""
        with self._lock:
            self._db.execute("BEGIN")
            try:
                self._db.executemany(
                    "DELETE FROM presets WHERE profile = ? AND kind = ? AND name = ?",
                    [(self._profile, kind, n) for n in names],
                )
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
                records = self._db.execute(
                    "SELECT name, data FROM presets WHERE profile = ? AND kind = ?", (self._profile, kind)
                ).fetchall()
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
                            updates.append((json.dumps(record), self._profile, kind, name))
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
                    rows.append((self._profile, kind, uuid4().hex if grouped else label, json.dumps(record)))
            if not preview:
                self._db.execute("BEGIN")
                try:
                    self._db.executemany("INSERT INTO presets (profile, kind, name, data) VALUES (?, ?, ?, ?)", rows)
                    self._db.executemany(
                        "UPDATE presets SET data = ? WHERE profile = ? AND kind = ? AND name = ?", updates
                    )
                    self._db.execute("COMMIT")
                except Exception:
                    self._db.execute("ROLLBACK")
                    raise
        return names, actions
