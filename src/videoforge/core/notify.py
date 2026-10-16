"""Notifications: tell a chat, push or email service (anything Apprise speaks) when a job ends or the
queue runs out of jobs.

A destination is an Apprise URL (discord://..., ntfy://..., mailtos://..., tgram://...) and the events it
wants. Messages go out one at a time on a thread of their own, so a slow or unreachable service never
holds up the queue; a failed send is retried a couple of times, then logged by the destination's name
(its URL carries a token or a password, so it is never logged).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import StrEnum
import logging
import time
from typing import Any

import apprise

from videoforge.core.job import JobResult, JobSpec, JobStatus
from videoforge.core.models import Severity

logger = logging.getLogger(__name__)

_ASSET = apprise.AppriseAsset(
    app_id="VideoForge", app_desc="VideoForge", app_url="https://github.com/jessielw/VideoForge"
)
# Under the tightest transport's limit (a Discord embed holds 4096), so a message arrives in one piece.
_MAX_BODY = 3500
_MAX_ERROR = 1500
_MAX_ISSUES = 5
_ATTEMPTS = 3
_RETRY_WAIT = 2.0  # seconds before the 2nd attempt, doubled for the next


class Event(StrEnum):
    JOB_DONE = "job_done"  # muxed, and the output passes validation
    JOB_FAILED = "job_failed"  # a tool failed, the output fails validation, or the plan is blocked
    JOB_CANCELLED = "job_cancelled"
    QUEUE_FINISHED = "queue_finished"  # the queue ran out of jobs (or stopped after the current one)


EVENT_LABELS: dict[Event, str] = {
    Event.JOB_DONE: "Job done",
    Event.JOB_FAILED: "Job failed",
    Event.JOB_CANCELLED: "Job cancelled",
    Event.QUEUE_FINISHED: "Queue finished",
}
DEFAULT_EVENTS = frozenset({Event.JOB_DONE, Event.JOB_FAILED, Event.QUEUE_FINISHED})

_JOB_EVENTS: dict[JobStatus, Event] = {
    JobStatus.DONE: Event.JOB_DONE,
    JobStatus.INVALID: Event.JOB_FAILED,
    JobStatus.FAILED: Event.JOB_FAILED,
    JobStatus.SKIPPED: Event.JOB_FAILED,
    JobStatus.CANCELLED: Event.JOB_CANCELLED,
}
_JOB_TITLES: dict[JobStatus, str] = {
    JobStatus.DONE: "Done",
    JobStatus.INVALID: "Invalid output",
    JobStatus.FAILED: "Failed",
    JobStatus.SKIPPED: "Skipped",
    JobStatus.CANCELLED: "Cancelled",
}


@dataclass(frozen=True, slots=True)
class Destination:
    name: str
    url: str
    enabled: bool = True
    events: frozenset[Event] = DEFAULT_EVENTS

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> Destination:
        """One from the Settings page / the store. Raises ValueError for a URL Apprise doesn't know or an
        unknown event."""
        url = str(data.get("url") or "").strip()
        if not url:
            raise ValueError("A notification needs an Apprise URL")
        if not apprise.Apprise().add(url):
            raise ValueError(f"Apprise doesn't recognise this URL: {url.split('://', 1)[0]}://...")
        events = data.get("events")
        try:
            chosen = DEFAULT_EVENTS if events is None else frozenset(Event(e) for e in events)
        except ValueError as ex:
            raise ValueError(f"Unknown notification event: {ex}") from None
        name = str(data.get("name") or "").strip() or url.split("://", 1)[0]
        return cls(name, url, bool(data.get("enabled", True)), chosen)

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "url": self.url,
            "enabled": self.enabled,
            "events": [e.value for e in Event if e in self.events],
        }


def load_destinations(items: Iterable[Mapping[str, Any]]) -> list[Destination]:
    """The saved ones; one that no longer loads (e.g. an Apprise update dropped its service) is skipped."""
    out = []
    for item in items:
        try:
            out.append(Destination.from_json(item))
        except ValueError as ex:
            logger.warning("Skipping the notification %r: %s", item.get("name"), ex)
    return out


@dataclass(frozen=True, slots=True)
class Message:
    event: Event
    title: str
    body: str  # markdown
    kind: apprise.NotifyType = apprise.NotifyType.INFO  # the transport's colour / priority


# --- the messages ----------------------------------------------------------------------------


def job_message(spec: JobSpec, result: JobResult, seconds: float) -> Message:
    name = result.output.name if result.output else spec.name
    fields = [("Output", _code(str(result.output)) if result.output else ""), ("Took", duration(seconds))]
    if spec.label:
        fields.insert(0, ("Label", spec.label))
    blocks = [_fields(fields)]
    issues = [i for i in result.issues if i.severity is Severity.BLOCK]
    if result.status is JobStatus.INVALID and issues:
        lines = [f"- {i.message}" for i in issues[:_MAX_ISSUES]]
        if len(issues) > _MAX_ISSUES:
            lines.append(f"- and {len(issues) - _MAX_ISSUES} more")
        blocks.append("**Validation**\n" + "\n".join(lines))
    if result.error and result.status is not JobStatus.CANCELLED:
        blocks.append("**Error**\n" + _code_block(result.error))
    kind = {
        JobStatus.DONE: apprise.NotifyType.SUCCESS,
        JobStatus.CANCELLED: apprise.NotifyType.WARNING,
    }.get(result.status, apprise.NotifyType.FAILURE)
    return Message(_JOB_EVENTS[result.status], f"{_JOB_TITLES[result.status]}: {name}", _body(blocks), kind)


def queue_message(statuses: Iterable[JobStatus], seconds: float, *, left: int = 0) -> Message:
    """After the queue's worker stops: what it ran, and how many jobs are still queued (`left`, when it
    stopped after the current job)."""
    counts = Counter(statuses)
    ran = sum(counts.values())
    parts = [f"{counts[s]} {_JOB_TITLES[s].lower()}" for s in JobStatus if counts[s]]
    fields = [
        ("Jobs", f"{ran} ({', '.join(parts)})" if parts else "0"),
        ("Took", duration(seconds)),
        ("Still queued", str(left) if left else ""),
    ]
    bad = ran - counts[JobStatus.DONE]
    kind = apprise.NotifyType.SUCCESS if not bad else apprise.NotifyType.WARNING
    title = "Queue stopped" if left else "Queue finished"
    return Message(Event.QUEUE_FINISHED, title, _body([_fields(fields)]), kind)


def check_message() -> Message:
    return Message(
        Event.JOB_DONE, "VideoForge test", "Notifications from VideoForge reach this destination.",
        apprise.NotifyType.SUCCESS,
    )  # fmt: skip


def duration(seconds: float) -> str:
    s = max(0, round(seconds))
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m {s:02d}s" if m else f"{s}s"


def _code(text: str) -> str:
    """Verbatim in markdown (a file name's underscores would otherwise turn into emphasis)."""
    return "`" + text.replace("`", "'") + "`"


def _code_block(text: str) -> str:
    text = text.strip().replace("```", "'''")
    if len(text) > _MAX_ERROR:
        text = text[:_MAX_ERROR].rstrip() + "\n[truncated]"
    return f"```\n{text}\n```"


def _fields(pairs: Iterable[tuple[str, str]]) -> str:
    return "\n".join(f"- **{label}:** {value}" for label, value in pairs if value)


def _body(blocks: Iterable[str]) -> str:
    body = "\n\n".join(b for b in blocks if b)
    if len(body) <= _MAX_BODY:
        return body
    cut = body[:_MAX_BODY]
    return cut[: cut.rfind("\n")].rstrip() + "\n\n[message truncated]"


# --- sending ---------------------------------------------------------------------------------


def send(url: str, message: Message) -> str | None:
    """Send one message to one Apprise URL: None when it went, else why it didn't (Apprise's own words)."""
    ap = apprise.Apprise(asset=_ASSET)
    if not ap.add(url):
        return "Apprise doesn't recognise this URL"
    said: list[str] = []

    def heard(entry, _plugin) -> None:
        if entry.level in ("WARNING", "ERROR", "CRITICAL"):  # the level's name
            said.append(str(entry.message))

    try:
        ok = ap.notify(
            body=message.body,
            title=message.title,
            notify_type=message.kind,
            body_format=apprise.NotifyFormat.MARKDOWN,
            log_callback=heard,
        )
    except Exception as ex:  # a plugin bug must not take the sender down
        return f"{type(ex).__name__}: {ex}"
    return None if ok else ("; ".join(dict.fromkeys(said)) or "The service didn't accept the message")


Sender = Callable[[str, Message], "str | None"]


@dataclass(eq=False)
class Notifier:
    """Sends each message to the destinations that want its event, in order, on one background thread."""

    sender: Sender = send
    destinations: list[Destination] = field(default_factory=list)
    retry_wait: float = _RETRY_WAIT

    def __post_init__(self) -> None:
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="notify")

    def notify(self, message: Message) -> None:
        for d in self.destinations:
            if d.enabled and message.event in d.events:
                self._pool.submit(self._deliver, d, message)

    def test(self, url: str) -> str | None:
        """Send the test message now (no retry): None when it went, else why it didn't."""
        return self.sender(url, check_message())

    def wait(self) -> None:
        """Until every message sent so far has gone (or failed)."""
        self._pool.submit(lambda: None).result()

    def close(self) -> None:
        self._pool.shutdown(wait=False)

    def _deliver(self, d: Destination, message: Message) -> None:
        wait, error = self.retry_wait, None
        for attempt in range(1, _ATTEMPTS + 1):
            error = self.sender(d.url, message)
            if error is None:
                return
            if attempt < _ATTEMPTS:
                time.sleep(wait)
                wait *= 2
        logger.warning("Notification %r (%s) not sent after %d tries: %s", d.name, message.title, _ATTEMPTS, error)
