# Storage and backups

VideoForge writes application data, per-source working files, and finished outputs to separate
locations. Back up the application data and configuration; keep work folders when you need reuse.

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

The newest **50 application session logs** are kept. The queue-wide event stream rolls over at
**10 MB**, retaining three rotated files. Archived records and text logs retain the newest **100
of each**; they are not a permanent archive of every run.

## Per-source work folders

For `Show.S01E01.mkv`, the work folder is `Show.S01E01.mkv_tmp/` beside the source. It contains the
index, `video.vpy`, video and audio encodes, pass statistics, `finished-steps.json`, the job log,
and per-output records and events.

The source directory must be writable. Allow space for intermediate video and audio in addition
to the final output. Jobs sharing a source use that source's work location.

## Cleanup

**Settings → Work folders** can delete a done job's working files automatically. Records and the
text log are copied to the data folder's `records/` first. Per-output `.jsonl` files are not archived
there; the queue-wide event stream still has the same events until it rotates.

The Queue's **Remove → Remove and delete work folders** also removes working files. Keep a work
folder if you expect to reuse its encodes. Removing intermediate files means the affected steps
must run again.

## Back up

1. Stop VideoForge, or stop the Docker service with `docker compose stop`.
2. Copy the entire data folder to your backup location.
3. Copy `videoforge.local.toml`, any custom configuration, and your Compose file separately.
4. Copy any work folders whose intermediate encodes you need to preserve.
5. Restart VideoForge, or run `docker compose start`.

Saved destinations and plugin settings can contain service credentials. Keep their backups private.

## Restore or move machines

Stop the application, restore the data folder and configuration, and start with that data folder.
Check tool paths and every saved source and output path before running the queue. Docker jobs use
container paths, so retaining the same mount paths avoids rewriting job inputs.

For the machine-readable output format, see [Job records and events](../job-record.md).
