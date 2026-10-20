# Windows portable

Use the portable ZIP to run VideoForge without a separate Python or Node.js installation.

## Install and launch

1. Download `VideoForge-<version>-windows-x64.zip` from
   [GitHub Releases](https://github.com/jessielw/VideoForge/releases).
2. Extract it to a folder where you can write files.
3. Add MKVToolNix and your encoder under `tools/`, or set their paths in **Settings**.
4. Run **VideoForge.exe** and check the tool status on **Settings**.

The ZIP includes Python, the built web app, VapourSynth plugins, `dovi_tool`, and `hdr10plus_tool`.
See [Tools and VapourSynth plugins](../configuration/tools.md) for the other paths and requirements.

!!! tip "Start with the tools you need"
    For a basic video encode with copied audio, start with MKVToolNix, x264 or x265, and the bundled
    source-filter plugin. DEE, qaac, and the other audio encoders are only needed for jobs that use them.

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
files and `videoforge.local.toml` if you use one. The queue, templates, and saved settings normally
live separately in `%APPDATA%\VideoForge`.

Back up that data folder before changing versions; see [Storage and backups](../configuration/storage.md).

## Build your own ZIP

From a source checkout with the [development prerequisites](source.md):

```powershell
uv run python scripts/build_portable.py
```

The result is written under `build/portable/`.

Next: [create your first job](first-job.md).
