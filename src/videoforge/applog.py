"""The app log: stdlib logging under "videoforge", one file per `serve` session in `<data dir>/logs/`.

Modules log through `logging.getLogger(__name__)` and never set anything up; `setup()` (called by
`serve`) adds the handlers: a file `videoforge_<YYYY-mm-dd_HH-MM-SS>.log` (the newest KEEP files are
kept, as StaxRip keeps its logs) and the console. Both sit behind a QueueHandler, so a job thread
never waits on disk. uvicorn's loggers go to the same place. Logging never stops the app: a data
folder that can't be written means no log file, and a console that can't show a character gets it
escaped.

Job output doesn't go here: each job's tool output is in its work folder (`videoforge.log`), and
what it did is in its record (core/record.py). This log has the app's own story: start, settings,
jobs started and finished, the preview worker, errors.
"""

from __future__ import annotations

import atexit
from datetime import datetime
import logging
import logging.handlers
from pathlib import Path
import platform
import queue
import sys
from typing import TextIO

KEEP = 50  # log files kept in the folder, newest first
MAX_BYTES = 10 * 1024 * 1024  # one session's file rolls over at this size (2 more parts kept)
FILE_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
CONSOLE_FORMAT = "%(asctime)s %(levelname)-7s %(message)s"
LOGGERS = ("videoforge", "uvicorn")  # uvicorn.error and .access propagate to "uvicorn" (access: below its level)

_listener: logging.handlers.QueueListener | None = None
_handler: logging.Handler | None = None


class _ConsoleHandler(logging.StreamHandler):
    """A console that can't encode a character (a Windows code page) shows it escaped instead of failing."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            stream: TextIO = self.stream
            encoding = getattr(stream, "encoding", None) or "utf-8"
            stream.write(msg.encode(encoding, "backslashreplace").decode(encoding, "replace") + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)


def version() -> str:
    try:
        from importlib.metadata import version as dist_version

        return dist_version("videoforge")
    except Exception:
        return "unknown"


def _prune(folder: Path, keep: int) -> None:
    """Delete all but the newest `keep - 1` log files (the new session's file makes `keep`)."""
    try:
        files = sorted(folder.glob("videoforge_*.log*"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return
    for old in files[max(keep - 1, 0) :]:
        try:
            old.unlink()
        except OSError:
            pass


def _file_handler(data_dir: Path, keep: int) -> tuple[logging.Handler | None, Path | None, str]:
    folder = data_dir / "logs"
    name = f"videoforge_{datetime.now():%Y-%m-%d_%H-%M-%S}.log"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        _prune(folder, keep)
        path = folder / name
        handler = logging.handlers.RotatingFileHandler(path, maxBytes=MAX_BYTES, backupCount=2, encoding="utf-8")
    except OSError as ex:
        return None, None, f"No log file ({ex})"
    handler.setFormatter(logging.Formatter(FILE_FORMAT))
    return handler, path, ""


def setup(data_dir: Path | None, *, console: bool = True, level: int = logging.INFO, keep: int = KEEP) -> Path | None:
    """Start logging (again: an earlier setup's handlers are replaced). Returns the log file, or None."""
    global _listener, _handler
    shutdown()
    handlers: list[logging.Handler] = []
    path, problem = None, ""
    if data_dir is not None:
        file_handler, path, problem = _file_handler(data_dir, keep)
        if file_handler is not None:
            handlers.append(file_handler)
    if console and sys.stderr is not None:  # pythonw has no console
        stream = _ConsoleHandler(sys.stderr)
        stream.setFormatter(logging.Formatter(CONSOLE_FORMAT, "%H:%M:%S"))
        handlers.append(stream)
    if not handlers:
        return None
    records: queue.SimpleQueue[logging.LogRecord] = queue.SimpleQueue()
    _handler = logging.handlers.QueueHandler(records)
    _listener = logging.handlers.QueueListener(records, *handlers, respect_handler_level=True)
    _listener.start()
    for name in LOGGERS:
        logger = logging.getLogger(name)
        logger.addHandler(_handler)
        if name == "videoforge":
            logger.setLevel(level)
            logger.propagate = False  # a root handler (e.g. pytest's) doesn't print it twice
    atexit.register(shutdown)
    log = logging.getLogger("videoforge")
    log.info("VideoForge v%s (Python %s, %s)", version(), platform.python_version(), platform.platform())
    if path is not None:
        log.info("Log file: %s", path)
    if problem:
        log.warning("%s; logging to the console only", problem)
    return path


def shutdown() -> None:
    """Flush and stop (at exit, or before a new setup)."""
    global _listener, _handler
    if _handler is not None:
        for name in LOGGERS:
            logging.getLogger(name).removeHandler(_handler)
        logging.getLogger("videoforge").propagate = True
    if _listener is not None:
        _listener.stop()
        for h in _listener.handlers:
            h.close()
    _listener = _handler = None
