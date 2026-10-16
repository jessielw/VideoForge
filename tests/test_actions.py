"""Actions: checked when saved, tokens filled per argument, files placed safely, run in order."""

from __future__ import annotations

import os
from pathlib import Path
from typing import cast

import pytest

from videoforge.core.actions import (
    Action,
    ActionKind,
    ActionRunner,
    Outcome,
    place_file,
    split_command,
    webhook_body,
)
from videoforge.core.events import JobFinished, QueueFinished
from videoforge.core.job import JobResult, JobSpec, JobStatus
from videoforge.core.models import JobInputs, Plan
from videoforge.core.notify import Event


def finished(tmp_path: Path, status=JobStatus.DONE, *, write=True) -> JobFinished:
    source = tmp_path / "src" / "Show S01E01.mkv"
    out = tmp_path / "out" / "Show S01E01.mkv"
    if write:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"video")
    spec = JobSpec(JobInputs(source), "manual", output_dir=out.parent, label="dub")
    plan = cast(Plan, None)  # actions never read the plan
    result = JobResult(plan, status, out if status is not JobStatus.FAILED else None, error="x264 died")
    return JobFinished(spec, result, 65.0, out.with_name(out.name + ".videoforge.json"))


def action(**data) -> Action:
    return Action.from_json(data)


def test_from_json_checks_what_it_can():
    a = action(kind="command", target='notify "{output}"')
    assert a.name == "Run a command" and a.events == {Event.JOB_DONE} and a.enabled
    assert action(**a.to_json()) == a
    for bad, why in [
        ({"kind": "nope", "target": "x"}, "Unknown action kind"),
        ({"kind": "move", "target": " "}, "needs a folder"),
        ({"kind": "move", "target": "D:/x", "events": ["queue_finished"]}, "not when the queue finishes"),
        ({"kind": "command", "target": "x {outptu}"}, "Unknown token {outptu}"),
        ({"kind": "command", "target": "x {output}", "events": ["queue_finished"]}, "has no job"),
        ({"kind": "command", "target": "x {output}", "events": ["job_done", "queue_finished"]}, "only use {status}"),
        ({"kind": "command", "target": "x {"}, "literal brace"),
        ({"kind": "webhook", "target": "ftp://x"}, "http://"),
        ({"kind": "command", "target": "x", "events": ["nope"]}, "Unknown action event"),
    ]:
        with pytest.raises(ValueError, match=why.replace("{", r"\{").replace("}", r"\}")):
            action(**bad)
    assert action(kind="command", target="x {status} {{literal}}", events=["job_done", "queue_finished"])
    assert action(kind="command", target="x {jobs} {took}", events=["queue_finished"])


@pytest.mark.skipif(os.name != "nt", reason="Windows command-line splitting")
def test_split_command_keeps_windows_paths():
    assert split_command(r'"C:\Program Files\Tool\tool.exe" --in "{output}" -x C:\a\b') == [
        r"C:\Program Files\Tool\tool.exe",
        "--in",
        "{output}",
        "-x",
        r"C:\a\b",
    ]


def test_place_file_moves_copies_and_wont_overwrite(tmp_path):
    src = tmp_path / "a" / "f.mkv"
    src.parent.mkdir()
    src.write_bytes(b"1")
    copied = place_file(src, tmp_path / "lib", move=False, overwrite=False)
    assert copied.error is None and copied.output is None and (tmp_path / "lib" / "f.mkv").read_bytes() == b"1"
    assert src.exists()
    again = place_file(src, tmp_path / "lib", move=False, overwrite=False)
    assert again.error and "Already there" in again.error
    src.write_bytes(b"2")
    moved = place_file(src, tmp_path / "lib", move=True, overwrite=True)
    assert moved.output == tmp_path / "lib" / "f.mkv" and moved.output.read_bytes() == b"2"  # pyright: ignore[reportOptionalMemberAccess]
    assert not src.exists()
    assert not list((tmp_path / "lib").glob("*.partial"))
    assert place_file(src, tmp_path / "lib", move=True, overwrite=True).error


def test_runner_runs_in_order_and_a_move_carries_the_new_path(tmp_path):
    ran: list[list[str]] = []
    posted: list[tuple[str, dict]] = []
    logged: list[tuple[str, str]] = []
    reported: list[dict] = []
    runner = ActionRunner(
        [
            action(name="Off", kind="command", target="nope", enabled=False),
            action(name="Move", kind="move", target=str(tmp_path / "lib" / "{label}")),
            action(name="Scan", kind="command", target='scan "{output}" {name} {status}'),
            action(name="Hook", kind="webhook", target="https://example.invalid/x", events=["job_done", "job_failed"]),
            action(name="Bye", kind="command", target="bye {jobs} {done}", events=["queue_finished"]),
        ],
        allow_commands=True,
        job_log=lambda job, line: logged.append((job, line)),
        report=lambda kind, **f: reported.append({"event": kind} | f),
        run=lambda argv: ran.append(argv) or Outcome(detail="exit code 0"),
        post=lambda url, body: posted.append((url, body)) or None,
        retry_wait=0,
    )
    event = finished(tmp_path)
    runner.on_event(event)
    runner.on_event(QueueFinished((JobStatus.DONE, JobStatus.FAILED), 10.0))
    runner.wait()

    new = tmp_path / "lib" / "dub" / "Show S01E01.mkv"
    assert new.read_bytes() == b"video"
    assert ran == [["scan", str(new), "Show S01E01.mkv", "done"], ["bye", "2", "1"]]
    assert posted[0][1]["job"]["output"] == str(new) and posted[0][1]["event"] == "job_done"
    assert [line for _, line in logged] == [
        f"Action 'Move': moved to {new}",
        "Action 'Scan': exit code 0",
        "Action 'Hook': sent",
    ]
    assert [r["action"] for r in reported] == ["Move", "Scan", "Hook", "Bye"]
    assert reported[0]["output"] == str(new) and reported[3]["job"] is None


def test_commands_off_and_failures_dont_stop_the_rest(tmp_path):
    logged: list[str] = []
    calls = []

    def post(url, body):
        calls.append(url)
        return "HTTP 500"

    runner = ActionRunner(
        [
            action(name="Cmd", kind="command", target="x"),
            action(name="Copy", kind="copy", target=str(tmp_path / "lib")),
            action(name="Hook", kind="webhook", target="https://example.invalid/x", events=["job_failed"]),
        ],
        allow_commands=False,
        job_log=lambda _job, line: logged.append(line),
        post=post,
        retry_wait=0,
    )
    runner.on_event(finished(tmp_path))
    runner.on_event(finished(tmp_path, JobStatus.FAILED))
    runner.wait()
    assert logged[0].startswith("Action 'Cmd' failed: Commands are off")
    assert logged[1].startswith("Action 'Copy': copied to")
    assert logged[2] == "Action 'Hook' failed: Not sent after 3 tries: HTTP 500" and len(calls) == 3


def test_webhook_body(tmp_path):
    e = finished(tmp_path, JobStatus.FAILED, write=False)
    from videoforge.core.actions import job_tokens

    body = webhook_body(e, job_tokens(e))
    assert body["event"] == "job_failed" and body["job"]["error"] == "x264 died" and body["job"]["output"] is None
    assert body["job"]["label"] == "dub" and body["job"]["seconds"] == 65.0
    assert ActionKind("webhook") is ActionKind.WEBHOOK
