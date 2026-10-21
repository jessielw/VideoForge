# From source

Install **Python 3.12+**, [uv](https://docs.astral.sh/uv/), Git, and Node.js. The repository's CI
uses Node.js 22. You also need the [media tools](../configuration/tools.md) for the jobs you run.

## Install

```sh
git clone https://github.com/jessielw/VideoForge.git
cd VideoForge
```

VapourSynth and `vspipe` come with the Python dependency; MediaInfo comes with `pymediainfo`.
On Windows x64, run the complete setup from the checkout:

```powershell
uv run python scripts/setup_windows.py
```

This installs the desktop and filter extras, fetches pinned tools and companion libraries, builds the
frontend, and verifies indexing, preview decoding, video/audio encoding and MKV/MP4 muxing. Repeat runs
reuse checksummed downloads and repair missing tool files. Use `--skip-frontend` to retain an existing build.
Only DEE and Apple's CoreAudioToolbox remain user supplied for their optional encoders.

For individual components or an inventory, see [Tools](../configuration/tools.md).
The native provisioners support Windows x64. For Linux, use the [Docker image](docker.md), or supply
compatible Linux tools and plugins yourself. Native macOS provisioning is not provided.

For a manual source installation with tools you provide, install Python dependencies and the frontend:

```sh
uv sync
cd frontend
npm ci
npm run build
cd ..
```

## Run in the browser

```sh
uv run videoforge serve
```

This opens [http://127.0.0.1:8765](http://127.0.0.1:8765). Open **Settings**, check the tool paths,
and follow [Your first job](first-job.md).

## Run in a desktop window

```sh
uv sync --extra desktop
uv run videoforge serve --window
```

The desktop window supports dropping local files onto path fields. On Windows it uses Edge WebView2.
Closing it keeps the application in the tray; choose **Quit** there, or press **Ctrl+C** in the terminal,
to stop it. Starting it again brings up the existing instance.

A browser does not reveal the full paths of dropped files. In the browser, paste a path instead:
in Explorer use **Ctrl+Shift+C**, then **Ctrl+V** in the path field.

## Local settings

Put machine-specific paths in `videoforge.local.toml` beside `videoforge.toml`:

```toml
[tools]
mkvmerge = 'D:\Tools\MKVToolNix\mkvmerge.exe'
x265 = 'D:\Tools\x265\x265.exe'
```

Saved changes from **Settings** take precedence over both files. See
[Settings and configuration files](../configuration/settings.md).

For frontend hot reload and code checks, see [Contributing](../development/contributing.md).
