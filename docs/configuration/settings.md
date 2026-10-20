# Settings and configuration files

Use **Settings** for tool paths, the default profile, folder browser roots, indexing behavior,
parallel audio, priorities, cleanup, notifications, actions, and plugin switches. Changes save
immediately to the application database.

## Configuration precedence

For settings available in both places, the application uses these layers in order:

1. `videoforge.toml`: shipped defaults in the application folder.
2. `videoforge.local.toml`: machine-specific overrides beside that file; tables merge recursively.
3. Saved **Settings** values in `videoforge.db`: override the file defaults for the server.

Reset a setting in the UI to return to its file default. Editing a TOML file does not override an
existing saved UI value. Restart VideoForge after editing a configuration file.

The command-line `plan`, `run`, and `validate` commands load file configuration; server UI overrides
are not a replacement for their file configuration.

## Local tool paths

Use TOML literal strings for Windows paths so backslashes do not need escaping:

```toml
profile = "manual"

[tools]
mkvmerge = 'D:\Tools\MKVToolNix\mkvmerge.exe'
x265 = 'D:\Tools\x265\x265.exe'
ffmpeg = 'D:\Tools\ffmpeg\bin\ffmpeg.exe'
vs_plugins = 'D:\Tools\vs-plugins'
```

Relative paths resolve against the configuration file's folder. Bare names such as `ffmpeg` are
looked up on `PATH`. `mkvextract` and `mkvpropedit` are found beside `mkvmerge`, and `ffprobe` beside
`ffmpeg`, unless explicitly configured. The default `vspipe` is the one installed with VideoForge's
Python environment.

For Docker, use container paths. A local configuration file can be mounted at
`/app/videoforge.local.toml`.

## Pipeline settings

```toml
[pipeline]
parallel_audio = 2
delete_work_dir = false
encoder_priority = "below_normal"
tool_priority = "normal"
```

| Setting | Effect |
| --- | --- |
| `parallel_audio` | Number of audio encodes alongside a job's video; `0` runs audio encodes one by one. The UI accepts 0–8. |
| `delete_work_dir` | Remove a successfully completed job's work folder after preserving its records and log |
| `encoder_priority` | Default priority for the video encoder and its `vspipe` |
| `tool_priority` | Default priority for the other tools |

Priorities are `idle`, `below_normal`, `normal`, `above_normal`, or `high`. Linux maps these to nice
values; raising priority requires the appropriate permissions. The Queue toolbar can change a
running job's priority separately.

Deleting work folders also deletes the intermediate encodes used for reuse. See
[Storage and backups](storage.md) before enabling cleanup.

## Pairing settings

```toml
[pairing]
encode_suffixes = ["_job", "_out", "_new", ""]
encode_extensions = [".h264", ".264", ".avc", ".hevc", ".265", ".h265"]
scan_source_folder = true
staxrip_temp = true
```

Suffixes match existing video encodes to source stems; episode names can also match by `SxxEyy`.
`scan_source_folder` also finds matching SRTs beside the source and one folder down.
`staxrip_temp` reads the source's StaxRip temp folder for an encode still running and chapter files.

## Actions and plugins

`[actions] commands = true` permits command actions; Docker ships with it disabled. The full command
and webhook behavior is described under [Notifications and actions](../actions.md).

Plugin configuration uses one table per plugin, such as `[plugins.library_scan]`. The plugin decides
the meaning of its keys. See [Plugins](../plugins.md).

## Listening address and data folder

These are command-line options:

```sh
uv run videoforge serve --port 8765 --data-dir "D:\VideoForgeData"
```

The default host is `127.0.0.1`. There is no login, so use an authenticated proxy if you expose the
server beyond the machine. See the [command-line reference](../reference/cli.md).
