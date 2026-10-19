"""Run external tools: a single command or a two-stage pipe, with log streaming, cancel, pause and priority."""

from __future__ import annotations

import codecs
from collections.abc import Callable, Sequence
import io
import os
import re
import signal
import subprocess
import threading
import time
from typing import IO, cast

from videoforge.core.execute import control, jobobject
from videoforge.core.execute.control import Priority

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
    """A run's control, used from another thread (e.g. the GUI): cancel it, pause and resume its tools, change
    their priority. A token with a parent is cancelled with it too (a job's steps stop together when one of
    them fails); its tools are the root token's, so they pause and change priority with it.

    Tools get the encoder priority (control.ENCODERS) or the tool priority, unless set_priority() chose one
    for the rest of the run. A tool started while paused starts paused."""

    def __init__(
        self,
        parent: CancelToken | None = None,
        *,
        encoder_priority: Priority = Priority.NORMAL,
        tool_priority: Priority = Priority.NORMAL,
    ) -> None:
        self._event = threading.Event()
        self._parent = parent
        self._lock = threading.Lock()
        self._tools: dict[control.ToolGroup, bool] = {}  # the running tools: is it an encoder's
        self._priorities = (tool_priority, encoder_priority)
        self._chosen: Priority | None = None  # set_priority()'s
        self._paused_at: float | None = None
        self._paused_s = 0.0  # the pauses before this one

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set() or (self._parent is not None and self._parent.cancelled)

    @property
    def _root(self) -> CancelToken:
        return self if self._parent is None else self._parent._root

    @property
    def paused(self) -> bool:
        return self._root._paused_at is not None

    @property
    def paused_seconds(self) -> float:
        """How long the run has been paused, all told (the current pause so far too)."""
        root = self._root
        with root._lock:
            now = 0.0 if root._paused_at is None else time.monotonic() - root._paused_at
            return root._paused_s + now

    @property
    def priority(self) -> Priority | None:
        """The priority set_priority() chose (None: each tool's own, encoder or tool)."""
        return self._root._chosen

    def pause(self) -> None:
        root = self._root
        with root._lock:
            if root._paused_at is None:
                root._paused_at = time.monotonic()
                for tool in root._tools:
                    tool.suspend()

    def resume(self) -> None:
        root = self._root
        with root._lock:
            if root._paused_at is not None:
                root._paused_s += time.monotonic() - root._paused_at
                root._paused_at = None
                for tool in root._tools:
                    tool.resume()

    def set_priority(self, priority: Priority | None) -> None:
        """One priority for the run's tools, now and for the rest of the run (None: back to each one's own)."""
        root = self._root
        with root._lock:
            root._chosen = priority
            for tool, encoder in root._tools.items():
                tool.set_priority(priority or root._priorities[encoder])

    def _start(self, proc: subprocess.Popen, encoder: bool) -> control.ToolGroup:
        """A tool started with jobobject.SUSPENDED, taken on and let run (or left paused)."""
        root = self._root
        with root._lock:
            tool = control.ToolGroup(proc, root._chosen or root._priorities[encoder])
            root._tools[tool] = encoder
            if root._paused_at is not None:
                tool.suspend()
            tool.start()
            return tool

    def _end(self, tool: control.ToolGroup) -> None:
        root = self._root
        with root._lock:
            root._tools.pop(tool, None)
            tool.close()


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
    tools: list[control.ToolGroup] = []
    pumps: list[threading.Thread] = []
    tails: list[list[str]] = []
    encoder = any(tool_name(argv) in control.ENCODERS for argv in argvs)

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
            if cancel is not None:  # ends with VideoForge, even on a crash; pauses with the run
                tools.append(cancel._start(proc, encoder))
            else:
                jobobject.adopt(proc)
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
        if cancel is not None:
            for tool in tools:
                cancel._end(tool)
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
