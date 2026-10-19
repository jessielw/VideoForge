# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - Unreleased

The first beta: an encode and mux job queue in the browser, for one user: on Windows (portable zip or from
source), or in Docker on Linux.

### Added

- **Job queue.** Queue a job or a batch of episodes (a folder of source MKVs); each runs index → VapourSynth
  script → x264 / x265 (1 or 2 passes) → audio → mux → validate. Jobs run one at a time and survive restarts;
  a rerun skips every step whose command and inputs haven't changed, so a crashed job resumes after its last
  finished step and a changed subtitle flag only muxes again. A job's audio encodes run alongside its video
  encode, up to 2 at once by default (Settings → Audio encodes; 0 runs them one by one). A running job shows
  its step, the encoder's speed (fps) and time left, the time since it started and a guess at the job's time
  left, in the queue and the job's header.
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
  source's audio, subtitles and chapters would be out of step.
- **Encoder.** x264 and x265 option panels, 1 or 2 passes; AutoQPF chapters to a qpf file. The encode is
  tagged with the source's colour description (primaries, transfer, matrix, range, chroma location, read by
  MediaInfo) and on x265 its HDR10 metadata (mastering display, MaxCLL / MaxFALL); shown on the Encoder tab,
  "Colour from the source" switches it off, and an option with the same flag wins. The Video tab names the
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
  `--no-high-tier`, as StaxRip does) and a mastering display; the job blocks without them. Not carried yet: profile 5 (always blocks: it has
  no HDR10 layer) and 8.4 (HLG); x264 drops it (a warning).
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
- **Subtitles.** Keep, leave out, reorder, retitle and flag source subtitles and added SRT files (matched by
  name or SxxEyy).
- **Containers.** MKV (mkvmerge) and MP4 (MP4Box), each with a warning or a block for what it can't hold. MKV
  keeps the source's attachments (an ASS subtitle's fonts) and global tags, as StaxRip does.
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
  ([docs/job-record.md](docs/job-record.md)). The encoders' and vspipe's progress lines are logged at every 1%
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
