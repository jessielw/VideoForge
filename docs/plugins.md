# Plugins

A plugin is Python code that VideoForge calls when things happen: a job starts or ends, the queue
finishes, a source is indexed. Use one when an [action](actions.md) isn't enough: talk to a server's
API, read the job record, decide per job what to do.

[examples/plugins/library_scan](https://github.com/jessielw/VideoForge/tree/main/examples/plugins/library_scan)
is a complete one (it asks Jellyfin to scan after jobs are done).

## A plugin

A folder in the plugins folder (`%APPDATA%\VideoForge\plugins` on Windows; Settings → Plugins
shows where), holding a manifest and a module:

```text
plugins/
  library_scan/
    videoforge-plugin.toml
    library_scan.py          (or a package: library_scan/__init__.py, ...)
    vendor/                  (optional: packages it brings along)
```

```toml
# videoforge-plugin.toml
id = "library_scan"          # unique; the settings table and the data folder are named after it
module = "library_scan"      # imported from this folder only
# object = "plugin"          # the Plugin's name in the module (this is the default)
```

```python
# library_scan.py
from videoforge.plugins import JobFinished, JobStatus, Plugin, PluginContext


def job_finished(event: JobFinished, ctx: PluginContext) -> None:
    if event.status is JobStatus.DONE:
        ctx.log.info("%s is done: %s", event.spec.name, event.output)
        ctx.job_log(event.spec.id, "Library scan: asked")  # shows in the job's log


plugin = Plugin(name="Library scan", version="1.0", on_job_finished=job_finished)
```

VideoForge loads plugins when it starts. Restart it after adding, changing or removing one.

An installed package can be a plugin too, through an entry point (the name is the id):

```toml
[project.entry-points."videoforge.plugins"]
library_scan = "videoforge_library_scan:plugin"
```

If two plugins have the same id, the one in the plugins folder wins. The other fails to load.

## What you get

`Plugin` fields (all optional but `name`):

| Field | Called with | When |
| --- | --- | --- |
| `setup` | `ctx` | once, after loading, before any event |
| `on_job_started` | `JobStarted(spec, output)`, `ctx` | a run begins (`output`: where it will write) |
| `on_job_finished` | `JobFinished(spec, result, seconds, record)`, `ctx` | a run ends (`.status`, `.output` for short) |
| `on_queue_finished` | `QueueFinished(statuses, seconds, left)`, `ctx` | the queue's worker stops |
| `on_index_finished` | `IndexFinished(spec, error)`, `ctx` | the index lane finished a source |

A job cancelled by shutting VideoForge down sends no `JobFinished`, because it resumes on the next start.

`JobFinished.record` is the path of the job record (`<output>.videoforge.json`, see
[job-record.md](job-record.md)): every track, where it came from, the encode settings, the tools'
versions. Read that instead of digging into `spec` and `result`.

`PluginContext`:

- `id`: the plugin's id.
- `settings`: its table from videoforge.toml (or videoforge.local.toml), e.g. `[plugins.library_scan]`.
- `data_dir`: `<data dir>/plugin-data/<id>`, the plugin's own files (made before `setup`).
- `log`: a logger writing to the app log, as `videoforge.plugin.<id>`.
- `job_log(job_id, line)`: adds a line to a job's log, shown in the browser.

## How it runs

- Each plugin has a thread of its own. Its functions are called one at a time, in event order. A slow
  plugin delays only its own later calls. The queue and other plugins keep going.
- An event is a snapshot. Its `spec` is a copy, so changing it changes nothing.
- A function that raises is logged, and the next event still comes. A plugin that fails to load
  (an import error, a bad manifest, a newer `api_version` than this VideoForge has) is listed on
  Settings → Plugins with the reason. VideoForge starts anyway.
- Settings → Plugins can switch a plugin off. It isn't even imported on the next start, which is how
  you get past one that breaks while loading.

## Packages

A plugin can import:

- the standard library (the portable build ships a full CPython, not a frozen app),
- anything VideoForge itself depends on, including `niquests` (HTTP), `apprise`, `pymediainfo`,
  `numpy`, `pillow`, and `rich`,
- packages in its own `vendor/` folder (`pip install --target vendor <package>`, using a Python of
  the same version as VideoForge's for anything compiled). They go on the import path after
  VideoForge's own, so a vendored copy of a package VideoForge already has is not the one used.

## The API

Import only from `videoforge.plugins`: `Plugin`, `PluginContext`, the four events, `JobSpec`,
`JobResult`, `JobStatus`, `API_VERSION`. The rest of VideoForge changes without notice.
`API_VERSION` goes up when something there changes in a way that breaks plugins. Set
`api_version` on your `Plugin` if you rely on a newer one.
