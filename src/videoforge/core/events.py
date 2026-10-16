"""What happens in a VideoForge run, for whatever acts on it: notifications, actions, plugins.

The queue emits an event on an EventBus; each subscriber that wants its type is called in turn, on the
emitting thread (the queue's worker or the index lane). So a subscriber that does slow work (sends a
message, moves a file, calls a server) hands it to a thread of its own and returns. A subscriber that
raises is logged and the others still run: nothing a subscriber does fails or holds up a job.

An event is a snapshot: its JobSpec is a copy, so a subscriber's thread can read it after the job is
edited or removed, and changing it changes nothing.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging
from pathlib import Path
import threading
from typing import Any

from videoforge.core.job import JobResult, JobSpec, JobStatus

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class JobStarted:
    """A run began: `output` is where it will write (None when the plan can't say)."""

    spec: JobSpec
    output: Path | None


@dataclass(frozen=True, slots=True)
class JobFinished:
    """A run ended (not one a shutdown cancelled: that job resumes on the next start).

    `record` is the job record (`<output>.videoforge.json`, docs/job-record.md) when the run wrote one.
    """

    spec: JobSpec
    result: JobResult
    seconds: float
    record: Path | None = None

    @property
    def status(self) -> JobStatus:
        return self.result.status

    @property
    def output(self) -> Path | None:
        return self.result.output


@dataclass(frozen=True, slots=True)
class QueueFinished:
    """The queue's worker stopped: the jobs it ran (in order), and how many are still queued (`left`,
    when it stopped after the current job)."""

    statuses: tuple[JobStatus, ...]
    seconds: float
    left: int = 0


@dataclass(frozen=True, slots=True)
class IndexFinished:
    """The index lane finished a job's source index: `error` is None when it worked."""

    spec: JobSpec
    error: str | None = None


Event = JobStarted | JobFinished | QueueFinished | IndexFinished
EVENT_TYPES: tuple[type, ...] = (JobStarted, JobFinished, QueueFinished, IndexFinished)
Handler = Callable[[Any], object]


class EventBus:
    """Subscribers by event type; thread-safe."""

    def __init__(self) -> None:
        self._subs: list[tuple[tuple[type, ...], Handler, str]] = []
        self._lock = threading.Lock()

    def subscribe(self, handler: Handler, *types: type, name: str = "") -> Callable[[], None]:
        """Call `handler(event)` for each event of the given types (none = every type). Returns a function
        that unsubscribes. `name` is what a failure is logged under."""
        unknown = [t for t in types if t not in EVENT_TYPES]
        if unknown:
            raise TypeError(f"Not an event type: {', '.join(map(str, unknown))}")
        entry = (types or EVENT_TYPES, handler, name or getattr(handler, "__qualname__", repr(handler)))
        with self._lock:
            self._subs.append(entry)

        def unsubscribe() -> None:
            with self._lock:
                if entry in self._subs:
                    self._subs.remove(entry)

        return unsubscribe

    def emit(self, event: Event) -> None:
        with self._lock:
            subs = [(h, n) for types, h, n in self._subs if isinstance(event, types)]
        for handler, name in subs:
            try:
                handler(event)
            except Exception:  # a subscriber's bug must not reach the queue
                logger.exception("%s failed on %s", name, type(event).__name__)
