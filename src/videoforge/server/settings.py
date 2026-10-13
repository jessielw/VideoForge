"""Server settings: where it listens, where it keeps its data, what the folder browser may show."""

from __future__ import annotations

import os
import string
from dataclasses import dataclass, field
from pathlib import Path

from videoforge.core.config import PROJECT_ROOT
from videoforge.core.history import app_data_dir


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
