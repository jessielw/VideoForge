"""Notifications: the messages a job's end and the queue's make, and who gets them."""

from __future__ import annotations

from pathlib import Path

import apprise
import pytest

from videoforge.core.job import JobResult, JobSpec, JobStatus
from videoforge.core.models import Issue, JobInputs, Plan, Severity
from videoforge.core.notify import (
    DEFAULT_EVENTS,
    Destination,
    Event,
    Notifier,
    duration,
    job_message,
    load_destinations,
    queue_message,
    send,
)


def spec(label: str = "") -> JobSpec:
    return JobSpec(JobInputs(Path("D:/src/Show_S01E01.mkv")), "manual", label=label)


def result(status: JobStatus, **kw) -> JobResult:
    return JobResult(Plan.__new__(Plan), status, **kw)


def test_job_messages():
    done = job_message(spec("dubbed"), result(JobStatus.DONE, output=Path("D:/out/Show_S01E01.dubbed.mkv")), 3725)
    assert (done.event, done.kind, done.title) == (
        Event.JOB_DONE,
        apprise.NotifyType.SUCCESS,
        "Done: Show_S01E01.dubbed.mkv",
    )
    # the file name is verbatim (its underscores aren't markdown emphasis)
    assert done.body.splitlines() == [
        "- **Label:** dubbed",
        f"- **Output:** `{Path('D:/out/Show_S01E01.dubbed.mkv')}`",
        "- **Took:** 1h 02m",
    ]

    issues = [Issue(Severity.BLOCK, f"c{n}", f"problem {n}") for n in range(7)] + [Issue(Severity.WARN, "w", "minor")]
    invalid = job_message(spec(), result(JobStatus.INVALID, output=Path("o.mkv"), issues=issues), 5)
    assert invalid.event is Event.JOB_FAILED and invalid.title == "Invalid output: o.mkv"
    assert "- problem 4\n- and 2 more" in invalid.body and "minor" not in invalid.body

    failed = job_message(spec(), result(JobStatus.FAILED, error="x264 exited 1\n" + "x" * 4000), 61)
    assert (failed.event, failed.kind, failed.title) == (
        Event.JOB_FAILED,
        apprise.NotifyType.FAILURE,
        "Failed: Show_S01E01.mkv",
    )
    assert "**Error**\n```\nx264 exited 1" in failed.body and "[truncated]\n```" in failed.body
    assert len(failed.body) < 2000

    cancelled = job_message(spec(), result(JobStatus.CANCELLED, error="Cancelled"), 1)
    assert cancelled.event is Event.JOB_CANCELLED and "Error" not in cancelled.body


def test_queue_message():
    q = queue_message([JobStatus.DONE, JobStatus.DONE, JobStatus.FAILED], 90)
    assert (q.event, q.title, q.kind) == (Event.QUEUE_FINISHED, "Queue finished", apprise.NotifyType.WARNING)
    assert q.body == "- **Jobs:** 3 (2 done, 1 failed)\n- **Took:** 1m 30s"
    stopped = queue_message([JobStatus.DONE], 4, left=2)
    assert stopped.title == "Queue stopped" and stopped.kind == apprise.NotifyType.SUCCESS
    assert "- **Still queued:** 2" in stopped.body


def test_duration():
    assert [duration(s) for s in (0, 59.6, 61, 3600, 7322)] == ["0s", "1m 00s", "1m 01s", "1h 00m", "2h 02m"]


def test_destinations():
    d = Destination.from_json({"url": " tgram://123:abc/456 ", "events": ["job_failed"]})
    assert (d.name, d.url, d.enabled, d.events) == ("tgram", "tgram://123:abc/456", True, {Event.JOB_FAILED})
    assert Destination.from_json(d.to_json()) == d
    assert Destination.from_json({"url": "json://h"}).events == DEFAULT_EVENTS
    for bad in ({}, {"url": "not a url"}, {"url": "json://h", "events": ["nope"]}):
        with pytest.raises(ValueError):
            Destination.from_json(bad)
    assert [x.name for x in load_destinations([{"url": "gone://"}, {"name": "ok", "url": "json://h"}])] == ["ok"]


def test_notifier_sends_to_who_wants_it_and_retries():
    sent: list[str] = []
    tries = {"json://flaky": 2}  # fails twice, then goes

    def sender(url, _message):
        sent.append(url)
        if tries.get(url):
            tries[url] -= 1
            return "timeout"
        return None

    n = Notifier(sender, retry_wait=0)
    n.destinations = [
        Destination("all", "json://all"),
        Destination("off", "json://off", enabled=False),
        Destination("queue", "json://queue", events=frozenset({Event.QUEUE_FINISHED})),
        Destination("flaky", "json://flaky", events=frozenset({Event.JOB_DONE})),
    ]
    n.notify(job_message(spec(), result(JobStatus.DONE), 1))
    n.wait()
    assert sent == ["json://all", "json://flaky", "json://flaky", "json://flaky"]
    n.close()


def test_send_reports_why():
    assert send("nope", queue_message([], 0)) == "Apprise doesn't recognise this URL"
    error = send("json://127.0.0.1:9/", queue_message([], 0))  # nothing listens on the discard port
    assert error and "error" in error.lower()
