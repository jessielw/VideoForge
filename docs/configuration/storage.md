# Storage and backups

VideoForge writes application data, per-source working files, and finished outputs to separate locations. Back up the application data and configuration; keep work folders when you need reuse.

## Application data

| Installation | Default data folder |
| --- | --- |
| Windows portable or source | `%APPDATA%\VideoForge` |
| Linux from source | `$XDG_DATA_HOME/VideoForge`, or `~/.local/share/VideoForge` |
| Docker | `/data` inside the container; `./data` in the Compose example |

`videoforge serve --data-dir <folder>` changes the data location.

The data folder contains:

| Path | Contents |
| --- | --- |
| `videoforge.db` | Queue, templates, saved settings, notification destinations, and actions |
| `logs/` | Application logs and the queue-wide `events.jsonl` stream |
| `records/` | Preserved job records and text logs from cleaned work folders |
| `plugins/` | Installed folder-based plugins |
| `plugin-data/` | Files owned by individual plugins |
| `plugin-staging/` | Pending plugin file changes, applied on the next start |

The newest **50 application session logs** are kept. The queue-wide event stream rolls over at **10 MB**, retaining three rotated files. Archived records and text logs retain the newest **100 of each**; they are not a permanent archive of every run.

## Per-source work folders

For `Show.S01E01.mkv`, the work folder is `Show.S01E01.mkv_tmp/` beside the source. What comes from the source alone (its index, an enhancement layer, HDR metadata, subtitles extracted for burning in) sits at the top, shared by every job on the source. Each job has its own folder in it, named by its label (`main/` without one): its `video.vpy`, video and audio encodes, pass statistics, chapters, its own `videoforge.log`, and its records and events.

```text
Show.S01E01.mkv_tmp/
  Show.S01E01.mkv.ffindex       shared: the source's index, HDR metadata, burn-in extracts
  finished-steps.json
  main/                         the job without a label
    video.vpy  video.hevc  audio0_eng.ac3  chapters.qpf
    videoforge.log
    Show.S01E01.mkv.videoforge.json
  dubbed/                       the job labelled "dubbed"
    video.vpy  video.hevc  audio0_jpn.ac3 ...
    videoforge.log
    Show.S01E01.dubbed.mkv.videoforge.json
```

When two jobs on one source would make the same encode (dubbed and subbed usually differ only in the mux), the second links the first one's file into its own folder instead of encoding again: a hard link, so it takes no extra space, or a copy where the drive can't link. Renaming a label later starts a new folder; the old one stays until the work folder is removed.

The source directory must be writable. Allow space for intermediate video and audio in addition to the final output.

## Cleanup

**Settings → Work folders** can delete a done job's working files automatically, once no other job in the queue uses the source. Records and the text logs are copied to the data folder's `records/` first. Per-output `.jsonl` files are not archived there; the queue-wide event stream still has the same events until it rotates.

The Queue's **Remove → Remove and delete work folders** shows the folders and their sizes for confirmation, then archives the same records and log before removing working files. If archiving fails, the folder is kept and the error is shown. Keep a work folder if you expect to reuse its encodes. Removing intermediate files means the affected steps must run again. Queue-only removal offers **Undo** while this server session remains open (the latest 100 removed jobs are retained).

## Back up

### Share templates and presets

Use **Settings → Preset sharing → Export presets…** to choose templates, video encoder presets, audio encoder presets, and video processing presets for a group. The resulting preset pack keeps display names, nested folders, and encoding settings. It excludes application settings, tool paths, saved folder choices, notification URLs, actions, plugin configuration, and default selections.

Use **Import presets…** in the same panel to preview and select entries from a pack. A matching name (for encoder and audio presets: in the same encoder and folder) replaces yours, so importing an updated pack again adds no duplicates; tick **Keep both** for numbered copies instead. Local settings and defaults stay the same. Review any custom scripts and extra arguments before sharing: user-authored text is preserved and can contain private paths or values.

### Full configuration backup

For a configuration-only backup, open **Settings → Configuration backup → Export configuration**. One JSON file includes all saved templates, video processing presets, video and audio encoder presets (with names and folders), default template selections, app settings, tool paths, folder choices, notifications, actions, pairing rules, and plugin configuration and switches.

Use **Import configuration…** in the same panel to preview the libraries and included scripts and actions before replacing your configuration. Export your current configuration first if you want to keep it. The restore is atomic and preserves template default references. Empty libraries in a backup clear that library. Existing jobs keep their own settings. Unavailable profiles and browser roots are reported; install missing profiles and check paths when moving between machines. Plugin configuration changes require a restart. New exports use configuration format version 4, including saved plugin form values, the default subtitle rules and the test encode's quality score setting. Version 3 and older backups restore that setting off; version 2 backups restore no default subtitle rules; version 1 backups also restore an empty set of plugin UI overrides. Plugin staging and the startup permission to manage plugins are not transferred. The template editor and New jobs preset selections reset to the imported defaults; selected source files in the New jobs form are kept.

Configuration files support up to 20 MiB and 5,000 presets in each library. They can contain credentials embedded in notification URLs, action targets, or plugin settings, plus scripts and command actions; keep backups private and review files before importing them. Exporting and previewing never execute included code. The file excludes jobs, logs, media, work folders, installed tools, plugin code and plugin-owned files, browser-local drafts, and server launch options such as host, port, and data directory.

To back up the queue and all application files as well:

1. Stop VideoForge, or stop the Docker service with `docker compose stop`.
2. Copy the entire data folder to your backup location.
3. Copy `videoforge.local.toml`, any custom configuration, and your Compose file separately.
4. Copy any work folders whose intermediate encodes you need to preserve.
5. Restart VideoForge, or run `docker compose start`.

Saved destinations and plugin settings can contain service credentials. Keep their backups private.

## Restore or move machines

Stop the application, restore the data folder and configuration, and start with that data folder. Check tool paths and every saved source and output path before running the queue. Docker jobs use container paths, so retaining the same mount paths avoids rewriting job inputs.

For the machine-readable output format, see [Job records and events](../job-record.md).
