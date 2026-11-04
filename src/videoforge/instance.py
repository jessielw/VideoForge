"""One tray VideoForge per data folder, and a port for it when the default is taken.

The lock is an OS file lock on `<data dir>/videoforge.lock`: released by the OS when the process ends, even if
it crashes, so there is never a stale lock file to clean up. It closes the gap `/api/health` leaves (a second
launch while the first is still starting, before it answers). Without it, the port fallback below would let
that second launch start a second copy on the next port.
"""

from __future__ import annotations

from pathlib import Path
import socket
import sys
from typing import IO


class InstanceLock:
    """An exclusive, non-blocking lock on a file; held until `release()` or the process ends."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._file: IO[bytes] | None = None

    def acquire(self) -> bool:
        """True when this process now holds the lock, False when another one does (or the folder can't be written)."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            handle = open(self.path, "ab")
        except OSError:
            return True  # can't lock here: don't stop VideoForge from starting over it
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return False
        self._file = handle
        return True

    def release(self) -> None:
        if self._file is not None:
            self._file.close()  # closing releases the lock
            self._file = None


def find_free_port(host: str, start: int, attempts: int = 10) -> int:
    """The first port from `start` that can be bound on `host`; `start` itself when none of them can (the
    server then reports its own error)."""
    for port in range(start, start + attempts):
        with socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
            except OSError:
                continue
            return port
    return start
