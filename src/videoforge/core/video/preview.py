"""The preview's VapourSynth in a child process, so a plugin crash or a runaway script can't take
VideoForge (and a running encode) down with it.

One long-lived worker (`python -m videoforge.core.video.preview`) keeps the clip cache, so seeking
stays quick. Requests and replies are length-prefixed JSON on its stdin/stdout (a frame's image
follows its reply); each request has an id and runs on its own thread there, so a source being
indexed doesn't hold up another job's frames. When the worker dies the waiting requests fail and
the next one starts a new worker. A request that runs far too long (a loop in a script) kills it.
The worker is in the tool Job Object: it ends with VideoForge however VideoForge ends.
"""

from __future__ import annotations

import json
import logging
import os
import struct
import subprocess
import sys
import threading
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import asdict
from typing import IO, Any, Literal

from videoforge.core.execute import jobobject
from videoforge.core.video.settings import Crop
from videoforge.core.video.vs import ClipInfo, ScriptError

log = logging.getLogger(__name__)

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_HEADER = struct.Struct(">II")  # reply/request JSON length, payload length

# A script the worker has loaded lately answers quickly; a new one may index its source first (minutes).
FRAME_TIMEOUT = 120.0
LOAD_TIMEOUT = 3600.0


class PreviewError(RuntimeError):
    """The preview worker stopped, or a request ran too long (the worker was restarted)."""


class FrameError(RuntimeError):
    """The script loads, but a filter fails on this frame."""


def _send(out: IO[bytes], header: dict[str, Any], payload: bytes = b"") -> None:
    data = json.dumps(header).encode()
    out.write(_HEADER.pack(len(data), len(payload)) + data + payload)
    out.flush()


def _read(stream: IO[bytes], n: int) -> bytes | None:
    buf = b""
    while len(buf) < n:
        chunk = stream.read(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf


def _recv(stream: IO[bytes]) -> tuple[dict[str, Any], bytes] | None:
    head = _read(stream, _HEADER.size)
    if head is None:
        return None
    size, payload = _HEADER.unpack(head)
    data = _read(stream, size)
    body = _read(stream, payload) if payload else b""
    if data is None or body is None:
        return None
    return json.loads(data), body


# --- the worker (child process) ---


def _handle(cache: Any, req: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
    from videoforge.core.video import crop as autocrop
    from videoforge.core.video import vs as vsx

    op = req["op"]
    try:
        clip = cache.get(req["script"])
    except vsx.ScriptError as e:
        return {"error": "script", "message": e.message, "line": e.line}, b""
    n = int(req.get("n", 0))
    try:
        if op == "info":
            return {"info": asdict(vsx.clip_info(clip))}, b""
        if op == "check":
            clip.get_frame(0)
            return {"info": asdict(vsx.clip_info(clip))}, b""
        if op == "frame":
            image = vsx.frame_image(clip, n, req.get("fmt", "jpeg"), int(req.get("quality", 90)))
            pict = vsx.frame_props(clip, n).get("_PictType", "")
            return {"pict": str(pict), "frames": clip.num_frames}, image
        if op == "autocrop":
            return {"crop": asdict(autocrop.detect(clip, samples=int(req.get("samples", 20))))}, b""
    except Exception as e:  # noqa: BLE001 - a filter failing on a frame; the script itself loaded
        return {"error": "frame", "message": f"Frame {n}: {type(e).__name__}: {e}"}, b""
    return {"error": "internal", "message": f"Unknown request {op!r}"}, b""


def main() -> None:
    """The worker: requests on stdin, replies on the real stdout. Whatever a script or plugin prints
    goes to stderr instead, so it can't break the replies."""
    out = os.fdopen(os.dup(1), "wb")  # buffered: writes all of each reply, then flushes
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    if os.name == "nt":  # plugins with their own C runtime take stdout from here
        import ctypes
        import msvcrt

        ctypes.windll.kernel32.SetStdHandle(-11, msvcrt.get_osfhandle(2))  # STD_OUTPUT_HANDLE

    from videoforge.core.video import vs as vsx

    cache = vsx.ClipCache()
    lock = threading.Lock()

    def run(req: dict[str, Any]) -> None:
        try:
            reply, payload = _handle(cache, req)
        except Exception as e:  # noqa: BLE001 - reported to the server, the worker carries on
            reply, payload = {"error": "internal", "message": f"{type(e).__name__}: {e}"}, b""
        with lock:
            _send(out, {"id": req["id"], **reply}, payload)

    pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="preview")
    while (msg := _recv(sys.stdin.buffer)) is not None:
        pool.submit(run, msg[0])
    os._exit(0)  # the server closed the pipe: it's gone or restarting us; don't wait for running requests


# --- the server's side ---


class _Worker:
    def __init__(self) -> None:
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "videoforge.core.video.preview"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=_NO_WINDOW | jobobject.SUSPENDED,
        )  # fmt: skip
        jobobject.adopt(self.proc)
        self.loaded: deque[str] = deque(maxlen=6)  # scripts asked for lately (the worker's cache size)
        self._pending: dict[int, Future[tuple[dict[str, Any], bytes]]] = {}
        self._lock = threading.Lock()
        self._next = 0
        self._stderr: deque[str] = deque(maxlen=20)
        self.dead = False
        threading.Thread(target=self._read_replies, name="preview-replies", daemon=True).start()
        threading.Thread(target=self._read_stderr, name="preview-stderr", daemon=True).start()

    def call(self, req: dict[str, Any], timeout: float) -> tuple[dict[str, Any], bytes]:
        fut: Future[tuple[dict[str, Any], bytes]] = Future()
        with self._lock:
            if self.dead:
                raise PreviewError("The preview process has stopped")
            self._next += 1
            rid = self._next
            self._pending[rid] = fut
            try:
                _send(self.proc.stdin, {"id": rid, **req})  # type: ignore[arg-type]
            except OSError:
                self._pending.pop(rid, None)
                raise PreviewError("The preview process has stopped") from None
        return fut.result(timeout)

    def _read_replies(self) -> None:
        while (msg := _recv(self.proc.stdout)) is not None:  # type: ignore[arg-type]
            with self._lock:
                fut = self._pending.pop(msg[0].get("id"), None)
            if fut is not None:
                fut.set_result(msg)
        code = self.proc.wait()
        last = f": {self._stderr[-1]}" if self._stderr else ""
        self._fail(f"The preview process stopped (exit code {code}){last}")
        if code != 0 and not self.dead:
            log.error("The preview process stopped (exit code %d). Its last output:\n%s", code, "\n".join(self._stderr))

    def _read_stderr(self) -> None:
        for raw in self.proc.stderr:  # type: ignore[union-attr]
            line = raw.decode("utf-8", "replace").rstrip()
            if line:
                self._stderr.append(line)
                log.info("preview: %s", line)

    def _fail(self, message: str) -> None:
        with self._lock:
            pending, self._pending = self._pending, {}
        for fut in pending.values():
            fut.set_exception(PreviewError(message))

    def stop(self, reason: str) -> None:
        self.dead = True
        self._fail(reason)
        if self.proc.poll() is None:
            self.proc.kill()


class Preview:
    """The server's handle on the worker: started on the first request, restarted after it dies."""

    def __init__(self, frame_timeout: float = FRAME_TIMEOUT, load_timeout: float = LOAD_TIMEOUT) -> None:
        self.frame_timeout = frame_timeout
        self.load_timeout = load_timeout
        self._worker: _Worker | None = None
        self._lock = threading.Lock()

    def _get(self) -> _Worker:
        with self._lock:
            if self._worker is None or self._worker.dead or self._worker.proc.poll() is not None:
                self._worker = _Worker()
            return self._worker

    def restart(self, reason: str = "The preview restarted") -> None:
        """Drop the worker (and its clips); the next request starts a new one, e.g. with new plugins."""
        with self._lock:
            worker, self._worker = self._worker, None
        if worker is not None:
            worker.stop(reason)

    close = restart

    def _call(self, op: str, script: str, **args: Any) -> tuple[dict[str, Any], bytes]:
        worker = self._get()
        timeout = self.frame_timeout if script in worker.loaded else self.load_timeout
        try:
            reply, payload = worker.call({"op": op, "script": script, **args}, timeout)
        except FutureTimeout:
            with self._lock:
                if self._worker is worker:
                    self._worker = None
            worker.stop(f"The preview took over {timeout:.0f} s and was restarted")
            raise PreviewError(f"The preview took over {timeout:.0f} s (a loop in the script?) and was restarted") from None
        if script not in worker.loaded:
            worker.loaded.append(script)
        error = reply.get("error")
        if error == "script":
            raise ScriptError(reply["message"], reply.get("line"))
        if error == "frame":
            raise FrameError(reply["message"])
        if error:
            raise PreviewError(reply["message"])
        return reply, payload

    def info(self, script: str) -> ClipInfo:
        return ClipInfo(**self._call("info", script)[0]["info"])

    def check(self, script: str) -> ClipInfo:
        """Run the script and render its first frame (ScriptError / FrameError when it fails)."""
        return ClipInfo(**self._call("check", script)[0]["info"])

    def frame(self, script: str, n: int, fmt: Literal["jpeg", "png"] = "jpeg", quality: int = 90) -> tuple[bytes, str, int]:
        """Frame n as an image, with its picture type and the clip's frame count."""
        reply, image = self._call("frame", script, n=n, fmt=fmt, quality=quality)
        return image, reply["pict"], reply["frames"]

    def autocrop(self, script: str, samples: int = 20) -> Crop:
        return Crop(**self._call("autocrop", script, samples=samples)[0]["crop"])


if __name__ == "__main__":
    main()
