"""Run external tools: a single command or a two-stage pipe, with log streaming and cancel."""

from __future__ import annotations

import codecs
from collections.abc import Callable, Sequence
import io
import os
import re
import signal
import subprocess
import threading
from typing import IO, cast

from videoforge.core.execute import jobobject

LogFn = Callable[[str], None]

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_POLL_S = 0.2
# Exit codes that still mean success (MKVToolNix returns 1 for warnings).
_OK_CODES = {"mkvmerge": {0, 1}, "mkvpropedit": {0, 1}, "mkvextract": {0, 1}}
# Progress bars redraw with \r, so a "line" ends at either.
_LINE_SPLIT = re.compile(r"[\r\n]+")
# Terminal color codes (MP4Box colors its output even into a pipe on Linux).
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_TAIL = 20
# A producer's complaint that its pipe closed (vspipe's fwrite error, EPIPE/EINVAL on Windows).
_BROKEN_PIPE = re.compile(r"fwrite\(\) call failed|broken pipe|errno:? (?:22|32)\b", re.IGNORECASE)


class Cancelled(Exception):
    pass


class ToolError(RuntimeError):
    """A step failed. returncode is the failing tool's exit code, when a tool failed."""

    def __init__(self, message: str, returncode: int | None = None) -> None:
        super().__init__(message)
        self.returncode = returncode


class CancelToken:
    """Set from another thread (e.g. the GUI) to stop the running job. A token with a parent is
    cancelled with it too (a job's steps stop together when one of them fails)."""

    def __init__(self, parent: CancelToken | None = None) -> None:
        self._event = threading.Event()
        self._parent = parent

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set() or (self._parent is not None and self._parent.cancelled)


def tool_name(argv: Sequence[str]) -> str:
    if len(argv) > 2 and argv[1] == "-m":  # one of ours, run as `python -m videoforge...ffindex`
        return argv[2].rsplit(".", 1)[-1]
    return os.path.splitext(os.path.basename(argv[0]))[0].lower()


def _pump(stream: IO[bytes], name: str, log: LogFn, tail: list[str]) -> None:
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    pending = ""

    def emit(line: str) -> None:
        line = _ANSI.sub("", line)
        if line.strip():
            tail.append(line)
            del tail[:-_TAIL]
            log(f"[{name}] {line}")

    reader = cast(io.BufferedReader, stream)  # Popen's pipes are buffered readers
    while chunk := reader.read1(65536):
        *lines, pending = _LINE_SPLIT.split(pending + decoder.decode(chunk))
        for line in lines:
            emit(line)
    emit(pending + decoder.decode(b"", final=True))


def _kill_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        # DeeZy starts ffmpeg/DEE/truehdd children; kill the whole tree.
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, check=False, creationflags=_NO_WINDOW
        )
    else:
        # Each tool leads its own process group (start_new_session in run()), so this ends its children too.
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def _signed(code: int) -> int:
    """Windows reports exit codes as unsigned 32-bit: 4294967295 is -1."""
    return code - (1 << 32) if code >= 1 << 31 else code


def run(argvs: Sequence[Sequence[str]], log: LogFn, cancel: CancelToken | None = None) -> None:
    """Run one command, or pipe the first command's stdout into the second.

    Raises ToolError on a failing exit code and Cancelled when the token is set.
    """
    if not 1 <= len(argvs) <= 2:
        raise ValueError("run() takes one command or a two-stage pipe")
    procs: list[subprocess.Popen] = []
    pumps: list[threading.Thread] = []
    tails: list[list[str]] = []

    try:
        for i, argv in enumerate(argvs):
            producer = i == 0 and len(argvs) == 2
            proc = subprocess.Popen(
                list(argv),
                stdin=procs[0].stdout if i == 1 else subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE if producer else subprocess.STDOUT,
                creationflags=_NO_WINDOW | jobobject.SUSPENDED,
                start_new_session=os.name != "nt",  # POSIX: its own process group, for _kill_tree
            )
            procs.append(proc)
            jobobject.adopt(proc)  # ends with VideoForge, even on a crash
            if i == 1 and procs[0].stdout is not None:
                procs[0].stdout.close()  # the producer sees a broken pipe if the consumer dies
            tail: list[str] = []
            tails.append(tail)
            stream = proc.stderr if producer else proc.stdout
            t = threading.Thread(target=_pump, args=(stream, tool_name(argv), log, tail), daemon=True)
            t.start()
            pumps.append(t)

        while running := [p for p in procs if p.poll() is None]:
            if cancel is not None and cancel.cancelled:
                raise Cancelled()
            try:
                running[0].wait(_POLL_S)
            except subprocess.TimeoutExpired:
                pass
    finally:
        for p in reversed(procs):
            _kill_tree(p)
            p.wait()
        for t in pumps:
            t.join(timeout=5)

    failed = [
        (tool_name(argv), _signed(proc.returncode), tail)
        for argv, proc, tail in zip(argvs, procs, tails, strict=True)
        if proc.returncode not in _OK_CODES.get(tool_name(argv), {0})
    ]
    if failed:
        # A consumer that fails (e.g. x264 on a bad option) makes the producer fail writing into the
        # pipe: lead with the tool that didn't just lose its pipe.
        failed.sort(key=lambda f: bool(_BROKEN_PIPE.search("\n".join(f[2]))))
        message = "\n".join(
            f"{name} exited with code {code}" + (":\n" + "\n".join(tail[-5:]) if tail else "")
            for name, code, tail in failed
        )
        raise ToolError(message, failed[0][1])
