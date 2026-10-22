# Plugins

A plugin is Python code that VideoForge calls when things happen: a job starts or ends, the queue
finishes, a source is indexed. Use one when an [action](actions.md) isn't enough: talk to a server's
API, read the job record, decide per job what to do.

[examples/plugins/library_scan](https://github.com/jessielw/VideoForge/tree/main/examples/plugins/library_scan)
is a complete one (it asks Jellyfin to scan after jobs are done).

## Install and configure

1. Open **Settings → Plugins → Install ZIP…** and choose a plugin ZIP.
2. Review its name and version, confirm you trust its Python code, and choose **Install on restart**.
3. Expand **Details and settings** and choose **Configure** if the plugin declares options.
4. Restart VideoForge. The plugin list shows whether it is running and any load or setup error.

Importing another ZIP with the same id offers **Replace on restart**, showing both versions. It keeps
the plugin's enabled state, settings and data. **Remove** deletes plugin code on the next restart;
settings and `plugin-data/<id>/` remain available if you reinstall it. Installed Python entry point
packages are managed outside this UI. A plugin with a pending file change must be restarted before
another file change can be queued.

ZIP previews and installation never import Python or install packages. Code executes when the app
next starts, with the same file and network access as VideoForge. The installer accepts a manifest at
the ZIP root or in one enclosing folder, up to 50 MiB compressed, 250 MiB extracted and 5,000 entries.
Invalid paths, links, encrypted files, duplicate names and Windows case collisions are rejected.

Web management defaults to enabled for loopback bindings and disabled for non-loopback bindings,
including Docker's `0.0.0.0`. Use `serve --plugin-management` to enable it explicitly, or
`--no-plugin-management` to disable it. This startup permission is not included in configuration backups.
Folder plugins can still be installed manually when web management is disabled.

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
name = "Library scan"        # required for ZIP installation
version = "1.0"              # required for ZIP installation
api_version = 1              # required for ZIP installation
description = "Scan the library after encoding."
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

IDs are compared without letter case. ZIP plugin ids use 1–64 ASCII letters, digits, underscores or
hyphens, beginning with a letter or digit, and must be valid Windows folder names. Replacements must
preserve the exact id. Older folder manifests containing only `id` and `module` remain supported.

## Declare settings

Add fields to the manifest to create a form under **Details and settings → Configure**:

```toml
[[settings]]
key = "url"
label = "Server URL"
help = "For example, http://localhost:8096"
required = true

[[settings]]
key = "api_key"
label = "API key"
type = "password"
required = true

[[settings]]
key = "when"
label = "Run after"
type = "choice"
choices = ["job", "queue"]
default = "queue"
```

Types are `text` (the default), `password`, `checkbox` (a boolean), `integer`, and `choice` (one of its
string `choices`). Keys are unique Python identifiers; labels default to their key. `help`, `default`
and `required` are optional. Required strings must be non-empty. There can be up to 100 fields.

Values arrive through `ctx.settings`. Precedence is manifest defaults, then `[plugins.<id>]` from
the effective application configuration, then saved UI overrides. Undeclared TOML keys are preserved.
**Reset overrides** restores the lower layers. Saves and resets take effect after restarting.
Missing or invalid required settings prevent setup and event callbacks; configure the plugin and restart.

Password fields are blank in the form; leaving them unchanged preserves their stored value. Clearing
a password saves an empty value (and is rejected when required). Passwords are stored with the app's
configuration, not encrypted; private configuration backups include them. Ordinary plugin inventory
and settings responses do not return password values.

## Package a plugin

From the plugin's folder, create a ZIP using VideoForge's Python (or any Python 3.12+):

```sh
python -m zipfile -c library_scan.zip videoforge-plugin.toml library_scan.py
```

For a package module, supply its directory instead of the `.py` file; include `vendor/` when needed.
Distribute the ZIP directly. Extra dependencies must be bundled; the installer works offline and never
modifies VideoForge's Python environment. Compiled dependencies must match the runtime's Python version,
OS and CPU architecture. Vendored imports share the process and are not isolated between plugins.

[examples/plugins/event_logger](https://github.com/jessielw/VideoForge/tree/main/examples/plugins/event_logger)
is a minimal starting point demonstrating all four slots. ZIP its manifest and `event_logger.py` to try it.

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
- `settings`: the effective manifest defaults, TOML settings and saved UI overrides for its id.
- `data_dir`: `<data dir>/plugin-data/<id>`, the plugin's own files (made before `setup`).
- `log`: a logger writing to the app log, as `videoforge.plugin.<id>`.
- `job_log(job_id, line)`: adds a line to a job's log, shown in the browser.

## How it runs

- Each plugin has a thread of its own. Its functions are called one at a time, in event order. A slow
  plugin delays only its own later calls. The queue and other plugins keep going.
- Each plugin receives an independent event snapshot. Changing its `spec` or `result` changes neither
  the job nor another plugin's event. Return values do not control processing.
- A function that raises is logged, and the next event still comes. A plugin that fails to load
  (an import error, a bad manifest, a newer `api_version` than this VideoForge has) is listed on
  Settings → Plugins with the reason. VideoForge starts anyway.
- Settings → Plugins can switch a plugin off. It isn't even imported on the next start, which is how
  you get past one that breaks while loading.
- A failed setup stops that plugin's callbacks until restart. A failed callback is logged and later
  callbacks continue. The plugin's details show its most recent failure.
- Threads do not sandbox plugins or forcibly stop an infinite loop; a stuck plugin can delay process
  exit. Plugin callbacks and built-in Actions run independently, with no ordering guarantee. In
  particular, an Action may move an output before a plugin reads the event's original output path.

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
