"""Run external tools: a single command or a two-stage pipe, with log streaming and cancel."""

from __future__ import annotations

import codecs
import os
import re
import subprocess
import threading
from collections.abc import Callable, Sequence
from typing import IO

LogFn = Callable[[str], None]

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_POLL_S = 0.2
# Exit codes that still mean success (MKVToolNix returns 1 for warnings).
_OK_CODES = {"mkvmerge": {0, 1}, "mkvpropedit": {0, 1}}
# Progress bars redraw with \r, so a "line" ends at either.
_LINE_SPLIT = re.compile(r"[\r\n]+")
_TAIL = 20


class Cancelled(Exception):
    pass


class ToolError(RuntimeError):
    pass


class CancelToken:
    """Set from another thread (e.g. the GUI) to stop the running job."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()


def tool_name(argv: Sequence[str]) -> str:
    return os.path.splitext(os.path.basename(argv[0]))[0].lower()


def _pump(stream: IO[bytes], name: str, log: LogFn, tail: list[str]) -> None:
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    pending = ""

    def emit(line: str) -> None:
        if line.strip():
            tail.append(line)
            del tail[:-_TAIL]
            log(f"[{name}] {line}")

    while chunk := stream.read1(65536):
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
        proc.kill()


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
                creationflags=_NO_WINDOW,
            )
            if i == 1:
                procs[0].stdout.close()  # the producer sees a broken pipe if the consumer dies
            procs.append(proc)
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

    for argv, proc, tail in zip(argvs, procs, tails):
        name = tool_name(argv)
        if proc.returncode not in _OK_CODES.get(name, {0}):
            detail = "\n".join(tail[-5:])
            raise ToolError(f"{name} exited with code {proc.returncode}" + (f":\n{detail}" if detail else ""))
