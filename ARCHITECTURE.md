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
    template.py          Template: a job's whole run (video, crop mode, encoder, audio by position or rules,
                         subtitle rules, container, AutoQPF); apply() to a spec, apply_audio() / apply_subs() once the
                         source's tracks are known
    plan_io.py           Type-driven JSON codec for every model
    disks.py             Which physical disk a path is on (the index lane waits for an encode on its disk)
    workdir.py           <source>_tmp/ per job: indexes, script, encodes, stats, logs
    history.py           Finished-output records (data dir; for the parked Fix release page)
    record.py            What a run did, for other tools: <output>.videoforge.json + .jsonl events (docs/job-record.md)
    video/
      settings.py        VideoSettings (source filter, crop, resize, filters, custom script), EncoderSettings
      script.py          VideoSettings -> .vpy text (one generator for preview and encode)
      vs.py              VapourSynth: plugin path, clip cache, info, RGB frames (run in the preview worker)
      preview.py         The preview worker: a child process holding the clips; JSON over stdin/stdout
      ffindex.py         FFMS2's index with progress, through the plugin's own ffms2.dll (ctypes)
      crop.py            Auto-crop detection (RGB lightness on sampled lines, read straight from YUV)
      encoders.py        x264 / x265: settings -> argv (1 or 2 pass), progress parsing
      qpf.py             AutoQPF: chapters -> qpf + chapter file
    execute/             audio.py, mux.py, chapters.py, process.py (external tools, piping, cancel), jobobject.py (tools end with the server, Windows)
                         mux.MUXERS: mkvmerge (MKV) and MP4Box (MP4), each with what its container can't hold
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
    store.py             SQLite (app data): jobs (spec + state JSON, order), presets (video, encoder, template)
    queue.py             The queue: one worker thread runs jobs in order; start/stop/cancel;
                         the index lane (its own thread: work folder, script, source index; nothing else)
    events.py            Progress, log lines and job changes -> WebSocket /api/events
    routes/              fs (folder browser), jobs, media (probe), video (frames, crop, script),
                         profiles, presets
  applog.py              The app log (stdlib logging under "videoforge"): <data dir>/logs, a file per session
  cli.py                 `videoforge serve` (opens the browser), plus validate/plan/run
  desktop.py             `serve --window`: the app in a pywebview window with a tray icon (pystray; the `desktop`
                         extra), drops carry paths
frontend/                Svelte 5 + Vite + TypeScript + Tailwind -> frontend/dist (served by FastAPI)
legacy/qt_gui/           The archived PySide6 GUI and its tests. Reference only; not packaged.
tools/                   Binaries (gitignored): MKVToolNix, DEE, DeeZy, qaac, opus-tools, truehdd, x264, x265, vs-plugins
                         (MP4Box and ffmpeg default to PATH; see README "Tools")
```

## The unit of work: a job

- **JobSpec** (persisted, edited in the UI): id, profile, inputs (source; an existing
  encode to reuse, optional; subtitles; chapters), original language, track
  overrides, VideoSettings, EncoderSettings, output folder, MuxSettings (container, extra muxer arguments).
- **Plan** (derived): what the profile's rules make of the probed inputs: audio
  actions, subtitle selection, titles and flags. Recomputed on every edit.
- **JobState** (persisted, written by the runner): status, current step, progress,
  per-step records (fingerprint, outputs, time), issues, output path, error.

A batch is one setup applied to many sources: each job gets its own copy of the
settings, and edits can be applied to several selected jobs at once.

## Templates

A template (`core/template.py`, StaxRip's idea) is the settings for a job's whole run, set up on the
Templates page without a file or saved from a job: VideoSettings, a crop mode (keep each job's / the
template's crop / detect it per job), EncoderSettings, MuxSettings, AutoQPF, and optionally audio and
subtitles. Each
profile's own defaults are a built-in template; the user can star one of theirs as a profile's default
(New jobs starts on it; `POST /api/jobs` with no settings gets it). Templates are applied when jobs are
added, to one job, or to a batch; a template applied after a job's own edits replaces them.

- **Auto crop:** `JobSpec.autocrop` is set; once the job is probed it waits in the index lane, which
  indexes the source and then runs the preview's auto-crop (status "cropping", not runnable meanwhile).
  A crop set by hand wins.
- **Audio, by position or by rules** (`TemplateAudio.mode`, source tracks only). By position: slot n
  is for the source's nth audio track (copy or an encode, title, flags, leave out, more outputs from
  the same track); slots past a source's tracks are ignored and tracks past the slots are kept or left
  out. By rules (`AudioRule`), for a season whose track order shifts: each track takes the first rule
  matching its language (as subtitles), the job's original language (or not), codec, channels (at
  least / at most) and traits (commentary / audio description by flag or title, `audio_traits`), and
  gets what a slot gives; an "only the first" rule goes to the first matching track and the others go
  on to the next rules. Kept tracks go in rule order (each followed by its more outputs), unmatched
  kept ones last, and one default at most (as subtitles). It waits in `JobSpec.audio_template` until
  the tracks are known, then becomes the job's track overrides (added audio files and subtitles keep
  theirs); for rules the profile's original-language guess is pinned first. Each output is fitted to
  its track (`fit_audio`): more channels than the track has -> the encode's default layout, DDP Atmos
  without an Atmos track -> DDP, and the bitrate goes back to the default with a changed layout or
  when the encode won't take it; the same settings set by hand still block. A job's Template menu
  saves its audio by position; replacing a template whose audio is by rules keeps them.
- **Subtitles, by rules:** position doesn't carry across sources, so subtitles are an ordered rule list
  (`TemplateSubs`): each track, source and added files alike, takes the first rule matching its language
  ("en" matches en-US, "es-419" only itself), format and traits (forced / SDH / commentary by flag or
  title, `sub_traits`), and is kept (title, flags) or left out; tracks no rule matches are kept or left
  out. Kept tracks go in rule order, and a default set by a rule goes to the first track it reaches
  (every other subtitle has it off). It waits in `JobSpec.subs_template` like the audio. Rules are made on
  the Templates page only; replacing a template from a job's menu keeps its rules.
- **Profiles without the track editor** choose tracks by their own rules: a template's audio and subtitles
  are dropped for their jobs (the queue's `_apply_tracks`), and the UI says so (Templates page notes, no
  "This job's audio too").

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
  commentary, original, visual impaired), languages and titles. The job's container
  (`JobSpec.container()`: its `MuxSettings.container` when the profile lists it in `containers`,
  else `Profile.container`) picks the muxer (`execute/mux.py` `MUXERS`) and the output extension;
  the job's extra arguments go to that tool as typed.
  - The video gets the source video's language (`VideoInfo.language`).
  - mkvmerge writes every flag.
  - MP4Box: language, title (handler name; MP4Box can't take ':' in it; the video's is empty, not
    GPAC's own), default = the enabled track of its alternate group, forced on timed text. Other
    flags warn, except an original flag carried from the source (most releases set it on every
    track: left out quietly); PGS/ASS/LPCM block.
    Chapters must be OGM text, so a chapter XML or the source's chapters are converted first.
  - The output check reads an MP4 for language, enabled (default) and format only.

## Logs and job records

- **App log** (`applog.py`): modules log through `logging.getLogger(__name__)`; `serve` calls `applog.setup()`:
  `<data dir>/logs/videoforge_<YYYY-mm-dd_HH-MM-SS>.log` (newest 50 kept, 10 MB per part) and the console,
  behind a QueueHandler/QueueListener. uvicorn runs with `log_config=None`, so its loggers land there too.
  Never fatal: an unwritable data folder means console only. Job tool output doesn't go here.
- **Work-folder text log** (`<source>_tmp/videoforge.log`, the queue's `_open_log`/`_log`): every run and
  index of the source, a time on each line, tool output prefixed `[x264]` etc., progress-only lines
  (indexers, mkvmerge) at every 10% (`steps._THIN_PROGRESS`; the progress bar still sees each one), and
  `Job record: ...` / `Job complete: <output>` at the end of a finished run.
- **Job record and events** (`core/record.py`, the public format in `docs/job-record.md`): the queue makes a
  `RunRecorder` per run (output from `build.job_output`): `<output name>.videoforge.jsonl` in the work folder
  gets run.started, step.started/finished (from on_step), run.finished; a run that writes the output writes
  `<output name>.videoforge.json` (source, output, video settings and script, each audio/subtitle output
  with the source track it came from, chapters, steps, issues, tool versions via `tools.versions`, cached
  per file and mtime). A failed run leaves the last record. The same events (and the index lane's
  index.started/finished) go to `<data dir>/logs/events.jsonl` (`JsonLines`, rolls at 10 MB). Writing them
  never fails a job.
- **Job label** (`JobSpec.label`, Output tab): `<stem>.<label>.<ext>` (`build.output_path`), so runs of one
  source (dubbed / subbed) are separate outputs with separate records.

## VapourSynth

- `vapoursynth` from PyPI (R81+) is self-contained: the core, `vspipe` and `vsrepo`
  come with the Python package. Plugins live in `tools/vs-plugins` and load through
  `VAPOURSYNTH_EXTRA_PLUGIN_PATH` (set for the server process, the preview worker and every vspipe run).
- One script generator serves both the preview (executed in the preview worker, a child process
  started on first use, one clip cached per job stage so a crop edit frees the old one; a crash or a
  request past its timeout costs only the worker, the next request starts a new one; it stops after
  5 idle minutes, handing its memory back; it is in the tool Job Object) and the encode (written to
  `<source>_tmp/video.vpy`, run by vspipe).
- Memory: the server process doesn't import numpy or VapourSynth (numpy's import alone commits
  ~30 MB per CPU thread for OpenBLAS; the worker runs with one BLAS thread). MediaInfo probes and
  AutoQPF run in the server; they measured flat over repeated probes and runs.
- Indexes go into the work folder (bestsource `cachepath`, lsmas/ffms2 `cachefile`),
  so preview and encode share them.

## Frontend

Pages: New jobs | Queue (job list + job editor tabs: Video, Encoder, Audio, Subtitles, Output, Log) |
Templates | Log | Settings. The frame preview (zoom, pan, crop overlay,
auto-crop), the folder browser and the encoder option panels are ported from the
user's video-forge React app. Live updates come over one WebSocket. The video editor's view
(preview/output/script, frame, zoom, scroll, edges, unsaved script text) is kept per job in memory
(`src/lib/videoView.svelte.ts`) until the job leaves the queue.

File paths: a page in a browser never learns a dropped file's path. In `serve --window` pywebview's
drop handler on the document gets the full paths and calls `window.videoforgeDropped(paths)`;
`window.videoforgeDesktop` tells the page drops work. Every path field uses `pathDrop`
(`src/lib/dropPaths.svelte.ts`): drops (in the window), pasted paths (one per line, quotes and file://
URIs undone; anywhere), checked by `POST /api/fs/kinds` (file, folder, missing, outside the roots)
against the field's rule. In a browser a drop shows a hint instead. Fields: New jobs slots, the track
editor's list (Audio/Subtitles), Output folder and Chapters on the Output tab.

The window (`serve --window`): pywebview owns the main thread, uvicorn runs in a thread, the pystray
icon detached (as in Reclaimerr). Closing hides the window (the service keeps running); the tray's Open
shows it, Quit asks while a job runs, then destroys the window. Ctrl+C quits too (a console handler marks
it quitting before pywebview's SIGINT handling closes the window). After the window loop ends, the
server's shutdown runs to the end (it cancels a running job, which stays cancelled). A second `serve`
finds the running one by `/api/health` and calls `POST /api/window/show` (or opens the browser).
Settings > Shut down (`POST /api/shutdown`) calls `app.state.shutdown`, which each mode sets: `serve`
stops its uvicorn server, the window quits as Quit does; the page then shows that VideoForge stopped.
The events WebSocket also reads, so a closed connection ends its handler and shutdowns don't wait on it.

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
- Batch index (Queue toolbar / batch panel): the index lane runs each job's `script` and `index` steps
  (`build.index_steps`), one job at a time, next to the encode queue. The index step is vspipe `--info`
  (L-SMASH, BestSource: their progress lines are read), or `core/video/ffindex.py` for FFMS2, whose
  Source() indexes silently: it builds the index through the plugin's ffms2.dll with a progress callback,
  keeps a valid one, and depends on the source alone (a crop edit doesn't index again). The steps are
  recorded in the job's steps, so the encode reuses them; the index step counts as done only while its
  index file is there (`script.index_exists`). Jobs waiting for a probe or an auto-crop wait their turn; a
  queued encode takes a job out of the lane. Only the lane indexes: the preview opens indexed sources only
  (409 otherwise), so opening a job never reads a whole remux. An unindexed job's Video tab is an index
  panel; its Index now puts the job first in the lane (`index(first=True)`), with progress there and in the
  header, and the job is locked (no edits) while it's being indexed. A template's auto crop waits in the
  lane too and runs after the index (`crop_pending`: not runnable meanwhile). `Entry.source_lock` is held
  by the lane (index and crop) and a preview request for a clip the worker doesn't hold yet. The lane's
  order is kept in the store (`index_lane` setting: the job being indexed first), so a restart goes on
  with it; a job stopped mid-index is indexed again (the indexers replace a broken index). Stopping the
  lane by hand empties it; a shutdown doesn't. Disks (Settings, on by default): a job whose source is on
  a disk the running encode reads (its source, work folder, output folder, reused encode) waits, and
  jobs on other disks go first; Index now on a job doesn't wait. `core/disks.py` finds the physical disk
  (Windows: the volume's disk numbers, so two partitions of one drive are one disk; a network path by
  its server; elsewhere `st_dev`). Queue toolbar: Select all, and Index (the selected jobs, or every job
  when none is selected) skips jobs already indexed.
- The CLI isn't kept in step with new features (the server and core are the product).
- Docker later: Linux binaries for the toolchain; qaac needs a decision (Windows-only).
