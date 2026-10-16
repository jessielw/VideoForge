# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - Unreleased

The first beta: an encode and mux job queue in the browser, for one user on Windows.

### Added

- **Job queue.** Queue a job or a batch of episodes (a folder of source MKVs); each runs index → VapourSynth
  script → x264 / x265 (1 or 2 passes) → audio → mux → validate. Jobs run one at a time and survive restarts;
  a rerun skips every step whose command and inputs haven't changed, so a crashed job resumes after its last
  finished step and a changed subtitle flag only muxes again.
- **Video.** Frame preview with zoom, pan and a crop overlay; auto crop; resize; filters; the generated
  VapourSynth script, editable. Source filters: FFMS2 (the default, with index progress), L-SMASH, BestSource.
- **Encoder.** x264 and x265 option panels, 1 or 2 passes; AutoQPF chapters to a qpf file.
- **Audio.** Copy or encode each track, more than one output from one track: DDP and DDP Atmos (DeeZy + DEE,
  truehdd), AAC (qaac or ffmpeg), Opus (opusenc or ffmpeg), FLAC, AC-3, E-AC-3 (ffmpeg). Each encode lists
  its layouts and bitrates, and a setting the track can't take is fitted or blocked.
- **Subtitles.** Keep, leave out, reorder, retitle and flag source subtitles and added SRT files (matched by
  name or SxxEyy).
- **Containers.** MKV (mkvmerge) and MP4 (MP4Box), each with a warning or a block for what it can't hold.
- **Templates.** A job's whole setup without a file: video, crop mode (keep, the template's, detect per job),
  encoder, container, AutoQPF, audio by position or by rules, subtitles by rules. Star one as the default
  for new jobs; apply one to a job or a batch.
- **Batch index.** Index jobs in the background while encodes run; a job whose source is on the disk an
  encode is reading waits, and jobs on other disks go first.
- **Job label.** Added to the output name to tell runs of one source apart.
- **Logs and job records.** A text log in each job's work folder, an app log per session, and for each
  output a machine-readable record of how it was made plus a live event stream
  ([docs/job-record.md](docs/job-record.md)).
- **Settings.** Tool paths with a check for each, folder browser roots, the disk wait, Shut down.
- **Desktop window.** `serve --window`: the app in its own window with a tray icon; Explorer drops carry
  file paths.
- **Portable build (Windows x64).** A zip with its own Python: unpack, add the tools, run `VideoForge.exe`.
- **Profiles.** The built-in `manual` profile; other profiles (a release group's rules) install as separate
  packages under the `videoforge.profiles` entry point group.

[0.1.0]: https://github.com/jessielw/VideoForge/commits/main
