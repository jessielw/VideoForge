"""Server settings: where it listens, where it keeps its data, what the folder browser may show."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import ipaddress
import os
from pathlib import Path
import string

from videoforge.core.actions import Action, load_actions
from videoforge.core.config import PROJECT_ROOT, AppConfig, app_data_dir, with_tools
from videoforge.core.execute.control import Priority
from videoforge.core.notify import Destination, load_destinations
from videoforge.core.plan_io import to_json

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
    data_dir: Path = field(default_factory=app_data_dir)  # videoforge.db, logs, kept job records, plugins
    roots: list[Path] = field(default_factory=default_roots)  # what the folder browser offers
    frontend_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "frontend" / "dist")
    probe_workers: int = 2  # concurrent probes (sources are often on a network share)
    allowed_hosts: list[str] = field(default_factory=list)  # extra exact hostnames, without ports
    allowed_origins: list[str] = field(default_factory=list)  # proxy/dev origins when Host is rewritten
    plugin_management: bool | None = None  # None: enable only for a loopback binding; never part of a backup

    @property
    def can_manage_plugins(self) -> bool:
        if self.plugin_management is not None:
            return self.plugin_management
        if self.host == "localhost":
            return True
        try:
            return ipaddress.ip_address(self.host).is_loopback
        except ValueError:
            return False

    @property
    def db_path(self) -> Path:
        return self.data_dir / "videoforge.db"

    @property
    def records_dir(self) -> Path:
        """Job records and logs kept from deleted work folders (workdir.keep_records)."""
        return self.data_dir / "records"

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
    delete_work_dir: bool | None = None  # delete a done job's work folder; None = videoforge.toml's
    encoder_priority: Priority | None = None  # the video encode's process priority; None = videoforge.toml's
    tool_priority: Priority | None = None  # every other tool's; None = videoforge.toml's
    plugin_settings: dict[str, dict] = field(default_factory=dict)
    sample_quality: bool = False  # a test encode measures its quality (SSIMULACRA2, XPSNR) after it

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
            store.get_setting("delete_work_dir"),
            _priority(store.get_setting("encoder_priority")),
            _priority(store.get_setting("tool_priority")),
            store.get_setting("plugin_settings") or {},
            bool(store.get_setting("sample_quality", False)),
        )

    def save(self, store) -> None:
        store.set_settings(to_json(self))

    def app_config(self, base: AppConfig, profile: str) -> AppConfig:
        """base (videoforge.toml) with these settings over it."""
        cfg = replace(with_tools(base, self.tools), profile=profile)
        if self.parallel_audio is not None:
            cfg = replace(cfg, parallel_audio=self.parallel_audio)
        if self.delete_work_dir is not None:
            cfg = replace(cfg, delete_work_dir=self.delete_work_dir)
        if self.encoder_priority is not None:
            cfg = replace(cfg, encoder_priority=self.encoder_priority)
        if self.tool_priority is not None:
            cfg = replace(cfg, tool_priority=self.tool_priority)
        return cfg


def _priority(value: object) -> Priority | None:
    return Priority(value) if value in tuple(Priority) else None
