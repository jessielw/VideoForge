"""The app log: one file per session, the newest kept, never fatal."""

import io
import logging
import os
from pathlib import Path

import pytest

from videoforge import applog


@pytest.fixture(autouse=True)
def _stop_logging():
    yield
    applog.shutdown()


def _read(path: Path) -> str:
    applog.shutdown()  # flushes the listener and closes the file
    return path.read_text(encoding="utf-8")


def test_a_session_file_starts_with_the_version(tmp_path: Path):
    path = applog.setup(tmp_path, console=False)
    assert path is not None and path.parent == tmp_path / "logs"
    assert path.name.startswith("videoforge_") and path.suffix == ".log"
    logging.getLogger("videoforge.server.queue").info("Job %s started", "E01.mkv")
    logging.getLogger("uvicorn.error").warning("from uvicorn")
    logging.getLogger("videoforge.x").debug("below the level")
    lines = _read(path).splitlines()
    assert f"VideoForge v{applog.version()}" in lines[0]
    assert any("INFO    videoforge.server.queue: Job E01.mkv started" in line for line in lines)
    assert any("WARNING uvicorn.error: from uvicorn" in line for line in lines)
    assert not any("below the level" in line for line in lines)


def test_the_newest_files_are_kept(tmp_path: Path):
    folder = tmp_path / "logs"
    folder.mkdir()
    for n in range(60):
        f = folder / f"videoforge_2026-01-01_00-00-{n:02d}.log"
        f.write_text("old", encoding="utf-8")
        os.utime(f, (1_000_000 + n, 1_000_000 + n))
    other = folder / "notes.txt"
    other.write_text("mine", encoding="utf-8")
    path = applog.setup(tmp_path, console=False, keep=50)
    assert path is not None
    logs = sorted(folder.glob("videoforge_*.log*"))
    assert len(logs) == 50 and path in logs
    assert not (folder / "videoforge_2026-01-01_00-00-10.log").exists()  # the oldest went
    assert (folder / "videoforge_2026-01-01_00-00-59.log").exists()
    assert other.exists()


def test_an_unwritable_data_folder_means_no_file(tmp_path: Path):
    blocker = tmp_path / "data"
    blocker.write_text("a file where the folder should be", encoding="utf-8")
    assert applog.setup(blocker, console=False) is None
    logging.getLogger("videoforge").error("still fine")  # no handler, no error
    assert applog.setup(blocker, console=True) is None  # console only
    logging.getLogger("videoforge").warning("to the console")


def test_setting_up_again_replaces_the_handlers(tmp_path: Path):
    applog.setup(tmp_path, console=False)
    path = applog.setup(tmp_path, console=False)
    assert path is not None
    logging.getLogger("videoforge").info("once")
    assert _read(path).count("once") == 1
    assert logging.getLogger("videoforge").propagate  # shutdown gives it back


def test_a_console_that_cant_encode_gets_escapes():
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252")
    handler = applog._ConsoleHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.emit(logging.LogRecord("videoforge", logging.INFO, __file__, 1, "Fallout 日本語", None, None))
    stream.flush()
    assert raw.getvalue().decode("cp1252").strip() == "Fallout \\u65e5\\u672c\\u8a9e"
