# VideoForge

[Documentation](https://jessielw.github.io/VideoForge/) ·
[Getting started](https://jessielw.github.io/VideoForge/getting-started/) ·
[Releases](https://github.com/jessielw/VideoForge/releases)

An encode and mux job queue that runs in your browser, in the spirit of StaxRip. Queue a job or a
batch of episodes, and each runs end to end:

index → VapourSynth (crop, resize, filters) → x264 / x265 / VP8 / VP9 / SVT-AV1 → audio → subtitles → mux (MKV
or MP4) → validate

It runs as one local process (FastAPI + a Svelte app) for one user: on Windows (portable zip or from
source), or in Docker on Linux. Jobs survive restarts,
and finished steps are skipped on a rerun.

> **Status:** 0.1.0 EARLY beta. It works end to end, but expect changes. See [CHANGELOG.md](CHANGELOG.md).

Not yet: sources other than MKV, MP4 and M2TS / TS (remux them to MKV first), GPU filters, a login (see
[Docker](#docker-linux)), Dolby Vision 8.4 (HLG) (profile 8.1, a MEL and a FEL go into x265 encodes as 8.1, a
profile 5 as 5; a FEL's enhancement layer is baked into the picture).

## Requirements

The [Windows portable build](#portable-build-windows) and the [Docker image](#docker-linux) include
the application and free toolchain. DEE and Apple CoreAudioToolbox remain user supplied. From source:

- Windows or Linux; macOS and Linux ARM64 source setups are experimental and self-managed (see below)
- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- Node.js (to build the web app)
- The tools below. VapourSynth itself and `vspipe` come with the `vapoursynth` Python package, and
  MediaInfo with `pymediainfo`; nothing to install for those.

## Tools

The Windows portable release includes the free tools below. From a Windows source checkout,
`uv run python scripts/setup_windows.py` provisions them, their plugins and the frontend, then runs
media smoke checks. Only DEE and Apple CoreAudioToolbox remain user supplied for their optional encoders.

Tools live in `tools/` (git-ignored) as below. Point to custom installations elsewhere: in `videoforge.toml` /
`videoforge.local.toml`, or on the **Settings** page, which shows each path, checks it and reports what's
missing. A bare name (`ffmpeg`, `MP4Box`) is looked up on `PATH`.

| Tool | Default path | Needed for |
| --- | --- | --- |
| [MKVToolNix](https://mkvtoolnix.download/) | `tools/MKVToolNix/mkvmerge.exe` | reading sources, MKV output |
| x264, x265 | `tools/x264/x264.exe`, `tools/x265/x265.exe` | the video encode |
| SvtAv1EncApp (SVT-AV1) | `tools/SvtAv1EncApp/SvtAv1EncApp.exe` | AV1 encodes ([Patman86's builds](https://github.com/Patman86/SVT-AV1-Mods-by-Patman/releases), as StaxRip ships, or [SVT-AV1](https://gitlab.com/AOMediaCodec/SVT-AV1)'s own) |
| VapourSynth plugins | `tools/vs-plugins/` | source filters (FFMS2, the default; L-SMASH; BestSource) and any filters your scripts use: see [VapourSynth plugins](#vapoursynth-plugins) |
| [MP4Box](https://gpac.io/) (GPAC) | `tools/GPAC/mp4box.exe` | MP4 output |
| ffmpeg | `tools/ffmpeg/bin/ffmpeg.exe` | FLAC / Opus / AAC / AC-3 / E-AC-3 encodes, and decoding for the other audio encoders |
| ffprobe | next to ffmpeg | an MP4 / TS source's timing (track starts, frame rate); without it, MediaInfo's |
| [DeeZy](https://github.com/jessielw/DeeZy) + Dolby Encoding Engine | `tools/DeeZy/deezy.exe`, `tools/DEE/dee.exe` | DDP / DDP Atmos |
| truehdd | `tools/truehdd/truehdd.exe` | DDP Atmos from TrueHD Atmos |
| qaac | `tools/qaac/qaac64.exe` | AAC (Apple) |
| opus-tools | `tools/opus-tools/opusenc.exe` | Opus (opusenc) |
| [dovi_tool](https://github.com/quietvoid/dovi_tool), [hdr10plus_tool](https://github.com/quietvoid/hdr10plus_tool) | `tools/dovi_tool/dovi_tool.exe`, `tools/hdr10plus_tool/hdr10plus_tool.exe` | Dolby Vision and HDR10+ metadata (bundled; `scripts/fetch_tools.py` provisions all free Windows tools) |

The qaac frontend and its resampler are bundled; its Apple runtime is supplied separately in
`tools/qaac/QTfiles64/`. DeeZy is bundled; DEE and its license go in `tools/DEE/`. FFmpeg AAC needs neither.

Inspect the pinned inventory with `uv run python scripts/fetch_tools.py --list`. Fetch selected packages
with `--only x264 x265`, or recheck the complete toolchain with
`uv run python scripts/verify_toolchain.py --smoke`. Downloads and installed-file hashes are verified;
repeat provisioning repairs missing files and preserves unrelated files. `tools/THIRD_PARTY.md` records
versions, source/build links and licenses. See [toolchain maintenance](docs/development/toolchain.md).

## VapourSynth plugins

VideoForge bundles a set of plugins and filter scripts, listed in
[vsplugins/manifest.toml](vsplugins/manifest.toml) with the source and version of each: the portable build
and the Docker image have them. From source, `uv run python scripts/fetch_plugins.py` downloads the Windows
builds into `tools/vs-plugins/` and the single-file scripts into the `.venv`, and `uv sync --extra filters`
installs the packaged scripts.

| For | Plugins (`core.<namespace>`) and scripts |
| --- | --- |
| Source filters | BestSource (`bs`), L-SMASH-Works (`lsmas`), FFMS2 (`ffms2`), d2vsource (`d2v`) |
| Borders | EdgeFixer (`edgefixer`), FillBorders (`fb`), bore (`bore`), `awsmfunc.bbmod` (BalanceBorders) |
| IVTC, deinterlacing | VIVTC (`vivtc`), Bwdif (`bwdif`), znedi3 (`znedi3`), EEDI3m (`eedi3m`), `havsfunc.QTGMC` |
| Denoising | MVTools (`mv`), dfttest2 (`dfttest2_cpu`, through the `dfttest2` module), BM3D (`bm3d`), TTempSmooth (`ttmpsm`), FFT3DFilter (`fft3dfilter`), zsmooth (`zsmooth`), RemoveGrain (`rgvs`), `havsfunc.SMDegrain` |
| Debanding, resizing, formats | vszip (`vszip`: Deband, RFS, EEDI3, Bilateral, masks, ...), fmtconv (`fmtc`), descale (`descale`) |
| Sharpening, anti-aliasing | CAS (`cas`), SangNom (`sangnom`) |
| Misc | MiscFilters (`misc`), Deblock (`deblock`), AddGrain (`grain`), SubText (`sub`) |
| Python | havsfunc (r33), mvsfunc, awsmfunc, vsutil, vs-rekt, adjust, dfttest2 |

All run on the CPU (no GPU filters yet). VapourSynth R81 only loads API 4 plugins, so older ones
(TDeintMod, EEDI2, CTMF, DFTTest, neo_f3kdb, RemapFrames, nnedi3) are left out: dfttest2, vszip's Deband
and RFS, and znedi3 stand in. Plugins of your own go in `tools/vs-plugins/` (`/tools/vs-plugins` in Docker).

## Portable build (Windows)

Unpack `VideoForge-<version>-windows-x64.zip` and run `VideoForge.exe`. The application, Python,
frontend, free tools, VapourSynth plugins and Microsoft C++ runtime DLLs are included. The desktop window
uses Windows Edge WebView2; `videoforge.cmd serve` opens the browser instead. Optional DEE and its license
go in `tools/DEE/`; Apple's runtime for qaac goes in `tools/qaac/QTfiles64/`.

`videoforge.cmd` is the console entry point (`videoforge.cmd serve` shows the log;
`videoforge.cmd --help`). Build a release with `uv run python scripts/build_portable.py` (writes
`build/portable/`). The builder verifies the shipped runtime, indexing, preview decoding, video/audio
encoding and MKV/MP4 muxing before creating the ZIP.

## Docker (Linux)

The image (`ghcr.io/jessielw/videoforge`, amd64) carries the free tools: MKVToolNix, x264, x265, SVT-AV1, FFmpeg 9,
MP4Box, opus-tools, DeeZy, truehdd, dovi_tool, hdr10plus_tool, Wine (for Windows tools), and the [VapourSynth plugins](#vapoursynth-plugins),
built from source.
Start from [compose.yaml](compose.yaml): set your media folder, then `docker compose up -d` and open
http://127.0.0.1:8765.

- `/data`: the queue, templates, settings and logs. `/media` (or any folder you mount): sources and outputs;
  each job's work folder goes next to its source, so the mount must be writable.
- `/tools`: what the image can't ship. Restart the container after adding DEE or qaac.
  - Dolby Encoding Engine for DDP / Atmos: the Linux build as `/tools/dee/dee`, or the Windows build as
    `/tools/wine/dee/dee.exe` (run under Wine), with its license next to it. Linux build files need their
    execute bit (`chmod +x tools/dee/*`; copies over SMB and Unraid's New Permissions drop it).
  - qaac: `/tools/wine/qaac/qaac64.exe` with its `QTfiles64` folder, as on Windows (run under Wine).
  - More VapourSynth plugins (`.so`) in `/tools/vs-plugins`.
- The server listens on port 8765 in the container: publish it (`-p 127.0.0.1:8765:8765`; on Unraid, add a
  Port to the template, container port 8765). Without that, nothing outside the container reaches it.
- There's no login: publish the port on `127.0.0.1` as the compose file does, or put it behind your own
  proxy with authentication. Publishing it on the LAN (`-p 8765:8765`) lets anyone on it run jobs.
- Build it yourself with `docker build -t videoforge .` (on the published plugins image), or the plugins
  image too (FFmpeg, MP4Box, x264 and the plugins: half an hour or more): `docker build -t videoforge-plugins
  vsplugins`, then `docker build --build-arg PLUGINS_IMAGE=videoforge-plugins -t videoforge .`.

## Quick start (from source)

On Windows x64, install uv, Git and Node.js, clone the repo, then run:

```powershell
uv run python scripts/setup_windows.py
uv run videoforge serve --window
```

This installs the locked Python extras, builds the frontend and verifies the provisioned tools/plugins.
For Linux amd64, use Docker, or provide compatible tools/plugins and configure their paths yourself.
Linux ARM64 and macOS users can attempt a self-managed source installation with native tools and
plugins they install or compile. Packaged ARM/macOS support and multi-platform Docker work are deferred;
full feature parity is not validated. See the [macOS/ARM64 source guide](docs/getting-started/source.md#macos-and-arm64)
for architecture requirements, tool-path overrides, plugin loading and H.264/H.265 validation.
A manual source installation is:

```
git clone https://github.com/jessielw/VideoForge
cd VideoForge
uv sync
cd frontend && npm install && npm run build && cd ..
uv run videoforge serve          # http://127.0.0.1:8765, opens the browser
```

To drop files from Explorer onto path fields, run it in its own window instead (a browser never tells
a page where a dropped file lives): `uv sync --extra desktop`, then `uv run videoforge serve --window`
(pywebview; on Windows it uses Edge WebView2). Closing the window keeps VideoForge running in the tray
(encodes go on); Quit from the tray icon or Ctrl+C stops it, and starting it again brings up the running
one. Pasting paths (Explorer: Ctrl+Shift+C, then Ctrl+V on a field) works in the browser too.

Machine-specific settings (tool paths, default profile) go in `videoforge.local.toml` next to
`videoforge.toml`. Its tables are merged over the defaults. The Settings page's changes are kept in the
app's database and win over both.

Extra encoder, audio, and mux arguments use double quotes around values with spaces, for example
`--chapters "C:\My Clips\chapters.txt"`. Backslashes stay literal except before a double quote:
use `\"` for a literal quote and double trailing backslashes before a closing quote.
This syntax is the same on Windows and Linux; apostrophes and shell operators are literal.

## A short tour

- **New jobs:** add a source MKV, MP4 or M2TS (or a folder of episodes for a batch), plus subtitle files,
  chapters, or an existing encode to reuse. Each job starts on a template.
- **Queue:** the job list and each job's editor: **Video** (frame preview with zoom and crop overlay, auto
  crop, resize, filters, the generated VapourSynth script, which you can edit), **Encoder** (x264 / x265,
  VP8 / VP9 through ffmpeg, SVT-AV1; 1 or 2 passes), **Audio** and **Subtitles** (keep, leave out, reorder, retitle, flag; copy or encode
  each audio track, more than one output from one track), **Output** (folder, container, chapters, AutoQPF,
  label) and **Log**. Select several jobs to apply an edit or a template to all of them.
- **Templates:** a job's whole setup without a file: video, crop mode (keep, the template's crop, or detect
  per job), encoder, container, AutoQPF, and optionally audio and subtitles. Audio goes by position
  (slot n is the source's nth track) or by rules (language, original language, codec, channels,
  commentary / audio description), for a season whose track order shifts; subtitles go by rules
  (language, format, forced / SDH / commentary). Star one as the default for new jobs.
- **Batch index:** Index on the Queue toolbar indexes the selected jobs (or all) in the background while
  encodes run; a job whose source is on the disk an encode is reading waits, and jobs on other disks go
  first (Settings). The preview only opens indexed sources, so opening a job never reads a whole remux.
- **Job label** (Output tab): added to the output name, `<name>.<label>.mkv`, to tell runs of one source
  apart (dubbed / subbed).
- **Log:** everything the jobs printed since the page opened, all jobs or one.
- **Settings:** tool paths with a check for each, folder browser roots, the disk wait, and Shut down.

## Where things are written

- **Next to the source, `<source>_tmp/`:** the source's work folder: the index at its top, and a folder per
  job (`main/`, or the job's label) with its `video.vpy`, the encodes, `videoforge.log` (every run and index
  of the job, with times and tool output), and per output
  `<output name>.videoforge.json` (how it was made: settings, script, each track and the source track it
  came from, commands, tool versions) and `<output name>.videoforge.jsonl` (live events). The format is in
  [docs/job-record.md](docs/job-record.md), for tools that read it. It stays after the job, so a rerun reuses
  the encodes: `finished-steps.json` notes which files are finished, and Start queue / Run selected ask which
  of them (the video, each audio encode) to reuse and which to make again. To clean up: Settings → Work folders deletes a job's folder once it's done (the records and log
  are copied to `records/` in the data folder first), or remove jobs with Remove → "Remove and delete work
  folders".
- **The output folder:** the finished file (written as `<output>.partial`, validated before publishing).
  Existing unmanaged files default to Stop; Output offers Skip, Rename or Replace. Rejected candidates
  are kept with an `.unpublished-<id>` name for inspection.
- **The data folder, `%APPDATA%\VideoForge`** (or `--data-dir`): `videoforge.db` (the queue, templates,
  settings), `logs/` (an app log per session, the newest 50 kept, and `events.jsonl` with every job's
  events) and `records/` (the job records and logs of deleted work folders, the newest 100 kept).

## Profiles

A profile decides what goes into the output: which tracks, copy or encode, titles, flags, and the checks
on the finished file. VideoForge ships one, `manual`: every source track in source order, copied, and
you exclude, reorder, retitle and flag tracks yourself (or let a template's rules do it).

Other profiles (for example a release group's rules) are separate Python packages that register
under the `videoforge.profiles` entry point group. See [ARCHITECTURE.md](ARCHITECTURE.md).

## Development

Documentation uses Zensical: `uv run --only-group docs --frozen zensical serve` previews it at
http://localhost:8000; `uv run --only-group docs --frozen zensical build --clean --strict` builds it.
See [Documentation and releases](docs/development/documentation.md) for the GitHub Pages workflow.

`uv run videoforge serve --no-browser`, then `cd frontend && npm run dev` (http://localhost:5173, proxies
`/api`). Tests: `uv run pytest -q` and `cd frontend && npm run check`. Checks: `uv run poe typecheck`
(basedpyright, standard, `src`), `uv run poe lint` (ruff), and `uv run poe format` (ruff fixes, then
`ruff format`); `poe lint-fix`, `poe format-check` too. How it's built: [ARCHITECTURE.md](ARCHITECTURE.md).

## License

[MIT](LICENSE)
