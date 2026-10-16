# Job record and events (schema v1)

VideoForge writes what each job run did in a form other tools can read: NFO generators, uploaders,
anything that wants to know how a release was made without parsing a text log. This is the contract:
fields are only added within a schema version (`v`); a change that would break a reader bumps `v`.

## Where the files are

Each job has a work folder next to its source, `<source file name>_tmp/` (for `Show.S01E01.mkv`:
`Show.S01E01.mkv_tmp/`). In it, named after the **output file**:

| File | What |
| --- | --- |
| `<output name>.videoforge.json` | The **record**: how that output was made. Written when a run makes the output. |
| `<output name>.videoforge.jsonl` | The **events**: one JSON object per line, appended while runs happen. |
| `videoforge.log` | The text log a person reads: every run and index of this source, every tool's output. |

`<output name>` is the whole file name, extension included (`Show.S01E01.dubbed.mkv.videoforge.json`),
so outputs made from one source (a job label such as `dubbed`, or MKV and MP4) each keep their own
files. Glob `*.videoforge.json` in a work folder to find every output made from that source.

VideoForge also appends every job's events, plus the index lane's, to one stream in its data folder:
`%APPDATA%\VideoForge\logs\events.jsonl` on Windows (`$XDG_DATA_HOME/VideoForge` or
`~/.local/share/VideoForge` elsewhere; `serve --data-dir` moves it). It rolls over at 10 MB to
`events.jsonl.1` (three kept). The app's own log is in the same folder, one file per session
(`videoforge_<YYYY-mm-dd_HH-MM-SS>.log`, the newest 50 kept).

## Reading a record

- **Completed** means: the record exists and `run.status` is `"done"`. `"invalid"` means the output
  was written but failed VideoForge's output check (`issues` says why). Nothing else is written as a
  record: a failed or cancelled run leaves the previous record (if any) in place, because the output
  file it describes is still the one there.
- A later run to the same output **replaces** the record. The events file keeps every run.
- Paths are absolute, as they were on the machine that ran the job. An output moved or renamed
  after the run is not followed: treat `output.path` as where it was written, and match by name, size
  or your own means if it moved.
- Times are local ISO 8601 with the UTC offset (`2026-10-15T21:04:05.123+02:00`).
- The file is written atomically (a `.partial` beside it, then renamed), so a reader never sees half
  of one.

## Record fields

```jsonc
{
  "v": 1,                                  // schema version
  "videoforge": "0.1.0",                   // the VideoForge that wrote it
  "run": {
    "id": "3f9c2a7b1d04",                  // this run (the events carry it too)
    "status": "done",                      // "done" | "invalid"
    "started": "...", "finished": "...", "seconds": 812.4,
    "error": null
  },
  "job": {
    "id": "a1b2c3d4e5f6",                  // VideoForge's job id (stable while the job is in the queue)
    "name": "Show.S01E01.mkv",             // the source file name
    "label": "dubbed",                     // the user's label for this run ("" for none)
    "profile": "manual",                   // the profile whose rules planned it
    "episode": "S01E01"                    // from the source name (SxxEyy), or null
  },
  "source": { "path": "...", "name": "...", "size": 123, "modified": "..." },
  "output": { "path": "...", "name": "...", "size": 123, "modified": "...", "container": "mkv" },
  "work_dir": "...",
  "log": ".../videoforge.log",
  "events": ".../<output name>.videoforge.jsonl",
  "original_language": "en",               // the content's original language as the job had it

  "video": { ... },                        // see below
  "audio": [ ... ],                        // output order
  "subtitles": [ ... ],                    // output order
  "chapters": { "from": "autoqpf", "path": "...", "qpfile": "..." },
  "steps": [ ... ],
  "issues": [ ... ],
  "tools": { "x264": "x264 0.165.3222 b35605a", "mkvmerge": "mkvmerge v97.0 ...", ... }
}
```

### `video`

When VideoForge encoded the video:

```jsonc
{
  "encoded": true,
  "encode": ".../video.264",               // the raw encode in the work folder
  "width": 1920, "height": 800,            // after crop / resize
  "language": "en",
  "script": { "path": ".../video.vpy", "text": "import vapoursynth as vs\n..." },
  "source_filter": "ffms2",                // "ffms2" | "lsmash" | "bestsource"
  "crop": { "left": 0, "top": 140, "right": 0, "bottom": 140 },
  "resize": null,                          // or { "width", "height", "kernel" }
  "filters": "",                           // extra script lines, as typed
  "custom_script": false,                  // true: the user wrote the script body
  "encoder": {
    "name": "x264",                        // "x264" | "x265"
    "rate_control": "crf",                 // "crf" | "abr" | "2pass"
    "crf": 18.0, "bitrate_kbps": 10000,    // the one rate_control uses counts
    "preset": "slower", "tune": "", "depth": 8,
    "options": { "aq-mode": "3" },         // --name value (an empty value is a bare flag)
    "extra": ""                            // raw arguments, as typed
  },
  "commands": ["vspipe ... | x264 ..."]    // one per pass, as a shell would take them
}
```

When the job reused an existing encode: `{ "encoded": false, "encode": "<that file>", "language": "en" }`.

### `audio[]` and `subtitles[]`

One entry per output track, in output order. `index` is the position among that kind (0-based);
`track` is the position in the output file (0-based, the video is 0, then audio, then subtitles).

```jsonc
{
  "index": 0, "track": 1,
  "source": {
    "kind": "source",                      // "source": a track of the job's source; "file": an added file
    "path": "...",                         // the file the track was read from
    "id": 1,                               // its mkvmerge track id in that file (all tracks, 0-based)
    "index": 0,                            // its position among that file's audio (or subtitle) tracks, 0-based
    "copy": 0,                             // audio: 1, 2, ... = another output made from the same track
    "codec": "truehd", "layout": "7.1", "atmos": true, "language": "en", "title": "..."
                                           // subtitles: "format", "language", "title"
  },
  "action": "ddp",                         // audio: "copy", or the encode ("ddp", "atmos", "aac", "flac", "opus", ...)
  "encoder": { "label": "DDP (DEE)", "tools": ["deezy", "dee"] },   // null for a copy
  "command": "deezy encode ...",           // null for a copy
  "file": ".../audio_2.ec3",               // the encoded file in the work folder; null for a copy
  "codec": "eac3", "layout": "5.1", "channels": 6, "atmos": false, "bitrate_kbps": 640, "delay_ms": 0,
  "language": "en", "title": "English DDP 5.1",
  "default": true, "forced": false, "hearing_impaired": false,
  "commentary": false, "original": true, "visual_impaired": false
}
```

Subtitle entries have `format` (`"srt"`, `"pgs"`, `"ass"`, `"tx3g"`, ...: as the output holds it, so an SRT
muxed into MP4 is `"tx3g"`; `source.format` is what it was) instead of the audio fields after `source`, and the same language, title and flags. For a track of the source, `source.id` and
`source.index` are what `mkvmerge -J` and ffmpeg (`a:N` / `s:N`) call it; add 1 for a 1-based count.

### `chapters`

`from` is `"autoqpf"` (generated from the source, with the `qpfile` the encoder placed keyframes
by), `"file"` (a chapter file the user gave: `path`), `"source"` (the source's own chapters) or
`null` (none).

### `steps[]` and `issues[]`

```jsonc
{ "id": "video", "label": "Video (x264)", "status": "done", "seconds": 700.2,
  "exit_code": 0, "command": "...", "error": null }
```

`status` is `"done"`, `"reused"` (finished in an earlier run and still valid, so skipped), `"failed"`,
`"cancelled"` or `"pending"`. Issues: `{ "stage": "plan" | "output", "severity": "info" | "warn" |
"block", "code": "...", "message": "..." }`; `plan` issues are what the job's plan warned about,
`output` issues come from checking the finished file.

### `tools`

The version line of each tool the run used, keyed by VideoForge's tool name (`vspipe`, `x264`,
`x265`, `ffmpeg`, `qaac`, `opusenc`, `deezy`, `dee`, `truehdd`, `mkvmerge`, `mp4box`); `""` when the
tool printed none.

## Events

Each line of a `.videoforge.jsonl` (and of the queue-wide `events.jsonl`) is one object:

```jsonc
{ "v": 1, "time": "...", "event": "step.finished", "job": "a1b2c3d4e5f6", "run": "3f9c2a7b1d04", ... }
```

| `event` | Fields |
| --- | --- |
| `run.started` | `name`, `label`, `profile`, `source`, `output` (planned path, or null), `container`, `work_dir`, `issues` (the plan's) |
| `step.started` | `step` (id), `label`, `n` (1-based), `total`, `command`. Not sent for a reused step |
| `step.finished` | `step`, `label`, `n`, `total`, `status` (`done`, `reused`, `failed`, `cancelled`), `seconds`, `exit_code`, `command`, `error` |
| `run.finished` | `status` (`done`, `invalid`, `failed`, `skipped`, `cancelled`), `output`, `error`, `seconds`, `record` (its path, or null), `issues` (the output check's) |
| `index.started` | `name` (queue-wide stream only: the index lane, which has no output yet) |
| `index.finished` | `name`, `error` (null when it worked; `"Cancelled"` when stopped) |
| `action.finished` | `action` (its name), `type` (`command`, `move`, `copy`, `webhook`), `error` (null when it worked), `output` (after a move: the new path), `seconds`; `job` is null for the queue's actions (queue-wide stream only; docs/actions.md) |

Lines are flushed one at a time, so `tail -f` (or reading new lines as they appear) follows a run
live. A reader should skip events it doesn't know: new ones may be added within a version.
