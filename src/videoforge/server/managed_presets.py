"""Presets a plugin ships, kept exactly as the plugin ships them: the pack is the truth.

A plugin names a preset pack in its manifest (`presets = "presets/pack.json"`, the preset pack format with
a `key` on every entry). At every start, and when a profile is created, imported or reset, each profile is
brought in line with the packs of the plugins installed (and enabled). A shipped preset is *managed*: the
profile remembers its key, where it is stored and a digest of the record as shipped.

    new key                  -> added; a preset of the user's own with its name is taken over (overwritten),
                                so the plugin's never sits beside an older copy as "Name (2)"
    pack changed             -> updated in place (same storage name, so a default template stays one)
    edited by the user       -> put back as shipped
    deleted by the user      -> put back
    the user's own preset under its name (a "Name (2)" deleted as a duplicate, an import of an older pack)
                             -> taken over; a numbered copy of the plugin's beside it goes
    key gone from the pack   -> kept, marked retired; no longer kept in line

Between starts `status` says which ones differ from the pack (`stale`), and `reset` puts one back at once.
A template the user renamed is a new preset of theirs, and the managed one is put back under its name.
Encoder and audio presets are stored under a random id with a label and folder, so renaming one is an edit.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
import hashlib
import json
import logging
from pathlib import Path
import re
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


def _identical(db: sqlite3.Connection, profile: str, e: Shipped) -> str | None:
    """The stored name of a preset that already equals this shipped one, if any."""
    grouped = e.kind in GROUPED
    want = digest({**e.record, "label": e.name} if grouped else e.record)
    for name, raw in db.execute("SELECT name, data FROM presets WHERE profile = ? AND kind = ?", (profile, e.kind)):
        record = json.loads(raw)
        label = record.get("label") if grouped else name
        if not isinstance(label, str) or not re.fullmatch(re.escape(e.name) + r"( \(\d+\))?", label):
            continue
        if digest({**record, "label": e.name} if grouped else record) == want:
            return name
    return None


def _occupant(db: sqlite3.Connection, profile: str, e: Shipped) -> tuple[str, Any] | None:
    """The user's own preset where a shipped one would go, which no plugin manages: (its stored name, its record).
    A template or video preset is found by its name; an encoder or audio preset by its encoder (or action), folder
    and label."""
    managed = {
        name
        for (name,) in db.execute("SELECT name FROM managed_presets WHERE profile = ? AND kind = ?", (profile, e.kind))
    }
    if e.kind not in GROUPED:
        record = None if e.name in managed else _stored(db, profile, e.kind, e.name)
        return None if record is None else (e.name, record)
    parent = "encoder" if e.kind == "encoder" else "action"
    rows = db.execute("SELECT name, data FROM presets WHERE profile = ? AND kind = ? ORDER BY name", (profile, e.kind))
    for name, raw in rows:
        if name in managed:
            continue
        record = json.loads(raw)
        settings = record.get("settings", record)
        if (
            record.get("label") == e.name
            and tuple(record.get("group", ())) == e.group
            and settings.get(parent) == e.data[parent]
        ):
            return name, record
    return None


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
    twin = _identical(db, profile, e)
    if twin is not None:  # already saved exactly as shipped: adopt it instead of numbering a copy
        return twin, "new"
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


def _put(db: sqlite3.Connection, profile: str, kind: str, name: str, record: Any) -> None:
    db.execute(
        "UPDATE presets SET data = ? WHERE profile = ? AND kind = ? AND name = ?",
        (json.dumps(record), profile, kind, name),
    )


def _moved(db: sqlite3.Connection, profile: str, kind: str, old: str, new: str) -> None:
    """A template now stored as `new` instead of `old`: a rule set's default that named it follows it."""
    if kind != "template" or old == new:
        return
    row = db.execute(
        "SELECT value FROM settings WHERE profile = ? AND key = 'template_defaults'", (profile,)
    ).fetchone()
    defaults = json.loads(row[0]) if row else None
    if isinstance(defaults, dict) and old in defaults.values():
        defaults = {rule_set: new if name == old else name for rule_set, name in defaults.items()}
        db.execute(
            "UPDATE settings SET value = ? WHERE profile = ? AND key = 'template_defaults'",
            (json.dumps(defaults), profile),
        )


def _enforce(
    db: sqlite3.Connection, profile: str, e: Shipped, name: str | None, reserved: tuple[str, ...]
) -> tuple[str, str | None]:
    """Make the profile hold exactly what the plugin ships for `e`, managed under `name` (None: not yet).
    (Where it is stored now, what was done: 'new', 'took over', 'restored', 'updated', or None.)"""
    current = None if name is None else _stored(db, profile, e.kind, name)
    reserved_name = e.kind not in GROUPED and e.name in reserved
    occupant = None if reserved_name else _occupant(db, profile, e)
    if occupant is not None:  # the user's own preset where this one belongs: it becomes the plugin's
        target, record = occupant
        if name is not None and current is not None and name != target:  # the plugin's numbered copy beside it goes
            db.execute("DELETE FROM presets WHERE profile = ? AND kind = ? AND name = ?", (profile, e.kind, name))
            _moved(db, profile, e.kind, name, target)
        if digest(record) != e.digest:
            _put(db, profile, e.kind, target, e.record)
        return target, "took over"
    if name is None or current is None:
        target, _ = _add(db, profile, e, reserved)
        if name is not None:
            _moved(db, profile, e.kind, name, target)
        return target, "new" if name is None else "restored"
    if e.kind not in GROUPED and name != e.name and not reserved_name and _stored(db, profile, e.kind, e.name) is None:
        # a numbered template or video preset whose own name is free again: back under it
        db.execute("DELETE FROM presets WHERE profile = ? AND kind = ? AND name = ?", (profile, e.kind, name))
        db.execute(
            "INSERT INTO presets (profile, kind, name, data) VALUES (?, ?, ?, ?)",
            (profile, e.kind, e.name, json.dumps(e.record)),
        )
        _moved(db, profile, e.kind, name, e.name)
        return e.name, "updated"
    if digest(current) != e.digest:
        _put(db, profile, e.kind, name, e.record)
        return name, "updated"
    return name, None


def sync(
    db: sqlite3.Connection, profile: str, packs: list[Pack], reserved: dict[str, tuple[str, ...]]
) -> list[dict[str, str]]:
    """Bring one profile in line with the packs; what happened to each preset that changed."""
    report: list[dict[str, str]] = []

    db.execute("BEGIN")
    try:
        for pack in packs:
            known = {
                (kind, key): name
                for kind, key, name in db.execute(
                    "SELECT kind, key, name FROM managed_presets WHERE profile = ? AND plugin = ?",
                    (profile, pack.plugin),
                )
            }
            for e in pack.entries:
                had = (e.kind, e.key) in known
                name = known.pop((e.kind, e.key), None)
                stored, action = _enforce(db, profile, e, name, reserved.get(e.kind, ()))
                if had:
                    db.execute(
                        "UPDATE managed_presets SET name = ?, shipped = ?, available = NULL, retired = 0"
                        " WHERE profile = ? AND plugin = ? AND kind = ? AND key = ?",
                        (stored, e.digest, profile, pack.plugin, e.kind, e.key),
                    )
                else:
                    db.execute(
                        "INSERT INTO managed_presets (profile, plugin, kind, key, name, shipped) VALUES (?, ?, ?, ?, ?, ?)",
                        (profile, pack.plugin, e.kind, e.key, stored, e.digest),
                    )
                if action is not None:
                    report.append(
                        {"plugin": pack.plugin, "kind": e.kind, "key": e.key, "name": stored, "action": action}
                    )
            for (kind, key), name in known.items():  # shipped before, not in this pack
                db.execute(
                    "UPDATE managed_presets SET retired = 1, available = NULL"
                    " WHERE profile = ? AND plugin = ? AND kind = ? AND key = ? AND retired = 0",
                    (profile, pack.plugin, kind, key),
                )
                if db.execute("SELECT changes()").fetchone()[0]:
                    report.append({"plugin": pack.plugin, "kind": kind, "key": key, "name": name, "action": "retired"})
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise
    return report


def forget_missing(db: sqlite3.Connection, profile: str) -> None:
    """Stop tracking managed presets whose stored preset is gone because the library was replaced or reset
    (not deleted one by one): the next sync ships them again instead of reading the gap as a user's delete."""
    for kind, name in db.execute("SELECT kind, name FROM managed_presets WHERE profile = ?", (profile,)).fetchall():
        if _stored(db, profile, kind, name) is None:
            db.execute("DELETE FROM managed_presets WHERE profile = ? AND kind = ? AND name = ?", (profile, kind, name))


def status(db: sqlite3.Connection, profile: str, packs: Sequence[Pack] = ()) -> list[dict[str, Any]]:
    """Every managed preset of a profile: where it stands against what its plugin ships. A deleted one whose
    place the user's own preset took (found through `packs`) is `replaced`, `replaced_by` naming that preset.
    Sync puts every one back, so anything but `current` is a change since the last start."""
    shipping = {(e.plugin, e.kind, e.key): e for p in packs for e in p.entries}
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
        replaced_by = None
        e = shipping.get((plugin, kind, key))
        if current is None and not retired and e is not None:
            label, group = e.name, list(e.group)
            occupant = _occupant(db, profile, e)
            if occupant is not None:
                state, replaced_by = "replaced", occupant[0] if kind not in GROUPED else occupant[1]["label"]
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
                "replaced_by": replaced_by,  # state "replaced": the user's preset in its place
                # the version the plugin ships now (its digest), and whether the preset in use isn't it
                "shipping": e.digest if e is not None else None,
                # the next start (or `reset`) puts it back: edited, deleted or replaced since the last one
                "stale": state != "current" and not retired,
            }
        )
    return out


def reset(db: sqlite3.Connection, profile: str, e: Shipped, reserved: tuple[str, ...]) -> str:
    """Put a managed preset back as its plugin ships it now, as the next start would; its name."""
    row = db.execute(
        "SELECT name FROM managed_presets WHERE profile = ? AND plugin = ? AND kind = ? AND key = ?",
        (profile, e.plugin, e.kind, e.key),
    ).fetchone()
    if row is None:
        raise KeyError(e.key)
    db.execute("BEGIN")
    try:
        name, _ = _enforce(db, profile, e, row[0], reserved)
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
