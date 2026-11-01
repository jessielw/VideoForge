# Settings and configuration files

Use **Settings** for tool paths, the default rule set, folder browser roots, indexing behavior, the test encode's [quality score](../usage/encoders.md#quality-score), parallel audio, priorities, cleanup, notifications, actions, and plugin switches. Changes save immediately to the application database.

## Profiles

A profile is a whole configuration: every **Settings** value, the templates, the encoder and video processing presets, and the default template selections. **Settings → Profiles** lists them: create, rename, switch to, or delete one. A new profile starts as a fresh install does, from `videoforge.toml`, or as a copy of the active profile. One profile is active at a time; the first one, made from an existing installation's configuration, is named **Default**.

The queue is shared: every profile sees the same jobs, and a job keeps the settings it was made with. Switching waits for the queue to stop and for indexing and test encodes to finish, then applies the other profile's settings at once. Installed plugins are shared; each profile keeps its own plugin settings and switches, which take effect when VideoForge starts again. The last profile, and the active one, can't be deleted.

Use **Settings → Encoder presets** to manage audio and video encoder libraries without opening a job or template. Both managers support folders, editing, duplication, import, and export, including the open draft's unsaved settings. Saving a library preset leaves existing jobs and templates as they are.

## Configuration precedence

For settings available in both places, the application uses these layers in order:

1. `videoforge.toml`: shipped defaults in the application folder.
2. `videoforge.local.toml`: machine-specific overrides beside that file; tables merge recursively.
3. An imported configuration backup, if present: supplies restored server defaults, including pairing and plugin settings. The TOML files themselves are not rewritten.
4. The active profile's saved **Settings** values in `videoforge.db`: override those defaults for the server.

Reset a setting in the UI to return to its default (from the imported backup, if one was restored). Editing a TOML file does not override an imported configuration or an existing saved UI value. Restart VideoForge after editing a configuration file.

Use **Settings → Configuration backup** to export the active profile's configuration and preset libraries, or import one into a new or existing profile, without creating a job. See [Storage and backups](storage.md#back-up).

The command-line `plan`, `run`, and `validate` commands load file configuration; server UI overrides are not a replacement for their file configuration.

## Local tool paths

Use TOML literal strings for Windows paths so backslashes do not need escaping:

```toml
rule_set = "manual"

[tools]
mkvmerge = 'D:\Tools\MKVToolNix\mkvmerge.exe'
x265 = 'D:\Tools\x265\x265.exe'
ffmpeg = 'D:\Tools\ffmpeg\bin\ffmpeg.exe'
vs_plugins = 'D:\Tools\vs-plugins'
```

Relative paths resolve against the configuration file's folder. Bare names such as `ffmpeg` are looked up on `PATH`. `mkvextract` and `mkvpropedit` are found beside `mkvmerge`, and `ffprobe` beside `ffmpeg`, unless explicitly configured. The default `vspipe` is the one installed with VideoForge's Python environment.

For Docker, use container paths. A local configuration file can be mounted at `/app/videoforge.local.toml`.

## Pipeline settings

```toml
[pipeline]
parallel_audio = 2
delete_work_dir = false
min_free_gb = 20
encoder_priority = "below_normal"
tool_priority = "normal"
```

| Setting | Effect |
| --- | --- |
| `parallel_audio` | Number of audio encodes alongside a job's video; `0` runs audio encodes one by one. The UI accepts 0–8. |
| `delete_work_dir` | Remove a successfully completed job's work folder after preserving its records and log |
| `min_free_gb` | Free space, in GB, the disks of a job's work folder and output folder each need when its run starts. With less, the run fails before its first step and the queue goes on. `0` turns the check off. |
| `encoder_priority` | Default priority for the video encoder and its `vspipe` |
| `tool_priority` | Default priority for the other tools |

Priorities are `idle`, `below_normal`, `normal`, `above_normal`, or `high`. Linux maps these to nice values; raising priority requires the appropriate permissions. The Queue toolbar can change a running job's priority separately.

Deleting work folders also deletes the intermediate encodes used for reuse. See [Storage and backups](storage.md) before enabling cleanup.

## Pairing settings

```toml
[pairing]
encode_suffixes = ["_job", "_out", "_new", ""]
encode_extensions = [".h264", ".264", ".avc", ".hevc", ".265", ".h265"]
scan_source_folder = true
staxrip_temp = true
```

Suffixes match existing video encodes to source stems; episode names can also match by `SxxEyy`. `scan_source_folder` also finds matching subtitle files (SRT, ASS/SSA, SUP, VobSub IDX) beside the source and one folder down. `staxrip_temp` reads the source's StaxRip temp folder for an encode still running and chapter files.

## Actions and plugins

`[actions] commands = true` permits command actions; Docker ships with it disabled. The full command and webhook behavior is described under [Notifications and actions](../actions.md).

Install plugin ZIPs, enable or disable plugins, and edit declared plugin options under **Settings → Plugins**. File changes and plugin settings apply after restart. TOML tables such as `[plugins.library_scan]` remain supported; saved form values override them. See [Plugins](../plugins.md).

## Listening address and data folder

These are command-line options:

```sh
uv run videoforge serve --port 8765 --data-dir "D:\VideoForgeData"
```

The default host is `127.0.0.1`. There is no login, so use an authenticated proxy if you expose the server beyond the machine. See the [command-line reference](../reference/cli.md).
