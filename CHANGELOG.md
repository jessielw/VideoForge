# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0-beta.1] - Unreleased

The first beta: an encode and mux job queue in the browser, for one user: on Windows (portable zip or from
source), or in Docker on Linux.

### Added

- `serve` reads its settings from `VIDEOFORGE_*` variables too (`VIDEOFORGE_ALLOW_HOST`,
  `VIDEOFORGE_ALLOW_ORIGIN`, `VIDEOFORGE_PLUGIN_MANAGEMENT`, `VIDEOFORGE_HOST`, `VIDEOFORGE_PORT`,
  `VIDEOFORGE_DATA_DIR`), so a Docker or Unraid template sets them without replacing the image's command.
  The image honors `PUID` / `PGID`, `UMASK` and `TZ`: started as root, it runs as that user (through gosu)
  and hands `/data` to it.

- Auto crop of a Dolby Vision source takes the bars from its RPU's L5 active area (DoviCrop's method), not
  only the luma: the detected borders stop short of a bar's soft edge (Godzilla Minus One: 274 where L5 says
  276 / 277). Per side the smallest bar of the presets in use (a varying-aspect film keeps every frame), rounded
  down to mod 2, checked against the detected borders (a side where the picture shows inside the bar takes the
  detected value). The index now extracts the RPU (the encode reuses it). The editor and the job log say where
  the crop came from.

- The job record keeps the encoder's closing statistics for the final pass (`video.encoder_summary`: x264 /
  x265's "frame I: ..." to "encoded N frames ..."), the block an NFO quotes. A run that reuses the encode keeps
  the earlier run's.

- A DDP or Atmos encode no longer fails when the job's folder is too deep for DEE (Windows' 259-character
  limit: a long source name in a deep folder). DeeZy then works in a short temp folder of its own.

- A standard-mode DDP 7.1 above 1024 kb/s blocks the plan (DEE makes it 1024): Blu-ray mode goes higher.

- DDP Blu-ray 7.1 reads as DDP, not AC-3: some MediaInfo builds report its AC-3 core and E-AC-3 dependent
  substream as AC-3 "Dep", which failed the output check of a job that made one.

- Job records state what the encode carried of the source's HDR (`video.hdr`): its Dolby Vision
  (profile, layers, FEL or MEL) and HDR10+, the profile the encode's Dolby Vision is written as, whether a
  FEL was baked in, and whether HDR10+ was kept. An NFO tool no longer has to read the log for it.

- A profile can set DeeZy's dialogue level (`AudioSettings.dialnorm`, `--custom-dialnorm`) for its DDP
  and Atmos encodes; a track's own Dialogue level still wins.

- x265's multi-pass analysis (`--multi-pass-opt-analysis` / `-distortion`) goes to `video.analysis` beside
  the two-pass stats (`--analysis-reuse-file`, as StaxRip does) instead of `x265_analysis.dat` in VideoForge's
  working directory; pass 2 waits for it like the stats.

- The FillBorders filter presets use `fillmargins` (StaxRip's mode) and list the other modes in a comment.

- **Duplicate** on the Queue copies the selected jobs, each right after its original with a label of
  its own, for a second output from the same source with a few settings changed. The copy reuses the
  source index and every encode whose settings it kept. Labels now show in the queue list and the
  job header, and search matches them.

- Each job keeps its files in its own folder in the source's work folder, named by its label
  (`main/` without one): its script, encodes, chapters, log and records. Files from the source alone
  (index, HDR metadata) stay shared at the top. A job whose encode would match another job's links
  that file into its folder instead of encoding again. Actions get `{job_dir}`, and records a
  `job_dir` field. Work folders made before this keep their files, but jobs encode again once.

- Audio and video encoder preset pickers show **My presets** and custom folders first across all
  encoders. Search spans folders and encoders, with an optional encoder filter. The same browser
  is available in preset managers, including Settings.

- Audio **Delay** fields show the total delay, initially filled with the detected source delay.
  Entering zero cancels that delay; clearing the field restores it. Existing saved corrections
  retain their timing.

- DDP mode selection for DeeZy: Standard (default) or Blu-ray, retained in audio presets and
  templates. Blu-ray uses `ddp-bluray`, requires 7.1 output, and defaults to 1280 kb/s.

- Readable Event logger and Jellyfin Library scan examples include setup guides. Releases attach
  installable example plugin ZIPs generated from the same source folders.

- Settings can install and replace Python plugin ZIPs, edit declared plugin options, and remove
  folder plugins. File changes and settings activate on restart; settings and plugin data survive
  replacement and removal. ZIP previews do not execute code. Configuration format version 2 includes
  saved plugin options and continues to read version 1 backups.

- Optional PGS zlib compression for the MKV muxer, disabled by default. Job output settings and
  templates control compression for embedded and added PGS subtitles.

- Templates and Settings use the available page width, with columns adapting to the panel's width.
  New jobs scrolls in short/zoomed windows instead of clipping its form or footer; file slots reflow
  when there is less room.

- Queue search by name/source path, status filters with counts, and pages of 100 jobs. Matching-job
  selection spans pages; hidden selections and batch-action scope are explicit. Keyboard focus
  follows list/rail changes, narrow layouts reflow, and selected rows retain readable contrast.
  Mounted browser tests cover a 10,000-job queue, keyboard interaction, reflow, and accessibility.

- Templates can be shared as versioned JSON files, individually or as a bundle of selected templates.
  The export picker includes Select all, Clear selection, and a selected count. Import previews
  settings and included scripts, supports selecting templates, and keeps existing setups with
  numbered copies for matching names. Invalid files are rejected before anything is saved.

- Imports show a persistent Added / Kept existing / Unmatched summary with reasons and links to
  existing jobs. Partial or zero-add imports retain their input draft for correction.

- Clearing a job's output folder now saves the empty value and blocks the job until a folder is set.
  Edits that omit the folder keep its current value.

- Server controls and WebSockets reject unexpected browser origins, and requests validate Host.
  Local access remains supported; `--allow-host` and `--allow-origin` configure explicit proxy access.

- Import matching discards stale responses, including failures, and Add uses only the settled input
  revision shown in the preview. Changing any path disables Add until the new match completes.

- Batch crop merges each eligible job's crop without replacing its other video settings, continues
  past busy/missing/imported jobs, and reports accurate updated/skipped/failed counts and reasons.

- Initial connection failures retry automatically with capped backoff and a Retry now button. Each
  reconnect reloads required catalogs, and the sidebar distinguishes connecting, retrying and offline.

- Opening or reconnecting during a run restores job details, step statuses and logs. Snapshot event
  boundaries retain newer live updates without duplicating log lines; failed log loads offer Retry.

- Waiting jobs can be unqueued from the selection toolbar or editor without removing their settings
  or files. Running jobs remain separate from this action.

- Rapid Settings edits build on the current draft and save in order. Older replies cannot roll back
  newer notification, action, plugin or tool changes; failed writes offer Retry or Discard.

- Starting or indexing a job waits for pending editor saves, including debounced video edits. Failed
  writes pause later edits and offer Retry or Discard before Start can proceed.

- **Drafts survive navigation.** New jobs and template drafts are retained per browser tab across
  navigation and refresh. Leaving or replacing an edited template offers Save, Discard or Stay.

- **Validate before publishing.** Muxed candidates pass validation before replacing a finished file.
  Unmanaged existing outputs default to Stop; the Output tab offers Skip, Rename and Replace. Files
  appearing or changing during a run are kept, and rejected candidates remain available for inspection.

- **Duplicate imports keep existing jobs.** The match preview links to existing jobs. Replacing one
  requires selecting “Replace and reset its edits”; busy jobs remain protected.

- **Predictable queue starts.** Start queue runs waiting work only, with its job count shown. Completed,
  failed and cancelled jobs run again only when explicitly selected with Run selected.

- **Safer work-folder cleanup.** Manual deletion previews paths and sizes and requires confirmation.
  Records and logs are archived before both manual and automatic cleanup; archive failure keeps the
  working files. Queue-only removal offers Undo with the job's settings and order preserved.

- **Encoder option help and checks.** The Encoder tab's option names come with suggestions and a line
  on what each does, read from the encoder's own help. A mistyped option (in the options or the extra
  arguments) warns with the nearest real name before the run, instead of failing when the encoder starts.
  A pasted command line (`--ref 4 --bframes 8 --no-sao`) in the new option field adds a row per option.
  Also fixed: editing an encoder preset in the preset manager closed its Advanced section.

- **Starter encoder presets.** Every encoder preset picker now offers x265 SDR (CRF 20), x265 HDR10 /
  HDR10+ (CRF 18), x265 Dolby Vision (CRF 18, `--level-idc 5.1`, which fills the VBV Dolby Vision needs)
  and SVT-AV1 (CRF 30, preset 4), all 10-bit, next to the profile's own defaults. Save a copy to change one.

- **Output file checks.** A job whose output file already exists warns that the run replaces it, and
  two jobs that would write the same file are blocked until one gets a label, name or folder of its own.

- **Interlaced source warning.** The probe reads MediaInfo's scan type and field order; an interlaced
  source whose filter chain has no IVTC or deinterlacer warns before the run, and the Video tab shows it.

- **Preset manager dialogs.** Audio and video pickers keep quick selection in a compact popup.
  Manage presets opens a shared dialog with folder browsing and editable encoder settings,
  separate Save and Apply actions, and protection for unsaved edits.

- **Audio presets.** Pick common or saved encoder/channel/bitrate configurations on individual
  audio outputs and template slots/rules. Source-incompatible choices show a reason; saved presets
  support folders, search, and rename/move while preserving each track's metadata.

- **Grouped encoder presets.** Save named configurations under each encoder with nested folders,
  search, rename/move, and repeated names across folders. Pick them in job, template, batch, and
  New jobs editors; selections copy encoder settings while keeping the rest of the setup.

- **Correctness fixes: MP4 subtitles.** Source SRT tracks are extracted and aligned before MP4Box imports
  them, preserving the final cue's duration and timing when the video starts after zero.

- **Correctness fixes: output color.** VP8, VP9, and AV1 container color tags follow encoder overrides,
  including range and AV1 HDR mastering/light levels. Manual color options also work with source color disabled.

- **Correctness fixes: quoted arguments.** Encoder, audio, and mux extra arguments use one parser that removes
  double-quote grouping while preserving Windows paths, empty arguments, and escaped literal quotes.

- **Correctness fixes: edited burn files.** Changing an external subtitle invalidates the video encode and
  preview. VobSub's `.idx` and `.sub` files are tracked together for extraction, presence, and reuse.

- **Correctness fixes: subtitle burn timing.** Source subtitles and identified external extracts are shifted
  to the first decoded video frame before rendering. Standalone subtitle files keep their own timing.

- **Correctness fixes: VFR timing.** Extracted timestamps are normalized to the first video frame, keeping
  audio and subtitles aligned when the source video starts after zero.

- **Correctness fixes: completed files.** Resume and explicit reuse check the completed file's size and
  modification time. An output replaced or truncated by another job is no longer accepted from an old
  job record; old records without file stamps are revalidated through the work folder or rebuilt.

- **Job queue.** Queue a job or a batch of episodes (a folder of sources); each runs index → VapourSynth
  script → x264 / x265 / VP8 / VP9 / SVT-AV1 (1 or 2 passes) → audio → mux → validate. Jobs run one at a time and survive restarts;
  a rerun skips every step whose command and inputs haven't changed, so a crashed job resumes after its last
  finished step and a changed subtitle flag only muxes again. A job's audio encodes run alongside its video
  encode, up to 2 at once by default (Settings → Audio encodes; 0 runs them one by one). A running job shows
  its step, the encoder's speed (fps) and time left, the time since it started and a guess at the job's time
  left, in the queue and the job's header.
- **Pause and process priority.** The Queue's Pause suspends the running job's tools and the index lane's,
  children too (DeeZy's ffmpeg / DEE), until Resume; paused time doesn't count in a step's time or the job's
  time left. Tools run at StaxRip's priorities: the video encode (the encoder and the vspipe feeding it) below
  normal, other tools normal (Settings → Process priority, `[pipeline] encoder_priority` / `tool_priority`); the
  toolbar's gauge menu changes the running ones' for the rest of their run. On Linux it's a nice value.
- **Reuse finished files.** When the jobs you start already have a finished video or audio encode in their work
  folder (from an earlier run, a job removed and added again, or a variant with another label), Start queue /
  Run selected asks per file: reuse it (the job is then mostly a mux, as in StaxRip) or make it again. Files
  made with other settings are offered too, marked and unticked.
- **Work folders.** A job's index, encodes and log live in `<source>_tmp/` next to the source. Settings →
  Work folders deletes it once the job is done (off by default; the job records and log are copied to the
  data folder's `records/` first, the newest 100 kept), and Remove → "Remove and delete work folders" deletes
  the folders of the jobs it removes.
- **Video.** One preview of the script's output, as in VapourSynth Editor, with zoom (100% = one screen
  pixel per frame pixel, nearest-neighbour from there up), pan and crop lines drawn on the real output (the
  cropped-off margins stacked back on, so a FillBorders after the crop shows); auto crop; resize as in
  StaxRip (keep aspect ratio: the height follows the width and each crop, on mod 2/4/8/16, with the aspect
  error shown; anamorphic sources included, and an encode keeps its pixel aspect via --sar); an anamorphic
  frame previews at the shape it plays at (the AR toggle shows the stored pixels); an ordered filter
  chain as in StaxRip (crop and resize are steps in it; each filter can move, switch off or be edited) with
  one-click presets by category, built on the bundled plugins; the generated VapourSynth script, editable. Source filters: FFMS2 (the default, with index progress), L-SMASH, BestSource.
  The encode is timed by the script's frame rate (`vspipe --info`), as in StaxRip: an IVTC or a double-rate
  deinterlace muxes at its own rate and AutoQPF places the chapters by it. A script whose length isn't the
  source's (a trim, a filter that changes the speed) warns on the Video tab and on the finished job: the
  source's audio, subtitles and chapters would be out of step. A variable frame rate source (MediaInfo's VFR)
  keeps its timestamps in an MKV, as in StaxRip (`mkvextract timestamps_v2`, mkvmerge `--timestamps`), while
  the script keeps every frame; one that doesn't (an IVTC) is muxed at its own constant rate and warns, and an
  MP4 (MP4Box takes no timestamps) warns that it's muxed at a constant rate.
- **Encoder.** x264 and x265 option panels, 1 or 2 passes; AutoQPF chapters to a qpf file. A 2-pass encode
  takes a bitrate or a target file size (MB, with StaxRip's DVD / BD sizes to pick): the video gets what the
  size leaves after the audio, subtitles, attachments, HDR metadata and container overhead, over the script's
  length (StaxRip's sum). Pass 2 waits for the audio encodes and counts their files; the Encoder tab shows the
  bitrate and where the size goes, and a size that leaves the video nothing blocks the job. The encode is
  tagged with the source's colour description (primaries, transfer, matrix, range, chroma location, read by
  MediaInfo) and on x265 its HDR10 metadata (mastering display, MaxCLL / MaxFALL) with StaxRip's flags
  alongside it (`--hdr10 --repeat-headers --hrd --aud`, `--range limited` when the source doesn't say, the VBV
  from `--level-idc`); shown on the Encoder tab, "Colour from the source" switches it off, and an option with
  the same flag wins (`--no-hrd` and so on). The Video tab names the
  source's HDR formats: HDR10 / HLG, HDR10+, Dolby Vision with its profile, layers and FEL or MEL (read
  from a second of its RPU).
- **HDR10+.** An x265 encode of an HDR10+ source carries its dynamic metadata ("HDR10+ from the source" on
  the Encoder tab, on by default): hdr10plus_tool reads it from the source, x265 writes it
  (`--dhdr10-info`), in MKV and MP4. A check before the encode stops the job when the script's frames
  aren't the metadata's (a trim, a frame-rate filter); the output is checked for it. x264 drops it (a
  warning), an 8-bit encode blocks. MP4 output no longer adds HDR boxes of its own (MP4Box `:hdr=none`):
  the stream carries the HDR metadata, so MediaInfo lists it once.
- **Dolby Vision.** An x265 encode of a profile 8.1 source (or a profile 7 MEL) carries its Dolby Vision as 8.1
  ("Dolby Vision from the source" on the Encoder tab, on by default), in MKV and MP4: dovi_tool reads the RPU,
  its active area (L5) follows the crop and resize, x265 writes it. Checked like HDR10+ (the script's frames
  before the encode, 8.1 in the output). It needs a 10-bit encode, `--vbv-maxrate` and `--vbv-bufsize` (x265's
  rule; with `--level-idc` set, the level's max bitrate fills the ones not set, High tier unless
  `--no-high-tier`, as StaxRip does) and a mastering display; the job blocks without them. A profile 5 source
  stays profile 5 (StaxRip's flow: the RPU as it is but for its L5; no HDR10 layer, so no mastering display
  needed); without its RPU (x264, or unticked) a profile 5 encode's colours look wrong, which warns. Not carried
  yet: 8.4 (HLG); x264 drops it (a warning).
- **Dolby Vision FEL.** A profile 7 FEL's enhancement layer is baked into the picture (felbaker, now among the
  bundled plugins) and its RPU goes on as 8.1: the index lane demuxes the layer (dovi_tool), muxes it into an
  MKV with the source's frame rate and indexes it; the script bakes it right after the source, so the preview
  shows the baked picture (auto crop reads the base layer). The HDR10 values come from the RPU: the mastering
  display's luminance, and MaxCLL / MaxFALL from its L1 (else L6, else the source's). Needs FFMS2 or L-SMASH
  (BestSource counts frames differently on such sources: it blocks). A profile 7 whose enhancement layer
  couldn't be read still blocks. The preview now lets go of a job's clips when the job is removed and before
  the index lane works on its source, so a work folder can be deleted and the layer written again.
- **Notifications.** Settings → Notifications sends to any service Apprise supports (Discord, Telegram, ntfy,
  Pushover, email, ...): each destination picks its events (job done, failed, cancelled, queue finished), can be
  switched off, and has a Test button that shows the service's own error.
- **Actions.** Settings → Actions runs things after a job ends or the queue finishes: move or copy the output
  to a folder (through a `.partial` file; the next actions see the new path), run a command with `{tokens}`
  (`{output}`, `{record}`, `{label}`, ...; arguments split before the tokens go in, no shell), or POST the event
  to a webhook. Commands run only when videoforge.toml's `[actions] commands` allows them (off in Docker).
  Outcomes go in the job's log and `events.jsonl`. See docs/actions.md.
- **Plugins.** Python plugins in `<data dir>/plugins/` (or installed packages' `videoforge.plugins` entry
  points) get each job's start and end, the queue's end and the index lane's, on a thread of their own, with
  their own settings (`[plugins.<id>]`), data folder and a line in the job's log. Settings → Plugins lists them,
  why one didn't load, and switches one off. `niquests` ships for them. See docs/plugins.md and
  `examples/plugins/library_scan`.
- **Audio.** Copy or encode each track, more than one output from one track: DDP and DDP Atmos (DeeZy + DEE,
  truehdd), AAC (qaac or ffmpeg), Opus (opusenc or ffmpeg), FLAC, AC-3, E-AC-3 (ffmpeg). Each encode lists
  its layouts and bitrates, and a setting the track can't take is fitted or blocked.
- **Audio normalize.** StaxRip's ffmpeg modes on every encode but DDP (DEE sets its own dialogue level), in the
  track's Settings: peak to 0 dB (volumedetect), loudness (EBU R128 loudnorm, two passes: target LUFS, true peak
  and loudness range, default -24 / -2 / 7 as StaxRip) or dynamic (dynaudnorm). The track is measured after its
  downmix in a step of its own, beside the video encode; the encode applies what it found. A source wider than
  the loudness range is compressed to fit (loudnorm's dynamic mode), kept at the source's sample rate.
- **Subtitles.** Keep, leave out, reorder, retitle and flag source subtitles and added SRT files (matched by
  name or SxxEyy). The Select subtitles menu selects all, deselects all, or keeps only one language or type
  (PGS, VobSub, SRT, ASS, etc.), with track counts and the job's edited languages.
- **Burn in subtitles.** "Burn in" on a subtitle track (a source track or an added SRT / ASS / SUP / IDX file)
  draws it into the video with the bundled SubText plugin, as StaxRip's hardcoded subtitle, and leaves it out of
  the mux; one per job, an encode only. A source track is extracted with the index (mkvextract), so the preview
  shows it too. Text (SRT, ASS) is drawn after the crop, as in StaxRip; an image subtitle (PGS, VobSub) before
  it, on the frame it was made for (SubText would stretch it onto the cropped one). A template's subtitle rule
  can burn in too (the first track it matches). The filter menu's Subtitle category has a "Burn in subtitles"
  preset for a file of your own (its lines to edit: a `style` for an SRT, say).
- **Containers.** MKV (mkvmerge) and MP4 (MP4Box), each with a warning or a block for what it can't hold. MKV
  keeps the source's attachments (an ASS subtitle's fonts) and global tags, as StaxRip does. MP4Box starts each
  track it copies at 0, so a copied track gets its delay to the video, as an encoded one does. MP4 holds a
  3-letter ISO 639-2 language (StaxRip writes the same): a region or script warns (es-419 is written as es), and
  the output check compares the language alone (a Fallout MP4 with es-419, fr-CA, nb and zh-Hant subtitles no
  longer comes out invalid). Basque, Galician, Kannada and Malayalam are known languages.
- **MP4 and M2TS / TS sources.** A source can be an MKV, MP4 (.mp4, .m4v) or MPEG transport stream (.m2ts,
  .mts, .ts), indexed straight from the file as in StaxRip. ffprobe (found next to ffmpeg) times it: each
  track's start as a player starts it (a TS's timestamps, an MP4's edit lists, which MediaInfo doesn't always
  list), for the audio's delay to the video, copied or encoded, and the exact frame rate (mkvmerge has one for an
  MKV only). Without ffprobe, MediaInfo's (23.976 taken as 24000/1001). A Blu-ray TrueHD track's AC-3 core is a
  track of its own (to copy into an
  MKV or encode; MP4Box can't copy it apart, so MP4 blocks that). MP4 output takes a TS track by its PID and an
  MP4's by its track ID. mkvextract reads Matroska only: a burned-in subtitle and a VFR source's timestamps are
  first copied into an MKV in the work folder (mkvmerge), which keeps the TS's timing. When MediaInfo gives a TS
  no frame rate (an x264 TS) or no chapters (a TS's program menu), AutoQPF takes the script's frame rate and
  chapters every 5% of the runtime.
- **VP8 / VP9.** Through ffmpeg's libvpx, as StaxRip's ffmpeg encoder does: CRF (`-crf` with `-b:v 0`, 0-63;
  VP8 `-b:v 100M`, since ffmpeg reads VP8's `-b:v 0` as a 256 kbit/s cap, StaxRip's included), 1-pass bitrate or
  2 passes (a target size too), the speed as `-cpu-used` (StaxRip's 0-6 list; VP8 at 4 and up warns: it puts a
  keyframe on every 2nd-3rd frame after a scene cut), StaxRip's VP9
  defaults (`-tile-columns 6 -frame-parallel 1 -auto-alt-ref 1 -lag-in-frames 25`, plus `-row-mt 1`) before the
  job's `-options`; VP8 is 8-bit only, VP9 8 / 10 / 12-bit. The encode is an IVF that both muxers read as it is;
  the chapters' keyframes are forced (`-force_key_frames`, from the qpfile); the pixel aspect and the colour the
  stream doesn't hold (VP9 has only the matrix and the range) are tagged by the mux (`--aspect-ratio-factor`,
  `--colour-*`; MP4Box `:par`, `:colr`). An HDR10 source's mastering display and light levels aren't carried
  yet (a warning). The Docker image's FFmpeg now has libvpx (rebuild the plugins image).
- **SVT-AV1.** SvtAv1EncApp, as StaxRip runs it (`tools/SvtAv1EncApp/SvtAv1EncApp.exe`; StaxRip ships Patman86's
  builds): CRF (`--rc 0 --crf`, 1-70 in quarter steps), 1-pass bitrate or 2 passes (`--rc 1 --tbr`, `--pass`;
  a target size too), the preset (StaxRip's -1 to 13 list, 4 by default) and tune, 8 or 10-bit, `--progress 2`
  (whose lines the queue reads, frames a minute included). Two passes add `--undershoot-pct 5` (StaxRip doesn't),
  unless the options or extra arguments set it: at SvtAv1EncApp's 25 a Fallout sample came in 26% under the
  bitrate (8 minutes of it, 33%; its own `--passes 2` the same), at 5 within 5.5%. It's told the script's frames
  (`--frames`, as StaxRip does: from a pipe it doesn't know the length). The source's colour goes in as H.273
  code points with the HDR10 mastering display (in plain numbers) and light levels, as StaxRip's SetMetaData
  writes them; the chapters' keyframes are forced (`--force-key-frames`, CRF only: SvtAv1EncApp refuses them with a bitrate, which
  warns). The encode is an IVF: the MKV's track is tagged with its pixel aspect, colour and HDR10 (mkvmerge
  copies none of it from the stream); the MP4 gets `:par` and `:colr`, and MP4Box's mdcv / clli from the stream.
  HDR10+ and Dolby Vision stay x265's (a warning). The Docker image builds SvtAv1EncApp 4.2.0.
- **Templates.** A job's whole setup without a file: video, crop mode (keep, the template's, detect per job),
  encoder, container, AutoQPF, audio by position or by rules, subtitles by rules. Star one as the default
  for new jobs; apply one to a job or a batch.
- **Batch index.** Index jobs in the background while encodes run; a job whose source is on the disk an
  encode is reading waits, and jobs on other disks go first.
- **Output name and label.** A job's own file name in place of the source's; a label added after it to
  tell runs of one source apart.
- **Folder browser.** Make folders, and delete them (one with anything in it only once you tick that its
  contents go too).
- **Logs and job records.** A text log in each job's work folder, an app log per session, and for each
  output a machine-readable record of how it was made plus a live event stream
  ([job record format](https://jessielw.github.io/VideoForge/job-record/)). The encoders' and vspipe's progress lines are logged at every 1%
  of the step (the progress bar sees them all), so a long encode keeps the job's first lines in its log.
- **Settings.** Tool paths with a check for each, folder browser roots, the disk wait, Shut down. The version
  shows in the sidebar (and `/api/health`).
- **Desktop window.** `serve --window`: the app in its own window with a tray icon; Explorer drops carry
  file paths.
- **Portable build (Windows x64).** A zip with its own Python: unpack, add the tools, run `VideoForge.exe`.
  dovi_tool and hdr10plus_tool come with it (`scripts/fetch_tools.py` fetches them for a source install).
- **Docker (Linux, amd64).** The server with the free tools (MKVToolNix, x264, x265, FFmpeg 9, MP4Box,
  opus-tools, DeeZy, truehdd, dovi_tool, hdr10plus_tool), in a browser. Its x265 is built with HDR10+. Windows tools run under Wine from
  `/tools/wine` (qaac, DEE's Windows build).
- **Bundled VapourSynth plugins.** Source filters (BestSource, L-SMASH-Works, FFMS2, d2vsource) and common
  filters (EdgeFixer, FillBorders, MVTools, znedi3, dfttest2, BM3D, zsmooth, vszip, fmtconv, descale, ...)
  plus havsfunc, mvsfunc and awsmfunc, from one list (`vsplugins/manifest.toml`): built from source in the
  Docker image, downloaded (pinned, checked) for the portable build or a source install
  (`scripts/fetch_plugins.py`).
- **Profiles.** The built-in `manual` profile; other profiles (a release group's rules) install as separate
  packages under the `videoforge.profiles` entry point group.

[0.1.0]: https://github.com/jessielw/VideoForge/releases/tag/0.1.0
