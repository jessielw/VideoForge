# VideoForge architecture

StaxRip in a browser for one user: queue a job (or a batch of episodes), and each
one runs a pipeline end to end: index, VapourSynth script (crop, resize,
filters), video encode, audio, subtitles, mux, validate. A group's rules live in a
profile: the built-in `manual` profile (no rules; the user sets up each
track), or a group's profile installed as its own package. Runs as one local process (FastAPI + a built Svelte
app): on Windows (portable zip or from source), or in Docker on Linux.

## Layout

```
src/videoforge/
  core/                  The engine. Imports no web framework and no profile (a test enforces it).
    models.py            Tracks, Plan (the rules' output), Overrides, Issue
    probe.py, classify.py, lang.py, mediainfo_text.py, pairing.py
    config.py            Tool paths (mkvmerge, x264, x265, vspipe, VS plugin folder, ...); mkvpropedit / mkvextract
                         found next to mkvmerge and ffprobe next to ffmpeg unless set
    arguments.py         Extra tool arguments: Windows double-quote/backslash rules on every platform,
                         passed as argv without a shell; apostrophes are literal, unclosed double quotes rejected
    profile.py           Profile ABC: plan rules, checks, track properties, video defaults
    jobs.py              probe_inputs / plan_job
    job.py               JobSpec (what to build, persisted) + JobState (runtime, persisted)
    template.py          Template: a job's whole run (video, crop mode, encoder, audio by position or rules,
                         subtitle rules, container, AutoQPF); apply() to a spec, apply_audio() / apply_subs() once the
                         source's tracks are known
    plan_io.py           Type-driven JSON codec for every model
    disks.py             Which physical disk a path is on (the index lane waits for an encode on its disk)
    workdir.py           <source>_tmp/ per job: indexes, script, encodes, stats, logs; keep_records copies a
                         folder's records and log to <data dir>/records before it's deleted
    record.py            What a run did, for other tools: <output>.videoforge.json + .jsonl events (docs/job-record.md)
    events.py            EventBus: JobStarted / JobFinished / QueueFinished / IndexFinished, emitted by the queue,
                         for notifications, actions and plugins (each subscriber hands slow work to its own thread)
    notify.py            Notifications (Apprise), a bus subscriber
    actions.py           Actions (docs/actions.md): command / move / copy / webhook after a job or the queue, a bus subscriber
    video/
      settings.py        VideoSettings (source filter, crop, resize, filters, custom script), EncoderSettings
      script.py          VideoSettings -> .vpy text (one generator for preview and encode)
      vs.py              VapourSynth: plugin path, clip cache, info, RGB frames (run in the preview worker)
      preview.py         The preview worker: a child process holding the clips; JSON over stdin/stdout
      ffindex.py         FFMS2's index with progress, through the plugin's own ffms2.dll (ctypes)
      crop.py            Auto-crop detection (RGB lightness on sampled lines, read straight from YUV)
      encoders.py        x264 / x265, VP8 / VP9 (ffmpeg's libvpx, into an IVF), SVT-AV1 (SvtAv1EncApp, into an
                         IVF): settings -> argv (1 or 2 pass), progress parsing (fraction, fps, the encoder's eta);
                         a VP8 / VP9 / SVT-AV1 job's issues
      color.py           The source's colour (MediaInfo -> VideoInfo.color) -> --colorprim/--transfer/... and
                         x265's HDR10 SEI with StaxRip's --repeat-headers --hrd --aud (and the VBV from --level-idc),
                         before the job's options (vspipe's y4m carries no colour; a --no- option turns one off);
                         ffmpeg's -color_* for VP8 / VP9, SvtAv1EncApp's H.273 codes and HDR10 (in plain
                         numbers), and the H.273 codes (AV1's HDR10 too) the mux tags their container with
                         (effective_container_color resolves defaults, options, and extra arguments in encoder
                         order; unknown overrides clear the corresponding source tag)
      hdr.py             Dolby Vision / HDR10+ in the source (MediaInfo -> VideoInfo.hdr; FEL or MEL from a second
                         of the RPU); HDR10+ into x265 (hdr10plus_tool's JSON, --dhdr10-info) and Dolby Vision
                         as 8.1, or a profile 5 as 5 (dovi_tool's RPU, its L5 moved by the crop and resize); a
                         FEL's enhancement layer (demux, MKV) and its HDR10 values from the RPU; their frame checks
      qpf.py             AutoQPF: chapters -> qpf + chapter file
      vfr.py             A VFR source's timestamps (mkvextract timestamps_v2) onto an MKV's encode, while they fit
      remux.py           One track of an MP4 / TS source copied into an MKV (mkvmerge), for mkvextract
      burn.py            A subtitle track burned into the video (SubText's TextFile / ImageFile; a source track
                         extracted with the index); out of the mux (plan.burn)
      target.py          A 2-pass target size -> the video bitrate (StaxRip's Calc.GetVideoBitrate): what the size
                         leaves after the audio, subtitles, attachments, HDR metadata and overhead, over the length
      options.py         Each video encoder's option names from its own help (cached per executable): the
                         Encoder tab's suggestions, and video.option_unknown for a name it doesn't list
      starters.py        Starter encoder presets (x265 SDR / HDR10 / Dolby Vision, SVT-AV1), built in next to
                         each profile's defaults in every encoder preset picker (/api/presets)
    execute/             audio.py, mux.py, chapters.py, process.py (external tools, piping, cancel), jobobject.py (tools end with the server, Windows)
                         control.py: pause and priority for a tool and its children (Windows: a job of its own,
                         nested; POSIX: its process group); process.CancelToken holds a run's tools for them
                         mux.MUXERS: mkvmerge (MKV) and MP4Box (MP4), each with what its container can't hold
                         audio.ENCODES: every audio encode (DEE, qaac, opusenc, ffmpeg's FLAC/Opus/AAC/AC-3/E-AC-3)
                         with its layouts, bitrates and tools; planner, tool checks and UI all read it
                         loudness.py: an audio track's normalize measure (ffmpeg volumedetect / loudnorm pass 1),
                         run as `python -m`, writing what ffmpeg printed to JSON for the encode
    pipeline/
      steps.py           Step (command(s) or Python call), outputs, fingerprint
      build.py           JobSpec + Plan -> [index, qpf, video pass(es), audio, mux, validate]
      run.py             Run steps; skip a step whose fingerprint and outputs match (resume)
      reuse.py           A job's finished files by section (video, each audio), for the Reuse dialog
  plugins/               The plugin API (__init__: Plugin, PluginContext, the events; docs/plugins.md) and loader.py:
                         <data dir>/plugins/<id>/videoforge-plugin.toml + `videoforge.plugins` entry points, each
                         plugin run on its own thread off the bus
  profiles/              Registry: the `videoforge.profiles` entry points (id = "module:Class")
    manual.py            The built-in profile: every track in source order, copied; the user's
                         overrides exclude, reorder, retitle and flag tracks; output checked against the plan
  server/                FastAPI. The only place that knows about HTTP.
    app.py               create_app(): /api routers + the built frontend (SPA fallback)
    settings.py          Port, data folder, browsable roots
    store.py             SQLite (app data): jobs (spec + state JSON, order), presets (video, encoder, template)
    queue.py             The queue: one worker thread runs jobs in order; start/stop/cancel, pause/resume, priority;
                         the index lane (its own thread: work folder, script, source index; nothing else)
    events.py            Progress, log lines and job changes -> WebSocket /api/events
    routes/              fs (folder browser), jobs, media (probe), video (frames, crop, script),
                         profiles, presets
  applog.py              The app log (stdlib logging under "videoforge"): <data dir>/logs, a file per session
  cli.py                 `videoforge serve` (opens the browser), plus validate/plan/run
  desktop.py             `serve --window`: the app in a pywebview window with a tray icon (pystray; the `desktop`
                         extra), drops carry paths
frontend/                Svelte 5 + Vite + TypeScript + Tailwind -> frontend/dist (served by FastAPI)
scripts/build_portable.py  The portable zip (see "Portable build"); scripts/launcher/VideoForge.cs its launcher
scripts/fetch_plugins.py   The bundled VapourSynth plugins' Windows builds and filter scripts (vsplugins/manifest.toml)
vsplugins/               The bundled VapourSynth plugins: manifest.toml, the Docker plugins image (Dockerfile, build.py)
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
index ─► script info ─► qpf/chapters ─┬► video (vspipe | x264/x265/ffmpeg/SvtAv1EncApp, 1 or 2 passes) ─┬► mux ─► validate
                                      └► audio encodes (up to N at once) ────────────────────────────────┘
```

- Each step writes only into the job's `<source>_tmp/` (the mux writes `<out>.partial`). The folder stays
  after the run (a rerun reuses it) unless `AppConfig.delete_work_dir` is on: then the queue deletes a done
  job's folder (`JobQueue._clean_up`, after `keep_records`) before `JobFinished` goes out, so the event's
  record is the kept copy. Removing jobs can delete theirs too (`JobQueue.delete_work_dirs`).
- The output file (`JobQueue._refresh_outputs`, StaxRip's "The target file already exists"): after each
  replan, a removal and a run, the queue compares every planned job's output path (case-insensitive on
  Windows). Idle jobs sharing one are `outfile.shared` BLOCKs (a queued or running job keeps its file); a file
  already there that isn't the job's own last output is an `outfile.exists` WARN, looked at again only when
  that job is replanned. The runner also checks the destination before work and publication. Unmanaged
  existing outputs use JobSpec.output_policy (stop/skip/rename/replace); verified same-job results can
  be rerun. Mux finalization validates the candidate before replacing the destination, preserving a
  rejected or conflicted candidate under a unique unpublished name. New output publication refuses
  an existing target (Windows rename; POSIX hard link). A filesystem without that operation fails safely.
- The audio encodes are background steps (`Step.background`): `run_steps` starts them on up to
  `AppConfig.parallel_audio` threads (videoforge.toml `[pipeline]`, Settings → Audio encodes; default 2)
  once the index is done (it reads the whole source too), and goes on with the video. A step waits for
  the background steps whose outputs it reads (the mux), and one step failing cancels the others
  (a child `CancelToken`). With 0 they run one by one, before the video. Their lines reach the queue
  through `step_log`, tagged with their step, since several steps run at once.
- A background step that reads another's outputs waits for it on its own thread, and its `Step.refresh` and
  reuse check run there too, so the steps after it don't wait. Normalizing by peak or loudness uses this: an
  `audio.N.measure` step (`execute/loudness.py`, the encode's downmix then volumedetect or loudnorm's first
  pass) writes `audioN_<lang>.loudness.json`, and the encode `audio.N` refreshes from it (the gain, or
  loudnorm's second pass with the measured values, `linear=true`, and an `aresample` back to the source's rate,
  since loudnorm's dynamic mode puts out 192 kHz). dynaudnorm is one pass. DeeZy's encodes don't offer it.
- A step's fingerprint covers its command and inputs. A rerun skips a step whose
  fingerprint matches and whose outputs still match the size and modification time captured in its
  `StepRecord`. Records without output stamps rebuild unless the user explicitly adopts files verified
  by the work folder's completion manifest. Starting a replacement invalidates its manifest entries.
  That gives crash recovery (restart
  the server and the job resumes after its last finished step) and cheap reruns
  (change a subtitle flag and only the mux runs again).
- Reuse, StaxRip-like: each finished step's files are noted in `<work>/finished-steps.json` (step,
  fingerprint, size, mtime; `workdir.note_finished`), so any job on the source can find them (a rerun, a
  re-added job, another label). `pipeline/reuse.reuse_offers` lists a job's sections (the video, each audio
  encode) whose file is finished, and whether today's settings made it. Start queue / Run selected ask
  (`POST /api/queue/reuse`, the Reuse dialog) when there are any: ticked sections go to `JobState.keep`
  (`run_steps(keep=...)` reuses them whatever their fingerprint and records today's), unticked ones lose
  their records and are made again. The index, script, chapters and mux follow the rule above.
- An imported encode (e.g. from StaxRip) replaces the video steps.
- Frame rate (`core/video/info.py`): `script.info` (`vspipe --info video.vpy video.info.txt`, keyed by the script)
  reads the script's frames and frame rate, which an IVTC or a double-rate deinterlace makes other than the
  source's. The `chapters` (AutoQPF's frames) and `mux` steps (a raw encode's `--default-duration` / MP4Box
  `:fps=`) carry `Step.refresh` and take it when their turn comes, as StaxRip takes the script's rate; before a
  run (the commands shown) and for a variable rate, the source's. A script whose length (frames / fps) isn't the
  source's (MediaInfo's frame count x the frame duration) beyond 3 frames would put the source's audio,
  subtitles and chapters out of step: `length_warning` shows on the Video tab (the output clip's info) and the
  validate step adds it as a `video.length` WARN.
- Interlaced sources (`filters.field_issues`): the probe keeps MediaInfo's ScanType / ScanOrder
  (`VideoInfo.scan_type` / `scan_order`, as StaxRip shows them). Interlaced, MBAFF or PAFF with no enabled
  field step in the chain is a `video.interlaced` WARN (the field order in its message); a custom body isn't
  read. Some progressive video is flagged interlaced, so it only warns.
- Variable frame rate (`core/video/vfr.py`, StaxRip's Demux.vb / Muxer.vb): a source MediaInfo calls VFR
  (`VideoInfo.vfr`; its `default_duration_ns` is only the first frame's, and BestSource reports an averaged
  rate) gets a `timestamps` step into an MKV: `mkvextract timestamps_v2` writes `timestamps.txt` (one line per
  frame and the last one's end). A `timestamps.normalize` step subtracts the first timestamp from every
  entry, preserving intervals while using the same zero origin as the audio/subtitle shifts. The mux
  takes `--timestamps 0:<file>` instead of `--default-duration`
  (a reused encode too). The mux's refresh keeps them while they fit the script's frame count; a script that
  drops or adds frames (an IVTC) is muxed at its own rate, and `length_warning` says so (its length then checked
  against MediaInfo's duration). MP4Box takes no timestamps file: `mux.mp4_vfr` WARN.
- Burned-in subtitles (`core/video/burn.py`, StaxRip's `Project.AddHardcodedSubtitleFilter`): a subtitle track's
  `TrackOverride.burn` (the track editor, or a template's subtitle rule: its first match) makes `plan_job` move
  it from `plan.subs` to `plan.burn`, whatever the profile chose (an encode only; one per job, a second marked
  one warns; a format SubText can't draw blocks). The script draws it in the body: text (`sub.TextFile`) after
  the crop step, as StaxRip; an image (`sub.ImageFile`) before it, since SubText scales the subtitle's canvas (the
  source frame) onto the clip; after a custom body; never at the `source` stage (auto crop). A source track gets
  a `burn.extract` step among the index steps (`mkvextract tracks` to `burn.<id>.<ext>` in the work folder), and
  `indexed()` waits for that file, so the preview (which opens only an indexed job) can draw it (from an MP4 or a
  TS, `burn.remux` copies the track into `burn.<id>.mks` first: see below). A nonzero timing offset also
  uses this remux for MKV tracks and identified external extracts, with `--sync` aligning subtitle
  timestamps to the decoded video's zero origin before extraction. Standalone added files stay as timed.
  Video steps fingerprint the rendered subtitle files (both `.idx` and `.sub` for VobSub); added files also
  contribute their size/mtime to a script comment, invalidating both generated scripts and preview clips
  after edits. The filter
  menu's `subtitle` category (after the crop) holds a plain `sub.TextFile` preset for a file typed in.
- Sources other than MKV (`pairing.SOURCE_EXTENSIONS`: MP4, M2TS / TS), read straight from the file as StaxRip
  does (its source filters open them; it demuxes audio with ffmpeg or MP4Box, VideoForge's audio steps read the
  source with ffmpeg as for an MKV). `probe.py` joins mkvmerge and MediaInfo on the track number, which is the MP4
  track ID or the TS PID there (kept in `AudioTrack.number` / `SubTrack.number`). ffprobe (`Tools.ffprobe`, its
  stream headers) times these sources, joined on the number too (its `id`; two streams under a PID in mkvmerge's
  order): a track's delay to the video is its `start_time` less the video's (`AudioTrack.delay_ms`,
  `SubTrack.delay_ms`; a player's start: an MP4's edit lists applied, AAC priming at 0), a TS's video start
  (`VideoInfo.start_ms`) its offset to the earliest stream, and `default_duration_ns` its average frame rate
  (mkvmerge has none outside Matroska; a Blu-ray VC-1's `r_frame_rate` is the field rate). Without ffprobe:
  MediaInfo's frame rate (23.976 -> 24000/1001), Video_Delay, else an MP4 edit list's Source_Delay where MediaInfo
  lists it; an x264 TS then has no rate, so AutoQPF and the mux of a raw encode take the script's (`Step.refresh`).
  MediaInfo calls an x264 TS VFR (its timestamps go through the VFR path). mkvmerge keeps a TS's offset to its
  earliest stream, taken or not, but starts the earliest track it takes from an MP4 at 0: `mux._source_shift`
  syncs an MP4 input's tracks by that one's delay (`SourceInfo.container`, mkvmerge's type).
- Audio sync correction (StaxRip's audio Delay field): `TrackOverride.sync_ms` (+ later, - earlier) becomes
  `PlannedAudio.sync_ms` in `jobs.apply_sync`, after the profile's plan, so every profile gets it. The mux adds
  it to whatever timing the track already gets (an MKV copy's `--sync`, an encode's delay, MP4Box `:delay=`);
  the audio encode's fingerprint doesn't change. A track more than 2 s off the video (its delay plus the
  correction, StaxRip's threshold) is an `audio.delay` WARN.
  A Blu-ray TrueHD PID's AC-3 core is a track of its own in mkvmerge (and ffmpeg's `a:N`), under the same number;
  MediaInfo's one track is the TrueHD's, so the core takes mkvmerge's details (`AudioTrack.core`). MP4Box takes a
  TS track by PID, an MP4's by track ID (`mux._mp4_track`), and can't copy a core apart (`mux.mp4_core` BLOCK).
  mkvextract reads Matroska only: `build.mkvextract_input` puts a `burn.remux` / `timestamps.remux` step
  (`core/video/remux.py`, mkvmerge with the one track) before `burn.extract` / `timestamps`; mkvmerge keeps a TS's
  offset to its earliest stream, as the mux does. AutoQPF can't read a TS's program menu (a menu with no
  chapters): `qpf.make_qpf` writes chapters every 5% of MediaInfo's runtime and has AutoQPF read that file.
- VP8 / VP9 (`core/video/encoders.py` `ffmpeg_command`): vspipe's y4m into `ffmpeg -c:v libvpx[-vp9] ... -f ivf
  video.ivf`. The IVF is timed by the y4m's frame rate, so both muxers take it as a container (no fps); it holds
  no pixel aspect and little colour (VP9: the matrix and range), so `build_steps` passes the encode's `sar` and
  `color.container_codes` to the muxer (`--aspect-ratio-factor`, `--colour-*`; MP4Box `:par`, `:colr=nclx`).
  ffmpeg runs VP8's `-crf` as constrained quality only and takes `-b:v 0` as its 256 kbit/s default, so VP8's
  CRF sends `-b:v 100M` (`VP8_CRF_CAP`, a ceiling a 1080p sample didn't reach); VP9 keeps StaxRip's `-b:v 0`.
  ffmpeg names its 2-pass log `<passlogfile>-0.log` (`encoders.stats_path`). There's no qpfile: the encode step
  refreshes when its turn comes and forces the qpfile's frames as keyframes (`-force_key_frames expr:`). A pipe
  from vspipe gets the encoder priority (`process.run`), so ffmpeg's audio encodes keep the tool priority.
- SVT-AV1 (`encoders.svtav1_command`): vspipe's y4m into `SvtAv1EncApp --input - ... --output video.ivf`, an IVF
  as VP8 / VP9's (`Encoder.ivf`). The encode step refreshes when its turn comes: SvtAv1EncApp gets the script's
  frames (`--frames`, from the info step, as StaxRip passes them: it doesn't know a pipe's length) and,
  in CRF, the qpfile's frames as `--force-key-frames Nf,...` (`encoders.forces_keyframes`; with `--rc 1` it
  refuses them). Two passes get `--undershoot-pct 5` (`SVTAV1_UNDERSHOOT`) unless the job's options or extra
  arguments set it: SvtAv1EncApp's 25 lands 26-33% under `--tbr` on Fallout, 5 within 5.5%. `color._svtav1_args` writes H.273 code points, AV1's chroma position (type 0 -> 1, type 2 -> 2)
  and x265's mastering display units as plain numbers (`color.mastering`). The AV1 stream holds the colour and
  HDR10, but mkvmerge copies none of it to the track, so `container_codes(..., hdr10=True)` tags it
  (`--colour-*`, `--chromaticity-coordinates`, `--max-luminance`, `--max-content-light`, ...); MP4Box writes the
  colr, mdcv and clli boxes from the stream, so an AV1 encode's HDR10 leaves `:hdr=none` out. `--progress 2`'s
  lines ("Encoding: n/total Frames @ x fps|fpm ... [-h:mm:ss]", ANSI colours stripped by `process`) give the
  fraction, fps and time left.
- HDR10+ (`core/video/hdr.py`, x265 with "HDR10+ from the source" on): before the video, `hdr10plus`
  (`ffmpeg ... -f hevc - | hdr10plus_tool extract`, StaxRip's command) writes `hdr10plus.json` to the work
  folder and `hdr10plus.check` compares its frames with the script's (`vspipe --info`): a trim, a frame-rate
  filter or a source filter counting frames its own way would put the metadata out of step, so the job stops
  there. x265 gets `--dhdr10-info`; the validate step blocks an output MediaInfo finds no HDR10+ in. MP4Box
  adds the video with `:hdr=none` (no HDR boxes: the stream's SEI carries it, and MediaInfo would list it
  twice). x264 drops it (a warning); 8-bit blocks.
- Dolby Vision (the same file; x265 with "Dolby Vision from the source" on; profile 8.1, a profile 7 MEL, or a
  profile 5, which stays profile 5: `hdr.dv_profile`):
  `dovi.rpu` (`ffmpeg ... | dovi_tool extract-rpu`) writes `dv_source.bin`; `dovi.edit` exports its L5 active
  area, moves each offset by the crop (at least 0) and scales it by the resize in the chain's order (DoviCrop's
  logic, `l5_offsets`), and writes `dv_rpu.bin` with `dovi_tool editor` in mode 2 (8.1) or 0 (profile 5, as it
  is); keyed by the source size, crop, resize, their order and the profile. `dovi.check` compares the RPU's frames
  with the script's, as for HDR10+. x265 gets `--dolby-vision-profile 8.1` (or `5`) `--dolby-vision-rpu`; it needs
  VBV (HRD), 10-bit and (8.1) a mastering display, so the plan blocks without them, as it does for 8.4 (HLG), a
  profile 7 whose enhancement layer couldn't be read and a custom script body (its crop isn't known). Profile 5
  has no HDR10 layer (its base layer is IPTPQc2): x265 writes its own colour signalling for it, and an encode
  without its RPU warns (`hdr.dv_profile5`). mkvmerge and MP4Box write the DV configuration from the stream; the
  validate step blocks an output MediaInfo doesn't find the written profile in.
- A profile 7 FEL (`hdr.bakes_fel`) is baked: the index lane (`index_steps` with the source's video) adds
  `dovi.el` (`ffmpeg ... | dovi_tool demux --el-only` -> `dv_el.hevc`), `dovi.el_mkv` (mkvmerge with the
  source's default duration -> `dv_el.mkv`, so the source filter can seek it) and, for FFMS2, `dovi.el_index`
  (L-SMASH indexes both when the index step opens the script). The script's generated head bakes it right after
  `clip = src` (`script.bake_lines`, felbaker's `fel.Bake`: 16-bit in, 12-bit out, `_Range` set to limited), so
  the preview and the encode see the same picture; stage "source" (auto crop) leaves it out. BestSource blocks
  (it counts 2 frames fewer than FFMS2 / L-SMASH on the test file). The encode's HDR10 SEI comes from the RPU
  (`hdr.fel_color`: "RPU mastering display", then L1's MaxCLL / MaxFALL, else L6, else the source's): the
  encode steps carry `Step.refresh`, which `run_steps` calls when their turn comes, after `dovi.rpu` wrote the
  RPU; before that (the Encoder tab) they show the source's values.
- Target size (`core/video/target.py`, 2-pass with `EncoderSettings.target_mb`): StaxRip's sum, in decimal MB
  (its default prefix): the target less the audio (a copy's MediaInfo stream size, an encode's bitrate over the
  length, qaac TVBR by StaxRip's guess from its quality, FLAC by the lossless source's bitrate), the subtitles
  (their stream or file size, whole: mkvmerge doesn't compress them), an MKV's attachments, the HDR10+ JSON /
  Dolby Vision RPU and StaxRip's overhead per frame (0.014 KiB in MKV, 0.013 in MP4), over the script's length
  (a VFR MKV's: the source's). Both passes carry `Step.refresh`: pass 1 counts the planned sizes, and pass 2 has
  the encoded audio files among its inputs, so `run_steps` waits for those background steps and its bitrate
  counts their sizes (StaxRip corrects the bitrate once the audio is done). The plan blocks a size that leaves
  the video nothing (`video.target_small`) or a source without a length, and warns for tracks of unknown size.
- The plan is container-neutral: tracks carry plain flags (default, forced, hearing impaired,
  commentary, original, visual impaired), languages and titles. The job's container
  (`JobSpec.container()`: its `MuxSettings.container` when the profile lists it in `containers`,
  else `Profile.container`) picks the muxer (`execute/mux.py` `MUXERS`) and the output extension;
  the job's extra arguments go to that tool as typed.
  - The video gets the source video's language (`VideoInfo.language`).
  - mkvmerge writes every flag, and keeps the source's attachments (an ASS subtitle's fonts) and global tags.
  - MP4Box: language, title (handler name; MP4Box can't take ':' in it; the video's is empty, not
    GPAC's own), default = the enabled track of its alternate group, forced on timed text. Other
    flags warn, except an original flag carried from the source (most releases set it on every
    track: left out quietly); PGS/ASS/LPCM block.
    Chapters must be OGM text, so a chapter XML or the source's chapters are converted first.
    Source SRT tracks are extracted to `subtitle.<position>.srt` before import (`subs.<position>.extract`,
    with a remux for non-MKV sources or a timing shift). This avoids GPAC 2.4's MKV importer dropping the
    final cue's duration. The extract uses the decoded video's zero origin; the mux's local plan treats
    it as an external SRT with no additional delay. The original plan retains its source track identity.
  - The output check reads an MP4 for language, enabled (default) and format only. The language is
    compared as `lang.primary` (no region or script; nb / nn as no), since MP4Box writes a 3-letter
    ISO 639-2 code (`Muxer.carries_variants`); `mux.mp4_language` warns at plan time.

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

## Portable build

`scripts/build_portable.py` (Windows x64; the Release workflow runs it on a version tag and drafts a release):

```
VideoForge/
  VideoForge.exe         Launcher (C#, built with Windows' own csc.exe): runtime\pythonw.exe -m videoforge serve --window
  videoforge.cmd         The same with runtime\python.exe and the arguments given (console)
  runtime/               uv's standalone CPython with the locked dependencies (desktop extra) and VideoForge installed
  frontend/dist/         The built frontend
  videoforge.toml, tools/, README.md, CHANGELOG.md, LICENSE
```

- Both launchers set `VIDEOFORGE_ROOT` to the folder: `config.PROJECT_ROOT` (videoforge.toml, tools/, the frontend)
  is that instead of the checkout. The data folder stays `%APPDATA%\VideoForge`.
- A real Python, not a frozen app: vspipe embeds the Python registered by `vapoursynth config` (python.exe +
  python3xx.dll, the standard library as files), and the preview worker is `python -m`. `default_vspipe` also
  looks in the Python's scripts folder (`runtime\Scripts\vspipe.exe`), and `ensure_vspipe` registers python.exe
  when running under pythonw.exe.
- The VapourSynth plugins and filter scripts of `vsplugins/manifest.toml` are in it: `scripts/fetch_plugins.py`
  downloads each plugin's pinned Windows build (a PyPI wheel or a release archive, checked by sha256; .7z
  through 7-Zip's `7zr.exe`) into `tools/vs-plugins/`, and the single-file scripts (havsfunc, mvsfunc) into
  the runtime's site-packages; the packaged scripts are the `filters` extra. Other tools aren't bundled.
- The same layout works on macOS / Linux (standalone CPython and the vapoursynth wheel exist there) with a
  shell launcher.

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
- Docker (Linux, amd64): two images. `vsplugins/` builds the native half into `/opt/vf` (rarely: it's
  slow): FFmpeg 9 from source, then MP4Box (GPAC master, which builds against it and reads MKV through it),
  x264 (y4m input only) and the VapourSynth plugins of `vsplugins/manifest.toml` (`build.py`: one build recipe
  per plugin, a load test of each and of all together, and `runtime-packages.txt`, the Debian packages the
  binaries link to). L-SMASH-Works carries its own static FFmpeg (it doesn't build against 9 yet), kept to
  itself with `-Bsymbolic`. Zig plugins (zsmooth, vszip) are built per CPU level in a folder with a
  `manifest.vs`, so VapourSynth loads the best one. The `Dockerfile` (the app) copies `/opt/vf`, links its
  `vs-plugins/` as the vapoursynth package's autoloaded `plugins/`, builds x265 (8/10/12-bit, with HDR10+:
  Debian's has no `--dhdr10-info`), and adds Debian trixie's MKVToolNix and opus-tools, the DeeZy, truehdd,
  dovi_tool and hdr10plus_tool release binaries and the filter scripts. `docker.yml` tags the plugins
  image with a hash of `vsplugins/` and builds it only when that tag is new, then the app image on it (GHCR,
  on a version tag). `docker/videoforge.toml` is its config (`VIDEOFORGE_ROOT=/app`), data in `/data`, the
  user's tools in `/tools` (DEE, qaac, more plugins). The config names DEE and qaac bare (`dee`, `qaac`):
  `docker/entrypoint.sh` writes a launcher for each one in `/tools` to a folder on PATH (`/tools/dee/dee`,
  else `/tools/wine/dee/dee.exe`; `/tools/wine/qaac/qaac64.exe`), so a tool that isn't there shows as
  missing. Windows tools run under Debian's Wine (64-bit only; the DLLs stripped of debug info) through
  `docker/wine-run`: each user id gets its own prefix (Wine refuses one another user owns), copied from a
  template whose DLLs are links into Wine (16 MB, ~2 s the first time); the display drivers are off. Paths
  pass unchanged: Wine maps / to Z:, the current drive. On POSIX each tool runs in its own process group, so
  a cancel kills its children too (`process._kill_tree`), a pause stops them (SIGSTOP / SIGCONT) and a priority
  is the group's nice value (`execute/control.py`; the container runs as root, so raising one back works).
- VapourSynth R81 loads only API 4 plugins: the manifest leaves out the API 3 ones (TDeintMod, EEDI2, CTMF,
  DFTTest, neo_f3kdb, RemapFrames, nnedi3) for dfttest2, vszip and znedi3. R81 also takes a keyword's
  trailing underscore only (`lambda_`), so the fetch patches havsfunc r33's `_lambda` / `_global`. The
  Settings check of the plugins folder counts the vapoursynth package's own `plugins/` (the image's) too.
