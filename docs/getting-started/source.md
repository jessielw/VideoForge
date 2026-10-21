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
The native provisioners support Windows x64. For Linux amd64, use the [Docker image](docker.md), or supply
compatible Linux tools and plugins yourself. Linux ARM64 and macOS source setups are self-managed and
have not been validated end to end; see [macOS and ARM64](#macos-and-arm64) below. Packaged support and
multi-platform Docker images are deferred.

For a manual source installation with tools you provide, install Python dependencies and the frontend:

```sh
uv sync
cd frontend
npm ci
npm run build
cd ..
```

## macOS and ARM64

You can attempt a source installation with tools and plugins you install or compile yourself. This is
an experimental route, not a claim that every bundled Windows/Linux feature works on these platforms.
Use the browser interface; desktop-window behavior is not validated here.

### Choose compatible builds

Use one architecture for Python, VapourSynth and its native plugins: ARM64 on Apple Silicon or Linux
ARM64, or x86_64 for an Intel setup. Plugins must also target the host OS and VapourSynth API 4.
A Windows DLL or Linux `.so` cannot substitute for a macOS plugin. External tools must run on the host;
mixing architectures requires a separately configured and tested translation environment.

VapourSynth R81 publishes Python wheels for macOS 13+ on Intel and Apple Silicon, and for Linux ARM64
([release files](https://pypi.org/project/VapourSynth/81/#files)). After the manual installation above,
configure the checkout's Python and check its runtime:

```sh
uv run python -m vapoursynth config
uv run python -c "import platform, vapoursynth as vs; print(platform.machine()); print(vs.core)"
uv run vspipe --version
```

If a compatible wheel is unavailable for your OS/Python combination, follow the upstream
[VapourSynth build instructions](https://www.vapoursynth.com/doc/installation.html).
Keep the Python bindings and `vspipe` in the same environment used to run VideoForge.

### Install tools and compile the plugins you need

Start with MKVToolNix (`mkvmerge`, `mkvextract`, `mkvpropedit`), FFmpeg/ffprobe, x264, x265, and one source
plugin: FFMS2, BestSource or L-SMASH-Works. Select that source filter in the job's Video settings; FFMS2
is the default. Add other encoders, muxers and filters only when your jobs need them.

Use each project's native installation or build instructions. The
[plugin manifest](https://github.com/jessielw/VideoForge/blob/main/vsplugins/manifest.toml) records upstream
repositories, versions and namespaces, but its build options and downloads are not a macOS/ARM64 build
recipe. `vsplugins/build.py` and its Dockerfile currently assume Linux x86_64 in several places. The
Windows tool/plugin fetchers do not provision native macOS or ARM64 binaries.

Put your compiled plugins and their required companion files in a dedicated folder. Set `vs_plugins`
to that folder and override the Windows executable defaults in `videoforge.local.toml`, for example:

```toml
[tools]
mkvmerge = "mkvmerge"
mkvextract = "mkvextract"
mkvpropedit = "mkvpropedit"
ffmpeg = "ffmpeg"
ffprobe = "ffprobe"
x264 = "x264"
x265 = "x265"
vs_plugins = "/absolute/path/to/your/vs-plugins"
```

Bare executable names use `PATH`; absolute paths also work. Configure any additional tools your jobs
use in the same way. Changes saved in **Settings** take precedence over this file. Restart VideoForge
after changing plugins so the preview worker and new `vspipe` processes use the new libraries.

For packaged Python filter scripts, use `uv sync --extra filters`. To fetch only the pinned single-file
scripts (havsfunc and mvsfunc), without downloading Windows plugins, run:

```sh
uv run --extra filters python scripts/fetch_plugins.py --no-plugins
```

These scripts still require compatible native plugins for the functions you call. Some upstream
plugins need porting or have no compatible build; compiling the source does not guarantee feature parity.
Windows DEE/qaac executables also need a working compatibility layer and their user-supplied components;
Wine setup on macOS/ARM64 is not provided. Start with FFmpeg audio for the basic workflow.

### Verify your installation

1. Open **Settings** and check every tool used by the job. Plugin filenames appearing here do not prove
   that their libraries load.
2. Explicitly load each required plugin to expose architecture or dependency errors. For example,
   replace the path below with your FFMS2 library (use the actual filename from your build):

    ```sh
    uv run python -c "import vapoursynth as vs; vs.core.std.LoadPlugin('/absolute/path/to/plugin'); print(vs.core.ffms2.Source)"
    ```

    Use `vs.core.bs.VideoSource` for BestSource or `vs.core.lsmas.LWLibavSource` for L-SMASH-Works.
    See upstream [plugin loading](https://www.vapoursynth.com/doc/installation.html#plugin-autoloading).
3. Index a short source and open its preview. Keep its folder writable and use a separate output folder.
4. Complete an H.264 job and an H.265 job, including 10-bit HEVC if used, with FFmpeg audio and MKV output.
   Play the results and check the job logs. Validate MP4, HDR metadata and additional filters separately
   before relying on those features; basic HEVC does not establish HDR10+/Dolby Vision support.
5. Restart VideoForge and confirm saved jobs, paths and plugins still work before adding a batch.

The bundled `scripts/verify_toolchain.py` checks the Windows inventory; it is not a native macOS/ARM64
certification command. When reporting a source-install issue, include the OS, CPU architecture, Python
and VapourSynth versions, plugin/tool build versions, and the first failing command or job log.

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
