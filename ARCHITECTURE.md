# VideoForge architecture

StaxRip in a browser for one user: queue a job (or a batch of episodes), and each
one runs a pipeline end to end: index, VapourSynth script (crop, resize,
filters), video encode, audio, subtitles, mux, validate. A group's rules live in a
profile: the built-in `manual` profile (no rules; the user sets up each
track), or a group's profile installed as its own package. Runs as one local process on Windows (FastAPI + a built Svelte app);
the same server can later run in Docker.

## Layout

```
src/videoforge/
  core/                  The engine. Imports no web framework and no profile (a test enforces it).
    models.py            Tracks, Plan (the rules' output), Overrides, Issue
    probe.py, classify.py, lang.py, mediainfo_text.py, pairing.py
    config.py            Tool paths (mkvmerge, x264, x265, vspipe, VS plugin folder, ...)
    profile.py           Profile ABC: plan rules, checks, track properties, video defaults
    jobs.py              probe_inputs / plan_job
    job.py               JobSpec (what to build, persisted) + JobState (runtime, persisted)
    plan_io.py           Type-driven JSON codec for every model
    workdir.py           <source>_tmp/ per job: indexes, script, encodes, stats, logs
    history.py, fix.py   Finished-output records; fix mode
    video/
      settings.py        VideoSettings (source filter, crop, resize, filters, custom script), EncoderSettings
      script.py          VideoSettings -> .vpy text (one generator for preview and encode)
      vs.py              In-process VapourSynth: plugin path, clip cache, info, RGB frames
      crop.py            Auto-crop detection
      encoders.py        x264 / x265: settings -> argv (1 or 2 pass), progress parsing
      qpf.py             AutoQPF: chapters -> qpf + chapter file
    execute/             audio.py, mux.py, process.py (external tools, piping, cancel)
                         audio.ENCODES: every audio encode (DEE, qaac, opusenc, ffmpeg's FLAC/Opus/AAC/AC-3/E-AC-3)
                         with its layouts, bitrates and tools; planner, tool checks and UI all read it
    pipeline/
      steps.py           Step (command(s) or Python call), outputs, fingerprint
      build.py           JobSpec + Plan -> [index, qpf, video pass(es), audio, mux, validate]
      run.py             Run steps; skip a step whose fingerprint and outputs match (resume)
  profiles/              Registry: the `videoforge.profiles` entry points (id = "module:Class")
    manual.py            The built-in profile: every track in source order, copied; the user's
                         overrides exclude, reorder, retitle and flag tracks; output checked against the plan
  server/                FastAPI. The only place that knows about HTTP.
    app.py               create_app(): /api routers + the built frontend (SPA fallback)
    settings.py          Port, data folder, browsable roots
    store.py             SQLite (app data): jobs (spec + state JSON, order), presets
    queue.py             The queue: one worker thread runs jobs in order; start/stop/cancel
    events.py            Progress, log lines and job changes -> WebSocket /api/events
    routes/              fs (folder browser), jobs, media (probe), video (frames, crop, script),
                         profiles, presets, fix
  cli.py                 `videoforge serve` (opens the browser), plus validate/plan/run
frontend/                Svelte 5 + Vite + TypeScript + Tailwind -> frontend/dist (served by FastAPI)
legacy/qt_gui/           The archived PySide6 GUI and its tests. Reference only; not packaged.
tools/                   Binaries (gitignored): MKVToolNix, DEE, DeeZy, qaac, opus-tools, truehdd, x264, x265, vs-plugins
```

## The unit of work: a job

- **JobSpec** (persisted, edited in the UI): id, profile, inputs (source; an existing
  encode to reuse, optional; subtitles; chapters), original language, track
  overrides, VideoSettings, EncoderSettings, output folder.
- **Plan** (derived): what the profile's rules make of the probed inputs: audio
  actions, subtitle selection, titles and flags. Recomputed on every edit.
- **JobState** (persisted, written by the runner): status, current step, progress,
  per-step records (fingerprint, outputs, time), issues, output path, error.

A batch is one setup applied to many sources: each job gets its own copy of the
settings, and edits can be applied to several selected jobs at once.

## Pipeline

```
index ─► qpf/chapters ─► video (vspipe | x264/x265, 1 or 2 passes) ─► audio encodes ─► mux ─► validate
```

- Each step writes only into the job's `<source>_tmp/` (the mux writes `<out>.partial`).
- A step's fingerprint covers its command and inputs. A rerun skips a step whose
  fingerprint matches and whose outputs exist. That gives crash recovery (restart
  the server and the job resumes after its last finished step) and cheap reruns
  (change a subtitle flag and only the mux runs again).
- An imported encode (e.g. from StaxRip) replaces the video steps.
- The plan is container-neutral: tracks carry plain flags (default, forced, hearing impaired,
  commentary, original, visual impaired), languages and titles. The muxer the profile picks
  (`execute/mux.py` `MUXERS`, by `Profile.container`) maps them to its tool: mkvmerge track flags
  today; an MP4Box muxer would map them to its options (e.g. `:lang=`, `:name=`, `:kind=` roles
  such as commentary or description) and set the output extension.

## VapourSynth

- `vapoursynth` from PyPI (R81+) is self-contained: the core, `vspipe` and `vsrepo`
  come with the Python package. Plugins live in `tools/vs-plugins` and load through
  `VAPOURSYNTH_EXTRA_PLUGIN_PATH` (set for the server process and every vspipe run).
- One script generator serves both the preview (executed in-process, the clip
  cached by script text) and the encode (written to `<source>_tmp/video.vpy`, run by vspipe).
- Indexes go into the work folder (bestsource `cachepath`, lsmas/ffms2 `cachefile`),
  so preview and encode share them.

## Frontend

Pages: New jobs | Queue (job list + job editor tabs: Video, Encoder, Audio, Subtitles, Output, Log) |
Fix release | Log | Settings. The frame preview (zoom, pan, crop overlay,
auto-crop), the folder browser and the encoder option panels are ported from the
user's video-forge React app. Live updates come over one WebSocket.

UI kit: shadcn-svelte components (on bits-ui) in `frontend/src/lib/components/ui` (generated by the
shadcn-svelte CLI, `components.json`; `$lib` = `src/lib`), `@lucide/svelte` icons, `mode-watcher` for
light / dark / system (the toggle in the nav), `svelte-sonner` toasts (save errors, finished runs).
Theme tokens live in `src/app.css` (shadcn's names plus `success`, `warning`, `info`).

## Profiles

A profile decides what goes into the output (`core/profile.py`): the plan (tracks,
copy or encode, titles, flags, blocking issues), the container, whether added
subtitle files are used, the per-track properties the UI offers, video/encoder
defaults, audio encoder settings, and the checks on the finished file.

- **Discovery:** installed packages register under the `videoforge.profiles` entry
  point group; `videoforge.profiles.get_profile(id)` loads one. VideoForge's own
  `manual` is always present and is the default.
- **A group's profile** is a separate package, e.g.

  ```toml
  [project]
  dependencies = ["videoforge"]

  [project.entry-points."videoforge.profiles"]
  mygroup = "videoforge_mygroup:MyGroupProfile"
  ```

  VideoForge never imports it (a test enforces it). `profile = "mygroup"` in
  `videoforge.toml` (or `videoforge.local.toml`) makes it the default for new jobs.
- **Plan fields a profile fills in its own terms:** `Plan.resolution` (a size class
  or a plain size) and `PlannedSub.slot` (a category, "" for none).

## Decisions

- One user, one machine. No auth (binds to 127.0.0.1 by default).
- Jobs run one at a time; the queue survives restarts.
- The CLI isn't kept in step with new features (the server and core are the product).
- Docker later: Linux binaries for the toolchain; qaac needs a decision (Windows-only).
