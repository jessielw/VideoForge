# Troubleshooting

Start with the failed job's **Log** tab. For a problem before jobs run, inspect the application log
in the [data folder](../configuration/storage.md). Check **Settings** for missing or invalid tools.

## A tool is missing

Set the full executable path on **Settings** and run its check. A bare name only works if it is on
the application's `PATH`. Confirm that the tool matches the chosen encoder or container; MP4 needs
MP4Box, while MKV uses MKVToolNix.

The portable build does not include all external media tools. See
[Tools and VapourSynth plugins](../configuration/tools.md).

## Preview won't open

1. Select the job and use **Index** on the Queue toolbar.
2. Check the job log for source-reader errors or an index waiting for another job's disk.
3. Confirm the selected FFMS2, L-SMASH, or BestSource plugin is installed.
4. Disable the last added filter or correct the custom script, then check preview again.
5. If using BestSource, allow its first full-source decode to finish.

VapourSynth R81 needs API 4 plugins. An older API 3 plugin cannot be fixed by changing its path.
Use the supported replacement listed in the [bundled plugins](../configuration/tools.md#bundled-vapoursynth-plugins).

## Dropped files do not fill the path

Browsers do not reveal a dropped file's full local path. Use the desktop window, or copy the path
in Explorer with **Ctrl+Shift+C** and paste it into the field. From source, desktop mode is:

```sh
uv sync --extra desktop
uv run videoforge serve --window
```

## Docker cannot see a file or write a work folder

Use `/media/...` or another container mount path in the UI, rather than the host's path. Confirm
the volume is writable by the configured UID and GID. VideoForge creates `<source filename>_tmp/`
beside the source, even when the final output goes elsewhere.

## Docker is running but the page is unreachable

Confirm port **8765** is published. On Unraid, add the port mapping to the template. The supplied
Compose file binds to `127.0.0.1`, so the page is reachable from the Docker host; remote access
requires your own authenticated proxy and network configuration.

## The page says "Host is not allowed"

The server only answers the addresses it is told about. Set `VIDEOFORGE_ALLOW_HOST` to the hostname
or IP in your browser's address bar, without the port, such as `192.168.1.50`. On Unraid, add it as a
template **Variable**. See [Docker environment variables](../getting-started/docker.md#environment-variables).

## DEE or qaac is unavailable in Docker

Check the [required folder layout](../getting-started/docker.md#add-dee-or-qaac) and restart the
container after adding the tools. DEE needs its license beside it. Linux DEE needs executable
permission. Windows qaac needs its `QTfiles64` folder and is run through Wine.

## A job is blocked or skipped

Read its planning issues. Common causes include missing inputs, unsupported track/container
combinations, impossible audio layouts, unavailable tools, and HDR settings that the selected
encoder cannot satisfy. Correct the indicated setting before retrying.

## Output exists but the job is invalid

Muxing finished, but validation found a blocking difference from the plan. Read the output issues
and preserve the `.videoforge.json` record plus `videoforge.log` when investigating. Do not treat
file existence alone as a successful run.

## A rerun encodes again

Reuse requires completed files and matching saved step information. Changes to source inputs,
processing, encoder settings, or output identity can invalidate earlier work. Cleaning a work
folder deletes the intermediate encodes needed for reuse. An interrupted encode is incomplete
and starts again on rerun.

## A TOML change has no effect

Saved **Settings** values override file defaults for the server. Reset the affected UI setting
and restart after editing `videoforge.local.toml`. Confirm the file is beside the active
`videoforge.toml`; in Docker that is `/app/videoforge.local.toml`.

## Report a reproducible issue

Use [GitHub Issues](https://github.com/jessielw/VideoForge/issues) and include the VideoForge version,
installation type, source container and codecs, failing step, and the relevant log excerpt.
Remove private paths, notification URLs, webhook tokens, and license details before sharing.
