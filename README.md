# VideoForge

An encode and mux job queue that runs in your browser, in the spirit of StaxRip. Queue a job or a
batch of episodes, and each runs end to end:

index → VapourSynth (crop, resize, filters) → x264 / x265 → audio → subtitles → MKV mux → validate

It runs as one local process (FastAPI + a Svelte app) on Windows, for one user. Jobs survive restarts,
and finished steps are skipped on a rerun.

> **Status:** pre-release (working towards 0.1.0 beta). Expect changes.

## Requirements

- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- Node.js (to build the web app)
- Tools, set in `videoforge.toml` (paths relative to it, or on `PATH`):
  - [MKVToolNix](https://mkvtoolnix.download/) (`mkvmerge`, `mkvpropedit`)
  - x264 and/or x265
  - VapourSynth plugins in `tools/vs-plugins` (bestsource, lsmas or ffms2, plus any filters).
    VapourSynth itself and `vspipe` come with the `vapoursynth` Python package.
  - ffmpeg and MediaInfo
  - Optional, for audio encodes: [DeeZy](https://github.com/jessielw/DeeZy) with Dolby Encoding Engine
    and truehdd (DDP / Atmos), qaac (AAC), and opusenc (Opus)

## Quick start

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
`videoforge.toml`. Its tables are merged over the defaults.

Development: `uv run videoforge serve --no-browser`, then `cd frontend && npm run dev`
(http://localhost:5173, proxies `/api`). Tests: `uv run pytest -q` and `cd frontend && npm run check`.

## Profiles

A profile decides what goes into the output: which tracks, copy or encode, titles, flags, and the checks
on the finished file. VideoForge ships one, `manual`: every source track in source order, copied, and
you exclude, reorder, retitle and flag tracks yourself.

Other profiles (for example a release group's rules) are separate Python packages that register
under the `videoforge.profiles` entry point group. See [ARCHITECTURE.md](ARCHITECTURE.md).

## License

[MIT](LICENSE)
