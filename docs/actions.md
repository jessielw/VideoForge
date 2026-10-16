# Actions

Settings → Actions: what VideoForge does after a job ends or the queue finishes. Each action has a
kind, a target and the events it runs on (the same events as notifications: job done, job failed,
job cancelled, queue finished).

| Kind | Target | What it does |
| --- | --- | --- |
| Run a command | a command line | Runs it (no shell). |
| Move the output | a folder | Moves the job's output into it. The actions after it see the new path. |
| Copy the output | a folder | Copies the output into it. |
| Send a webhook | an `http(s)://` URL | POSTs the event as JSON (below); retried twice. |

A job's actions run in the order they're listed, one after another, on a thread of their own, so the
queue never waits for them. One that fails doesn't stop the next. Each outcome goes to:

- the job's log (`Action 'To library': moved to D:\Library\Show.S01E01.mkv`),
- the app log,
- the queue-wide `events.jsonl` as an `action.finished` event (docs/job-record.md).

## Tokens

Commands and folders can use `{tokens}`. Write `{{` and `}}` for a literal brace. An unknown token
is refused when the action is saved.

After a job: `{output}`, `{output_dir}`, `{output_name}`, `{output_stem}`, `{source}`,
`{source_dir}`, `{work_dir}`, `{record}` (the job record), `{name}`, `{label}`, `{job}` (its id),
`{status}` (done, invalid, failed, skipped, cancelled). A token the job doesn't have (no output) is empty.

When the queue finishes: `{status}` (finished, or stopped with jobs still queued), `{jobs}`, `{done}`,
`{failed}`, `{left}`, `{took}`.

An action for both a job's end and the queue's can use only `{status}`.

## Commands

The command line is split into arguments first (Windows rules on Windows: `"..."` groups words,
backslashes are path separators), and the tokens are filled into each argument afterwards. So a file
name with spaces or quotes stays one argument and is never read by a shell. For pipes, redirection or
a batch file's built-ins, run the shell yourself:

```text
"C:\Tools\scan.exe" --library Movies --file "{output}"
cmd /c echo {name} done >> D:\done.txt
```

A command still running after an hour is stopped and the action fails. A failed command's exit code
and the end of its output go in the job's log.

**Commands are off unless videoforge.toml allows them:**

```toml
[actions]
commands = true
```

The web page has no login: anyone who can reach it could add a command. The shipped
`videoforge.toml` turns commands on (VideoForge listens on this machine only); the Docker image's
turns them off. Turn them on there in a `videoforge.local.toml` only if no one else can reach it.

## Move and copy

The folder is made when it's missing. The file goes to `<name>.partial` first and is renamed when
it's complete, so a library scanner never sees half a file (a move on the same disk is just a
rename). A file already there is left alone and the action fails, unless "Replace a file already
there" is on. Moving the output doesn't change the job record or the history, which keep the path the
run wrote.

## Webhook body

```jsonc
{
  "event": "job_done",              // job_done, job_failed, job_cancelled
  "title": "Job done",
  "job": {
    "id": "a1b2c3d4e5f6", "name": "Show.S01E01.mkv", "label": "", "status": "done",
    "source": "D:\\src\\Show.S01E01.mkv",
    "output": "D:\\out\\Show.S01E01.mkv",   // after a move: where it is now; null when there's none
    "work_dir": "D:\\src\\Show.S01E01.mkv_tmp",
    "record": "D:\\src\\Show.S01E01.mkv_tmp\\Show.S01E01.mkv.videoforge.json",  // null when none was written
    "error": null,
    "seconds": 1834.2
  }
}
```

When the queue finishes:

```jsonc
{
  "event": "queue_finished",
  "title": "Queue finished",
  "queue": { "status": "finished", "jobs": 4, "done": 3, "left": 0, "seconds": 7202.5 }
}
```

A 2xx answer counts as sent. Anything else (or no answer in 30 seconds) is tried again after 2 and 4
seconds.

For anything actions can't do, write a [plugin](plugins.md).
