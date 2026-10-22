# Event logger

A minimal plugin showing all four event slots. It writes messages to VideoForge's logs and does
not change jobs, move files or contact external services. It requires no additional packages.

## Install and configure

1. Download `VideoForge-plugin-event_logger-1.0.zip` from a
   [VideoForge release](https://github.com/jessielw/VideoForge/releases), or build it using
   `python scripts/build_plugin_examples.py` from the repository root.
2. Import the ZIP through **Settings → Plugins → Install ZIP…**.
3. Open **Details and settings → Configure Event logger**. Keep the default **Log prefix**, or enter your own.
4. Restart VideoForge and confirm the plugin shows **Running** with **Enabled** checked.

Alternatively, copy this folder into the plugin folder shown in Settings and restart.
Changing the prefix or the Enabled checkbox takes effect on the next start.

## Settings

| Key | Form label | Default | Effect |
| --- | --- | --- | --- |
| `prefix` | Log prefix | `Event logger` | Text at the beginning of each message |

The same setting can be supplied in `videoforge.local.toml`:

```toml
[plugins.event_logger]
prefix = "My plugin"
```

Saved form values override TOML values. Use **Reset overrides** to return to the TOML value or default.

## Try the events

| Event | How to trigger it | Where to look | Example message |
| --- | --- | --- | --- |
| `JobStarted` | Start a queued job | The job's Log tab | `Event logger: started Movie.mkv` |
| `JobFinished` | Let a job finish, fail, or cancel it | The job's Log tab | `Event logger: finished with done` |
| `IndexFinished` | Use the Queue's Index control | The job's Log tab | `Event logger: index finished` |
| `QueueFinished` | Let the queue finish | The app log in the data folder's `logs/` directory | `Event logger: queue finished (1 jobs, 0 left)` |

`IndexFinished` reports the background index lane, rather than every indexing step inside an encode.
A shutdown cancellation sends no `JobFinished`, because that job is resumed on the next start.

## Read the source

- [event_logger.py](event_logger.py) contains the four callbacks and the exported `Plugin` object.
- [videoforge-plugin.toml](videoforge-plugin.toml) declares the plugin identity and its settings form.

Each callback receives an event snapshot and `PluginContext`. `ctx.job_log` writes to a job's log;
`ctx.log` writes to the application log. This is a starting template for your own plugin: choose a
new plugin id and module name before distributing your version.
