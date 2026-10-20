"""Pause and priority for a running tool and the children it starts, as one group (process.run's tools).

Windows: the tool's own job (jobobject.ToolJob), suspended and resumed process by process. POSIX: the tool's
process group (process.run starts each in a session of its own), SIGSTOP / SIGCONT, and a nice value on the
group. Raising a nice value back (a higher priority) needs CAP_SYS_NICE; without it that's logged, once.
"""

from __future__ import annotations

from enum import StrEnum
import logging
import os
import signal
import subprocess

from videoforge.core.execute import jobobject

log = logging.getLogger(__name__)


class Priority(StrEnum):
    """A tool's process priority (StaxRip's: Windows' priority classes, a nice value elsewhere)."""

    IDLE = "idle"
    BELOW_NORMAL = "below_normal"
    NORMAL = "normal"
    ABOVE_NORMAL = "above_normal"
    HIGH = "high"


_CLASS = {
    Priority.IDLE: jobobject.IDLE,
    Priority.BELOW_NORMAL: jobobject.BELOW_NORMAL,
    Priority.NORMAL: jobobject.NORMAL,
    Priority.ABOVE_NORMAL: jobobject.ABOVE_NORMAL,
    Priority.HIGH: jobobject.HIGH,
}
_NICE = {
    Priority.IDLE: 19,
    Priority.BELOW_NORMAL: 10,
    Priority.NORMAL: 0,
    Priority.ABOVE_NORMAL: -5,
    Priority.HIGH: -10,
}

# The video encoders (video/settings.Encoder): a command with one, or with vspipe piped into a tool (ffmpeg's
# VP8 / VP9), gets the encoder priority, every other tool the tool priority.
ENCODERS = frozenset({"x264", "x265", "svtav1encapp"})

_warned = False


class ToolGroup:
    """A tool just started (with jobobject.SUSPENDED) and the children it starts. start() lets it run (it stays
    paused if suspend() came first). Calls come one at a time (CancelToken's lock)."""

    def __init__(self, proc: subprocess.Popen, priority: Priority) -> None:
        self.proc = proc
        self._job = jobobject.ToolJob(proc) if os.name == "nt" else None
        if priority is not Priority.NORMAL:
            self.set_priority(priority)

    def start(self) -> None:
        if self._job is not None:
            self._job.start()

    def suspend(self) -> None:
        if self._job is not None:
            self._job.suspend()
        else:
            self._signal(signal.SIGSTOP)

    def resume(self) -> None:
        if self._job is not None:
            self._job.resume()
        else:
            self._signal(signal.SIGCONT)

    def set_priority(self, priority: Priority) -> None:
        global _warned
        if self._job is not None:
            self._job.set_priority(_CLASS[priority])
            return
        try:
            os.setpriority(os.PRIO_PGRP, self.proc.pid, _NICE[priority])
        except ProcessLookupError:
            pass
        except PermissionError:
            if not _warned:
                _warned = True
                log.warning("Couldn't raise a tool's priority to %s (that needs CAP_SYS_NICE)", priority.value)

    def close(self) -> None:
        if self._job is not None:
            self._job.close()

    def _signal(self, sig: int) -> None:
        try:
            os.killpg(self.proc.pid, sig)
        except ProcessLookupError:
            pass
