"""Presets a plugin ships and keeps up to date, without overwriting what a user changed.

A plugin names a preset pack in its manifest (`presets = "presets/pack.json"`, the preset pack format with
a `key` on every entry). At every start, and when a profile is created, each profile is brought in line with
the packs of the plugins installed. A shipped preset is *managed*: the profile remembers its key and a
digest of the record as shipped, which tells an untouched preset from one the user edited.

    new key                  -> added (a taken name gets a numbered copy)
    untouched, pack changed  -> updated in place (same storage name, so a default template stays one)
    edited by the user       -> left alone; `update_available` says the pack has a newer version
    deleted by the user      -> stays deleted (`reset` brings it back)
    key gone from the pack   -> kept, marked retired
    renamed by the user      -> a template or video preset is its name, so this is a delete: the managed
                                one stays gone and the renamed one is the user's own

Encoder and audio presets are stored under a random id with a label and folder, so renaming one is an edit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import logging
from pathlib import Path
import sqlite3
from typing import Any
from uuid import uuid4

from videoforge.core.template_io import MAX_NAME
from videoforge.plugins.loader import _is_below
from videoforge.plugins.manifest import MANIFEST, PluginError, read_manifest

logger = logging.getLogger(__name__)

TABLE = (
    "CREATE TABLE IF NOT EXISTS managed_presets ("
    " profile TEXT NOT NULL, plugin TEXT NOT NULL, kind TEXT NOT NULL, key TEXT NOT NULL,"
    " name TEXT NOT NULL, shipped TEXT NOT NULL, available TEXT, retired INTEGER NOT NULL DEFAULT 0,"
    " PRIMARY KEY (profile, plugin, kind, key))"
)
GROUPED = ("encoder", "audio")


@dataclass(frozen=True, slots=True)
class Shipped:
    """One preset of a plugin's pack."""

    plugin: str
    kind: str
    key: str
    name: str  # a template or video preset's name, an encoder or audio preset's label
    data: dict[str, Any]
    group: tuple[str, ...] = ()

    @property
    def record(self) -> Any:
        """What the presets table holds."""
        if self.kind in GROUPED:
            return {"label": self.name, "group": list(self.group), "settings": self.data}
        return self.data

    @property
    def digest(self) -> str:
        return digest(self.record)


@dataclass(slots=True)
class Pack:
    plugin: str
    entries: list[Shipped] = field(default_factory=list)


def digest(record: Any) -> str:
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def read_pack(plugin: str, doc: Any) -> Pack:
    """A plugin's pack, every entry keyed."""
    from videoforge.server.preset_pack import read_preset_pack  # it imports the store, which imports this

    bundle = read_preset_pack(doc, keep_keys=True)
    pack = Pack(plugin)
    for kind, entries in bundle["presets"].items():
        for entry in entries:
            if "key" not in entry:
                raise ValueError(f"{kind} preset {entry.get('name') or entry.get('label')!r} needs a key")
            name = entry["label"] if kind in GROUPED else entry["name"]
            pack.entries.append(Shipped(plugin, kind, entry["key"], name, entry["data"], tuple(entry.get("group", ()))))
    return pack


def load_packs(folder: Path | None, disabled: Any = ()) -> tuple[list[Pack], list[str]]:
    """The packs of the plugins in `folder`, and what was wrong with any that couldn't be read."""
    from videoforge.server.preset_pack import MAX_BYTES

    packs: list[Pack] = []
    problems: list[str] = []
    if folder is None or not folder.is_dir():
        return packs, problems
    for root in sorted((p for p in folder.iterdir() if p.is_dir()), key=lambda p: p.name.casefold()):
        if not (root / MANIFEST).is_file():
            continue
        try:
            manifest = read_manifest(root / MANIFEST)
            if not manifest.presets or manifest.id in disabled:
                continue
            path = root / manifest.presets
            if not _is_below(path, root) or not path.is_file():
                raise PluginError(f"{manifest.presets} is not a file in the plugin")
            if path.stat().st_size > MAX_BYTES:
                raise PluginError(f"{manifest.presets} is larger than {MAX_BYTES >> 20} MiB")
            packs.append(read_pack(manifest.id, json.loads(path.read_text(encoding="utf-8"))))
        except (PluginError, ValueError, OSError, RecursionError) as ex:
            problems.append(f"{root.name}: {ex}")
            logger.warning("Plugin presets in %s not used: %s", root.name, ex)
    return packs, problems


# --- the database side: called by Store under its lock, inside its connection -----------------------


def _stored(db: sqlite3.Connection, profile: str, kind: str, name: str) -> Any | None:
    row = db.execute("SELECT data FROM presets WHERE profile = ? AND kind = ? AND name = ?", (profile, kind, name))
    row = row.fetchone()
    return json.loads(row[0]) if row else None


def _taken(db: sqlite3.Connection, profile: str, e: Shipped, reserved: tuple[str, ...]) -> set[Any]:
    """The names (a template or video preset) or (encoder or action, folder, label) already in use."""
    rows = db.execute("SELECT name, data FROM presets WHERE profile = ? AND kind = ?", (profile, e.kind)).fetchall()
    if e.kind not in GROUPED:
        return {name for name, _ in rows} | set(reserved)
    parent = "encoder" if e.kind == "encoder" else "action"
    taken = set()
    for _, raw in rows:
        record = json.loads(raw)
        settings = record.get("settings", record)
        taken.add((settings.get(parent), tuple(record.get("group", ())), record.get("label")))
    return taken


def _numbered(base: str, used: Any) -> str:
    label, i = base, 2
    while used(label):
        suffix = f" ({i})"
        label = base[: MAX_NAME - len(suffix)] + suffix
        i += 1
    return label


def _add(db: sqlite3.Connection, profile: str, e: Shipped, reserved: tuple[str, ...]) -> tuple[str, str]:
    """Store a shipped preset under a free name: (that name, 'new' or 'copy')."""
    taken = _taken(db, profile, e, reserved)
    if e.kind in GROUPED:
        parent = e.data["encoder" if e.kind == "encoder" else "action"]
        label = _numbered(e.name, lambda x: (parent, e.group, x) in taken)
        record = {**e.record, "label": label}
        name = uuid4().hex
    else:
        label = _numbered(e.name, taken.__contains__)
        record, name = e.record, label
    db.execute(
        "INSERT INTO presets (profile, kind, name, data) VALUES (?, ?, ?, ?)",
        (profile, e.kind, name, json.dumps(record)),
    )
    return name, "new" if label == e.name else "copy"


def sync(
    db: sqlite3.Connection, profile: str, packs: list[Pack], reserved: dict[str, tuple[str, ...]]
) -> list[dict[str, str]]:
    """Bring one profile in line with the packs; what happened to each preset that changed."""
    report: list[dict[str, str]] = []

    def note(e_plugin: str, kind: str, key: str, name: str, action: str) -> None:
        report.append({"plugin": e_plugin, "kind": kind, "key": key, "name": name, "action": action})

    db.execute("BEGIN")
    try:
        for pack in packs:
            known = {
                (kind, key): (name, shipped, available)
                for kind, key, name, shipped, available in db.execute(
                    "SELECT kind, key, name, shipped, available FROM managed_presets WHERE profile = ? AND plugin = ?",
                    (profile, pack.plugin),
                )
            }
            for e in pack.entries:
                row = known.pop((e.kind, e.key), None)
                if row is None:
                    name, action = _add(db, profile, e, reserved.get(e.kind, ()))
                    db.execute(
                        "INSERT INTO managed_presets (profile, plugin, kind, key, name, shipped) VALUES (?, ?, ?, ?, ?, ?)",
                        (profile, pack.plugin, e.kind, e.key, name, e.digest),
                    )
                    note(pack.plugin, e.kind, e.key, name, action)
                    continue
                name, shipped, flagged = row
                current = _stored(db, profile, e.kind, name)
                newer = e.digest != shipped
                if current is not None and digest(current) == shipped and newer:
                    db.execute(
                        "UPDATE presets SET data = ? WHERE profile = ? AND kind = ? AND name = ?",
                        (json.dumps(e.record), profile, e.kind, name),
                    )
                    db.execute(
                        "UPDATE managed_presets SET shipped = ?, available = NULL, retired = 0"
                        " WHERE profile = ? AND plugin = ? AND kind = ? AND key = ?",
                        (e.digest, profile, pack.plugin, e.kind, e.key),
                    )
                    note(pack.plugin, e.kind, e.key, name, "updated")
                    continue
                db.execute(
                    "UPDATE managed_presets SET available = ?, retired = 0"
                    " WHERE profile = ? AND plugin = ? AND kind = ? AND key = ?",
                    (e.digest if newer and current is not None else None, profile, pack.plugin, e.kind, e.key),
                )
                if current is not None and newer and flagged != e.digest:  # said once, then the flag stays
                    note(pack.plugin, e.kind, e.key, name, "kept")
            for (kind, key), (name, _, _) in known.items():  # shipped before, not in this pack
                db.execute(
                    "UPDATE managed_presets SET retired = 1, available = NULL"
                    " WHERE profile = ? AND plugin = ? AND kind = ? AND key = ?",
                    (profile, pack.plugin, kind, key),
                )
                note(pack.plugin, kind, key, name, "retired")
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise
    return report


def status(db: sqlite3.Connection, profile: str) -> list[dict[str, Any]]:
    """Every managed preset of a profile: where it stands against what its plugin shipped."""
    out = []
    rows = db.execute(
        "SELECT plugin, kind, key, name, shipped, available, retired FROM managed_presets WHERE profile = ?"
        " ORDER BY plugin, kind, key",
        (profile,),
    ).fetchall()
    for plugin, kind, key, name, shipped, available, retired in rows:
        current = _stored(db, profile, kind, name)
        state = "removed" if current is None else "current" if digest(current) == shipped else "edited"
        label = current["label"] if current is not None and kind in GROUPED else name if kind not in GROUPED else key
        group = current.get("group", []) if current is not None and kind in GROUPED else []
        out.append(
            {
                "plugin": plugin,
                "kind": kind,
                "key": key,
                "name": name,
                "label": label,  # what the user sees: a template's name, an encoder or audio preset's label
                "group": group,
                "state": state,
                "retired": bool(retired),
                "update_available": available is not None,
            }
        )
    return out


def reset(db: sqlite3.Connection, profile: str, e: Shipped, reserved: tuple[str, ...]) -> str:
    """Put a managed preset back as its plugin ships it, edited or removed; its name."""
    row = db.execute(
        "SELECT name FROM managed_presets WHERE profile = ? AND plugin = ? AND kind = ? AND key = ?",
        (profile, e.plugin, e.kind, e.key),
    ).fetchone()
    if row is None:
        raise KeyError(e.key)
    name = row[0]
    db.execute("BEGIN")
    try:
        if _stored(db, profile, e.kind, name) is None:
            name, _ = _add(db, profile, e, reserved)
        else:
            db.execute(
                "UPDATE presets SET data = ? WHERE profile = ? AND kind = ? AND name = ?",
                (json.dumps(e.record), profile, e.kind, name),
            )
        db.execute(
            "UPDATE managed_presets SET name = ?, shipped = ?, available = NULL, retired = 0"
            " WHERE profile = ? AND plugin = ? AND kind = ? AND key = ?",
            (name, e.digest, profile, e.plugin, e.kind, e.key),
        )
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise
    return name
