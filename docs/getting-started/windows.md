# Windows portable

Use the portable ZIP to run VideoForge without a separate Python or Node.js installation.

## Install and launch

1. Download `VideoForge-<version>-windows-x64.zip` from
   [GitHub Releases](https://github.com/jessielw/VideoForge/releases).
2. Extract it to a folder where you can write files.
3. Run **VideoForge.exe** and check the tool status on **Settings**.

The ZIP includes Python, the built web app, VapourSynth and plugins, MKVToolNix, FFmpeg/ffprobe,
MP4Box, x264, x265, SVT-AV1, opusenc, DeeZy, truehdd, qaac's frontend, HDR metadata tools and
app-local Microsoft C++ runtime DLLs. See `tools/THIRD_PARTY.md` for versions, sources and licenses.

!!! tip "Optional user-supplied components"
    DDP / Atmos through DeeZy requires DEE and its license in `tools/DEE/`. Apple AAC through qaac
    requires Apple's CoreAudioToolbox in `tools/qaac/QTfiles64/`. FFmpeg AAC works without it.

The release builder runs indexing, preview, video/audio encoding and MKV/MP4 muxing checks before
creating the ZIP. Recheck an extracted release from its folder with:

```powershell
.\runtime\python.exe scripts\verify_toolchain.py --smoke
```

## Window, tray, and console

The desktop window accepts files dropped from Explorer onto path fields. Closing the window leaves
VideoForge running in the tray, including its active encodes. Choose **Quit** from the tray icon to
stop it. Starting VideoForge again brings the running window forward.

For a console session, open a terminal in the extracted folder:

```powershell
.\videoforge.cmd serve
```

To inspect the command line:

```powershell
.\videoforge.cmd --help
```

## Update

Stop VideoForge before updating. Extract a new release into a new folder and transfer your tool
user-supplied files (DEE, its license, Apple runtime, custom plugins) and `videoforge.local.toml`
if you use one. Keep the new release's bundled tools and notices. The queue, templates, and saved settings normally
live separately in `%APPDATA%\VideoForge`.

Back up that data folder before changing versions; see [Storage and backups](../configuration/storage.md).

## Build your own ZIP

From a source checkout with the [development prerequisites](source.md):

```powershell
uv run python scripts/build_portable.py
```

The result is written under `build/portable/`.

Next: [create your first job](first-job.md).
