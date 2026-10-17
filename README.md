# VideoForge

An encode and mux job queue that runs in your browser, in the spirit of StaxRip. Queue a job or a
batch of episodes, and each runs end to end:

index → VapourSynth (crop, resize, filters) → x264 / x265 → audio → subtitles → mux (MKV or MP4) → validate

It runs as one local process (FastAPI + a Svelte app) for one user: on Windows (portable zip or from
source), or in Docker on Linux. Jobs survive restarts,
and finished steps are skipped on a rerun.

> **Status:** 0.1.0 beta. It works end to end, but expect changes. See [CHANGELOG.md](CHANGELOG.md).

Not yet: sources other than MKV (remux an MP4 or M2TS to MKV first), GPU filters, a login (see
[Docker](#docker-linux)).

## Requirements

The [portable build](#portable-build-windows) and the [Docker image](#docker-linux) carry everything but
the tools. From source:

- Windows (or Linux), Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- Node.js (to build the web app)
- The tools below. VapourSynth itself and `vspipe` come with the `vapoursynth` Python package, and
  MediaInfo with `pymediainfo`; nothing to install for those.

## Tools

Put the tools in `tools/` (git-ignored) as below, or point to them elsewhere: in `videoforge.toml` /
`videoforge.local.toml`, or on the **Settings** page, which shows each path, checks it and reports what's
missing. A bare name (`ffmpeg`, `MP4Box`) is looked up on `PATH`.

| Tool | Default path | Needed for |
| --- | --- | --- |
| [MKVToolNix](https://mkvtoolnix.download/) | `tools/MKVToolNix/mkvmerge.exe` | reading sources, MKV output |
| x264, x265 | `tools/x264/x264.exe`, `tools/x265/x265.exe` | the video encode |
| VapourSynth plugins | `tools/vs-plugins/` | source filters (FFMS2, the default; L-SMASH; BestSource) and any filters your scripts use: see [VapourSynth plugins](#vapoursynth-plugins) |
| [MP4Box](https://gpac.io/) (GPAC) | `MP4Box` on `PATH` | MP4 output |
| ffmpeg | `ffmpeg` on `PATH` | FLAC / Opus / AAC / AC-3 / E-AC-3 encodes, and decoding for the other audio encoders |
| [DeeZy](https://github.com/jessielw/DeeZy) + Dolby Encoding Engine | `tools/DeeZy/deezy.exe`, `tools/DEE/dee.exe` | DDP / DDP Atmos |
| truehdd | `tools/truehdd/truehdd.exe` | DDP Atmos from TrueHD Atmos |
| qaac | `tools/qaac/qaac64.exe` | AAC (Apple) |
| opus-tools | `tools/opus-tools/opusenc.exe` | Opus (opusenc) |

Only MKVToolNix, an encoder and the source filter plugin are needed to start; the audio tools are only
needed for the encodes that use them (copying a track needs none).

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

Unpack `VideoForge-<version>-windows-x64.zip` anywhere, put the tools in its `tools/` (or set their paths on
the Settings page; the VapourSynth plugins are already in `tools/vs-plugins/`), and run `VideoForge.exe`: VideoForge in its own window, with a tray icon. It carries its
own Python, so nothing else is installed. `videoforge.cmd` is the console way in (`videoforge.cmd serve` shows
the log; `videoforge.cmd --help`). Build it yourself with `uv run python scripts/build_portable.py` (writes
`build/portable/`).

## Docker (Linux)

The image (`ghcr.io/jessielw/videoforge`, amd64) carries the free tools: MKVToolNix, x264, x265, FFmpeg 9,
MP4Box, opus-tools, DeeZy, truehdd, Wine (for Windows tools), and the [VapourSynth plugins](#vapoursynth-plugins),
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

## A short tour

- **New jobs:** add a source MKV (or a folder of episodes for a batch), plus subtitle files, chapters, or an
  existing encode to reuse. Each job starts on a template.
- **Queue:** the job list and each job's editor: **Video** (frame preview with zoom and crop overlay, auto
  crop, resize, filters, the generated VapourSynth script, which you can edit), **Encoder** (x264 / x265,
  1 or 2 passes), **Audio** and **Subtitles** (keep, leave out, reorder, retitle, flag; copy or encode
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

- **Next to the source, `<source>_tmp/`:** the job's work folder: the index, `video.vpy`, the encodes,
  `videoforge.log` (every run and index of this source, with times and tool output), and per output
  `<output name>.videoforge.json` (how it was made: settings, script, each track and the source track it
  came from, commands, tool versions) and `<output name>.videoforge.jsonl` (live events). The format is in
  [docs/job-record.md](docs/job-record.md), for tools that read it.
- **The output folder:** the finished file (written as `<output>.partial`, renamed when the mux is done).
- **The data folder, `%APPDATA%\VideoForge`** (or `--data-dir`): `videoforge.db` (the queue, templates,
  settings) and `logs/` (an app log per session, the newest 50 kept, and `events.jsonl` with every job's
  events).

## Profiles

A profile decides what goes into the output: which tracks, copy or encode, titles, flags, and the checks
on the finished file. VideoForge ships one, `manual`: every source track in source order, copied, and
you exclude, reorder, retitle and flag tracks yourself (or let a template's rules do it).

Other profiles (for example a release group's rules) are separate Python packages that register
under the `videoforge.profiles` entry point group. See [ARCHITECTURE.md](ARCHITECTURE.md).

## Development

`uv run videoforge serve --no-browser`, then `cd frontend && npm run dev` (http://localhost:5173, proxies
`/api`). Tests: `uv run pytest -q` and `cd frontend && npm run check`. Checks: `uv run poe typecheck`
(basedpyright, standard, `src`), `uv run poe lint` (ruff), and `uv run poe format` (ruff fixes, then
`ruff format`); `poe lint-fix`, `poe format-check` too. How it's built: [ARCHITECTURE.md](ARCHITECTURE.md).

## License

[MIT](LICENSE)
