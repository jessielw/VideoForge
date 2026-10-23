"""Actions: what VideoForge does after a job ends or the queue runs out, set up on the Settings page.

An action is a kind, a target and the events it runs on (the notifications' events):

- **command**: run a program. The target is a command line; each argument's `{tokens}` are filled in
  after it is split, so a path with spaces stays one argument and nothing in it is read by a shell
  (for pipes or redirection, run the shell yourself: `cmd /c ...`, `sh -c "..."`). Commands run only
  when videoforge.toml allows them (`[actions] commands`): anyone who can open the web page could
  otherwise run anything on the machine.
- **move** / **copy**: the job's output into a folder (the target, which may hold tokens; made when
  missing). The copy goes to `<name>.partial` first and is renamed when complete, so a library scanner
  never sees half a file. An existing file is left alone (the action fails) unless `overwrite` is on.
  After a move, the actions that follow see the new path as `{output}`.
- **webhook**: POST the event as JSON to a URL (docs/actions.md has the body).

A job's actions run in the order they are listed, one at a time on a thread of their own, so a slow one
never holds up the queue. Each one's outcome goes in the job's log and the app log, and as an
`action.finished` event in the queue-wide events.jsonl. One that fails doesn't stop the next.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import StrEnum
import logging
import os
from pathlib import Path
import shlex
import shutil
import string
import subprocess
import time
from typing import Any

from videoforge.core.events import JobFinished, QueueFinished
from videoforge.core.job import JobStatus
from videoforge.core.notify import EVENT_LABELS, Event, duration

logger = logging.getLogger(__name__)

COMMAND_TIMEOUT = 3600.0  # seconds; a command still running then is stopped and the action fails
WEBHOOK_TIMEOUT = 30.0
_ATTEMPTS = 3  # webhook tries
_RETRY_WAIT = 2.0  # seconds before the 2nd try, doubled for the next
_OUTPUT_TAIL = 20  # lines of a failed command's output kept in the log


class ActionKind(StrEnum):
    COMMAND = "command"
    MOVE = "move"
    COPY = "copy"
    WEBHOOK = "webhook"


ACTION_LABELS: dict[ActionKind, str] = {
    ActionKind.COMMAND: "Run a command",
    ActionKind.MOVE: "Move the output",
    ActionKind.COPY: "Copy the output",
    ActionKind.WEBHOOK: "Send a webhook",
}
DEFAULT_EVENTS = frozenset({Event.JOB_DONE})
_FILE_KINDS = frozenset({ActionKind.MOVE, ActionKind.COPY})
_JOB_EVENTS = frozenset({Event.JOB_DONE, Event.JOB_FAILED, Event.JOB_CANCELLED})

# {token}: what it stands for. Job tokens are empty when the job has no such thing (no output yet).
JOB_TOKENS: dict[str, str] = {
    "output": "the output file",
    "output_dir": "the output's folder",
    "output_name": "the output's file name",
    "output_stem": "the output's file name without its extension",
    "source": "the source file",
    "source_dir": "the source's folder",
    "work_dir": "the source's work folder (<source>_tmp), shared by the jobs on the source",
    "job_dir": "the job's own folder in it (<source>_tmp/<label>, or main): its encodes, log and record",
    "record": "the job record (<output>.videoforge.json)",
    "name": "the job's name",
    "label": "the job's label",
    "job": "the job's id",
    "status": "how it ended: done, invalid, failed, skipped or cancelled",
}
QUEUE_TOKENS: dict[str, str] = {
    "status": "finished, or stopped (after the current job, with jobs still queued)",
    "jobs": "how many jobs it ran",
    "done": "how many of them are done",
    "failed": "how many aren't (invalid, failed, skipped, cancelled)",
    "left": "how many are still queued",
    "took": "how long it ran (e.g. 1h 05m)",
}


@dataclass(frozen=True, slots=True)
class Action:
    name: str
    kind: ActionKind
    target: str  # the command line, the folder or the URL
    enabled: bool = True
    events: frozenset[Event] = DEFAULT_EVENTS
    overwrite: bool = False  # move / copy: replace a file already there

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> Action:
        """One from the Settings page / the store. Raises ValueError saying what's wrong with it."""
        try:
            kind = ActionKind(data.get("kind"))
        except ValueError:
            raise ValueError(f"Unknown action kind: {data.get('kind')!r}") from None
        target = str(data.get("target") or "").strip()
        if not target:
            raise ValueError(
                {
                    ActionKind.COMMAND: "A command action needs a command",
                    ActionKind.MOVE: "A move action needs a folder",
                    ActionKind.COPY: "A copy action needs a folder",
                    ActionKind.WEBHOOK: "A webhook action needs a URL",
                }[kind]
            )
        events = data.get("events")
        try:
            chosen = DEFAULT_EVENTS if events is None else frozenset(Event(e) for e in events)
        except ValueError as ex:
            raise ValueError(f"Unknown action event: {ex}") from None
        if kind in _FILE_KINDS and Event.QUEUE_FINISHED in chosen:
            raise ValueError(f"{ACTION_LABELS[kind]} runs after a job, not when the queue finishes")
        if kind is ActionKind.WEBHOOK:
            if not target.lower().startswith(("http://", "https://")):
                raise ValueError("A webhook URL starts with http:// or https://")
        else:
            _check_tokens(target, chosen)
            if kind is ActionKind.COMMAND and not split_command(target):
                raise ValueError("A command action needs a command")
        name = str(data.get("name") or "").strip() or ACTION_LABELS[kind]
        return cls(name, kind, target, bool(data.get("enabled", True)), chosen, bool(data.get("overwrite", False)))

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind.value,
            "target": self.target,
            "enabled": self.enabled,
            "events": [e.value for e in Event if e in self.events],
            "overwrite": self.overwrite,
        }


def load_actions(items: Iterable[Mapping[str, Any]]) -> list[Action]:
    """The saved ones; one that no longer loads is skipped (and logged)."""
    out = []
    for item in items:
        try:
            out.append(Action.from_json(item))
        except ValueError as ex:
            logger.warning("Skipping the action %r: %s", item.get("name"), ex)
    return out


def _check_tokens(text: str, events: frozenset[Event]) -> None:
    """Every {token} is known for each event the action runs on (a queue has no output)."""
    try:
        names = [f for _, f, _, _ in string.Formatter().parse(text) if f is not None]
    except ValueError as ex:
        raise ValueError(f"{ex} (write {{{{ and }}}} for a literal brace)") from None
    jobs, queue = bool(events & _JOB_EVENTS), Event.QUEUE_FINISHED in events
    if jobs and queue:
        known, hint = (
            JOB_TOKENS.keys() & QUEUE_TOKENS.keys(),
            " (an action for a job's end and the queue's too can only use {status})",
        )
    elif queue:
        known, hint = QUEUE_TOKENS.keys(), " (the queue finishing has no job: no {output} or {source})"
    else:
        known, hint = JOB_TOKENS.keys(), ""
    for f in names:
        if not f:
            raise ValueError("An empty {} isn't a token (write {{ and }} for a literal brace)")
        if f not in known:
            raise ValueError(f"Unknown token {{{f}}}" + hint)


def split_command(command: str) -> list[str]:
    """A command line -> its arguments, as the system's own shell would split it (quotes kept off)."""
    if os.name != "nt":
        return shlex.split(command)
    # Windows: backslashes are path separators, not escapes; "..." groups words.
    lexer = shlex.shlex(command, posix=False)
    lexer.whitespace_split = True
    lexer.commenters = ""
    return [a[1:-1] if len(a) >= 2 and a[0] == a[-1] == '"' else a for a in lexer]


def job_tokens(event: JobFinished, output: Path | None = None) -> dict[str, str]:
    out = output if output is not None else event.output
    spec = event.spec
    return {
        "output": str(out) if out else "",
        "output_dir": str(out.parent) if out else "",
        "output_name": out.name if out else "",
        "output_stem": out.stem if out else "",
        "source": str(spec.inputs.source),
        "source_dir": str(spec.inputs.source.parent),
        "work_dir": str(spec.work_dir),
        "job_dir": str(spec.job_dir),
        "record": str(event.record) if event.record else "",
        "name": spec.name,
        "label": spec.label,
        "job": spec.id,
        "status": event.status.value,
    }


def queue_tokens(event: QueueFinished) -> dict[str, str]:
    done = sum(s is JobStatus.DONE for s in event.statuses)
    return {
        "status": "stopped" if event.left else "finished",
        "jobs": str(len(event.statuses)),
        "done": str(done),
        "failed": str(len(event.statuses) - done),
        "left": str(event.left),
        "took": duration(event.seconds),
    }


def fill(text: str, tokens: Mapping[str, str]) -> str:
    return text.format_map(tokens)


def event_of(event: JobFinished | QueueFinished) -> Event:
    if isinstance(event, QueueFinished):
        return Event.QUEUE_FINISHED
    return {
        JobStatus.DONE: Event.JOB_DONE,
        JobStatus.CANCELLED: Event.JOB_CANCELLED,
    }.get(event.status, Event.JOB_FAILED)


# --- doing them ------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Outcome:
    error: str | None = None  # None: it worked
    detail: str = ""  # what it did (moved to ..., exit code 0)
    output: Path | None = None  # move: where the output is now


def run_command(argv: list[str], timeout: float = COMMAND_TIMEOUT) -> Outcome:
    try:
        done = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except FileNotFoundError:
        return Outcome(f"Not found: {argv[0]}")
    except subprocess.TimeoutExpired:
        return Outcome(f"Still running after {duration(timeout)}; stopped")
    except OSError as ex:
        return Outcome(f"Couldn't start {argv[0]}: {ex}")
    if done.returncode:
        tail = (done.stderr.strip() or done.stdout.strip()).splitlines()[-_OUTPUT_TAIL:]
        return Outcome(f"Exit code {done.returncode}" + ("\n" + "\n".join(tail) if tail else ""))
    return Outcome(detail="exit code 0")


def place_file(src: Path, folder: Path, *, move: bool, overwrite: bool) -> Outcome:
    """Move or copy src into folder, through `<name>.partial` unless it's a rename on one disk."""
    if not src.is_file():
        return Outcome(f"The output isn't there: {src}")
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as ex:
        return Outcome(f"Can't make {folder}: {ex}")
    dest = folder / src.name
    if dest.resolve() == src.resolve():
        return Outcome(detail="already there", output=dest)
    if dest.exists() and not overwrite:
        return Outcome(f"Already there (overwrite is off): {dest}")
    try:
        if move:
            try:
                os.replace(src, dest)  # one disk: a rename
                return Outcome(detail=f"moved to {dest}", output=dest)
            except OSError:
                pass  # another disk: copy, then remove the original
        partial = dest.with_name(dest.name + ".partial")
        shutil.copy2(src, partial)
        os.replace(partial, dest)
        if move:
            src.unlink()
    except OSError as ex:
        with_partial = dest.with_name(dest.name + ".partial")
        with_partial.unlink(missing_ok=True)
        return Outcome(f"{'Move' if move else 'Copy'} failed: {ex}")
    return Outcome(detail=f"{'moved' if move else 'copied'} to {dest}", output=dest if move else None)


def webhook_body(event: JobFinished | QueueFinished, tokens: Mapping[str, str]) -> dict[str, Any]:
    kind = event_of(event)
    body: dict[str, Any] = {"event": kind.value, "title": EVENT_LABELS[kind]}
    if isinstance(event, QueueFinished):
        body["queue"] = {
            "status": tokens["status"],
            "jobs": len(event.statuses),
            "done": int(tokens["done"]),
            "left": event.left,
            "seconds": round(event.seconds, 1),
        }
        return body
    body["job"] = {
        "id": event.spec.id,
        "name": event.spec.name,
        "label": event.spec.label,
        "status": event.status.value,
        "source": tokens["source"],
        "output": tokens["output"] or None,
        "work_dir": tokens["work_dir"],
        "job_dir": tokens["job_dir"],
        "record": tokens["record"] or None,
        "error": event.result.error or None,
        "seconds": round(event.seconds, 1),
    }
    return body


def post_json(url: str, body: dict[str, Any], timeout: float = WEBHOOK_TIMEOUT) -> str | None:
    """POST body to url: None when the server took it (2xx), else why not."""
    import niquests  # only when a webhook goes out

    try:
        r = niquests.post(url, json=body, timeout=timeout, headers={"User-Agent": "VideoForge"})
    except Exception as ex:  # niquests' own errors, and a bug in it must not take the runner down
        return f"{type(ex).__name__}: {ex}"
    if r.status_code is None or not 200 <= r.status_code < 300:
        return f"HTTP {r.status_code} {r.reason or ''}".rstrip()
    return None


# --- the runner ------------------------------------------------------------------------------

JobLog = Callable[[str, str], None]  # (job id, line)
Report = Callable[..., None]  # (kind, **fields): an action.finished event for events.jsonl


@dataclass(eq=False)
class ActionRunner:
    """Runs each event's actions, in order, on one background thread (the EventBus subscriber)."""

    actions: list[Action] = field(default_factory=list)
    allow_commands: bool = False  # videoforge.toml [actions] commands
    job_log: JobLog | None = None
    report: Report | None = None
    run: Callable[[list[str]], Outcome] = run_command
    post: Callable[[str, dict[str, Any]], str | None] = post_json
    retry_wait: float = _RETRY_WAIT

    def __post_init__(self) -> None:
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="actions")

    def on_event(self, event: JobFinished | QueueFinished) -> None:
        kind = event_of(event)
        wanted = [a for a in self.actions if a.enabled and kind in a.events]
        if wanted:
            self._pool.submit(self._run_all, wanted, event)

    def wait(self) -> None:
        """Until every action started so far has finished."""
        self._pool.submit(lambda: None).result()

    def close(self) -> None:
        self._pool.shutdown(wait=False)

    def _run_all(self, actions: list[Action], event: JobFinished | QueueFinished) -> None:
        output = event.output if isinstance(event, JobFinished) else None
        for action in actions:
            tokens = job_tokens(event, output) if isinstance(event, JobFinished) else queue_tokens(event)
            started = time.monotonic()
            try:
                outcome = self._do(action, event, tokens, output)
            except Exception as ex:  # a bug must not stop the actions after it
                logger.exception("Action %r raised", action.name)
                outcome = Outcome(f"{type(ex).__name__}: {ex}")
            if outcome.output is not None:
                output = outcome.output
            try:
                self._tell(action, event, outcome, time.monotonic() - started)
            except Exception:
                logger.exception("Action %r: its outcome couldn't be reported", action.name)

    def _do(
        self, action: Action, event: JobFinished | QueueFinished, tokens: dict[str, str], output: Path | None
    ) -> Outcome:
        if action.kind is ActionKind.WEBHOOK:
            return self._post(action.target, webhook_body(event, tokens))
        if action.kind is ActionKind.COMMAND:
            if not self.allow_commands:
                return Outcome("Commands are off: set `commands = true` under [actions] in videoforge.toml")
            return self.run([fill(a, tokens) for a in split_command(action.target)])
        if output is None:
            return Outcome("The job has no output")
        folder = Path(fill(action.target, tokens)).expanduser()
        return place_file(output, folder, move=action.kind is ActionKind.MOVE, overwrite=action.overwrite)

    def _post(self, url: str, body: dict[str, Any]) -> Outcome:
        wait, error = self.retry_wait, None
        for attempt in range(1, _ATTEMPTS + 1):
            error = self.post(url, body)
            if error is None:
                return Outcome(detail="sent")
            if attempt < _ATTEMPTS:
                time.sleep(wait)
                wait *= 2
        return Outcome(f"Not sent after {_ATTEMPTS} tries: {error}")

    def _tell(self, action: Action, event: JobFinished | QueueFinished, outcome: Outcome, seconds: float) -> None:
        job, about = (event.spec.id, f" ({event.spec.name})") if isinstance(event, JobFinished) else (None, "")
        if outcome.error is None:
            line = f"Action {action.name!r}: {outcome.detail or 'done'}"
            logger.info("%s%s", line, about)
        else:
            line = f"Action {action.name!r} failed: {outcome.error}"
            logger.warning("%s%s", line, about)
        if job is not None and self.job_log is not None:
            self.job_log(job, line)
        if self.report is not None:
            self.report(
                "action.finished",
                job=job,
                action=action.name,
                type=action.kind.value,
                error=outcome.error,
                output=str(outcome.output) if outcome.output else None,
                seconds=round(seconds, 1),
            )
