"""Server settings: where it listens, where it keeps its data, what the folder browser may show."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import os
from pathlib import Path
import string

from videoforge.core.actions import Action, load_actions
from videoforge.core.config import PROJECT_ROOT, AppConfig, with_tools
from videoforge.core.history import app_data_dir
from videoforge.core.notify import Destination, load_destinations

MAX_PARALLEL_AUDIO = 8  # the Settings page's limit on audio encodes at once


def default_roots() -> list[Path]:
    """Every drive on Windows (incl. mapped network drives), / elsewhere."""
    if os.name == "nt":
        return [Path(f"{d}:\\") for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
    return [Path("/")]


@dataclass(slots=True)
class ServerSettings:
    host: str = "127.0.0.1"  # one user, this machine: no auth, so don't listen beyond it by default
    port: int = 8765
    data_dir: Path = field(default_factory=app_data_dir)  # videoforge.db, job history
    roots: list[Path] = field(default_factory=default_roots)  # what the folder browser offers
    frontend_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "frontend" / "dist")
    probe_workers: int = 2  # concurrent probes (sources are often on a network share)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "videoforge.db"

    @property
    def plugins_dir(self) -> Path:
        """A folder per plugin (plugins/loader.py)."""
        return self.data_dir / "plugins"

    @property
    def plugin_data_dir(self) -> Path:
        """A folder per plugin for its own files (PluginContext.data_dir)."""
        return self.data_dir / "plugin-data"


@dataclass(slots=True)
class SavedSettings:
    """What the Settings page changed, kept in the store and layered over videoforge.toml at startup.
    Anything left out (an empty value) falls back to the toml / the defaults."""

    tools: dict[str, str] = field(default_factory=dict)  # Tools field -> path
    roots: list[str] | None = None  # folder-browser roots; None = every drive
    profile: str | None = None  # default profile for new jobs
    index_waits_for_disk: bool = True  # batch indexing holds a job back while an encode reads its disk
    notifications: list[Destination] = field(default_factory=list)  # where job and queue news goes
    actions: list[Action] = field(default_factory=list)  # what runs after a job ends or the queue finishes
    disabled_plugins: list[str] = field(default_factory=list)  # plugin ids not loaded on the next start
    parallel_audio: int | None = None  # audio encodes alongside the video; None = videoforge.toml's

    @classmethod
    def load(cls, store) -> SavedSettings:
        tools = store.get_setting("tools") or {}
        return cls(
            {k: v for k, v in tools.items() if isinstance(v, str) and v},
            store.get_setting("roots"),
            store.get_setting("profile"),
            bool(store.get_setting("index_waits_for_disk", True)),
            load_destinations(store.get_setting("notifications") or []),
            load_actions(store.get_setting("actions") or []),
            [str(i) for i in store.get_setting("disabled_plugins") or []],
            store.get_setting("parallel_audio"),
        )

    def save(self, store) -> None:
        store.set_setting("tools", self.tools)
        store.set_setting("roots", self.roots)
        store.set_setting("profile", self.profile)
        store.set_setting("index_waits_for_disk", self.index_waits_for_disk)
        store.set_setting("notifications", [d.to_json() for d in self.notifications])
        store.set_setting("actions", [a.to_json() for a in self.actions])
        store.set_setting("disabled_plugins", self.disabled_plugins)
        store.set_setting("parallel_audio", self.parallel_audio)

    def app_config(self, base: AppConfig, profile: str) -> AppConfig:
        """base (videoforge.toml) with these settings over it."""
        cfg = replace(with_tools(base, self.tools), profile=profile)
        return cfg if self.parallel_audio is None else replace(cfg, parallel_audio=self.parallel_audio)
