# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- x264 / x265 encodes warn (`video.color_retag`) when the encoder options or extra arguments set `--colorprim`, `--transfer`, `--colormatrix` or `--range` to something other than the source's. The flags only label the picture, so unless the script converts it a player shows the wrong colours: a BT.2020 SDR UHD tagged BT.709 plays oversaturated. Remove the flags to keep the source's colour.
- A UHD source that doesn't describe its colour gets a note (`video.color_untagged`) when the encoder options don't set it either: the encode is untagged there and a player has to guess.
- Track editor: when a rule set picks the Default track itself and offers no Default pill (e.g. the first audio track), the track it marks shows a read-only "Default" label.
- Job editor: a MediaInfo button shows MediaInfo's text report of the source, or of the job's encode, added audio or subtitle files, with a Copy button. The report is read when asked (a spinner shows while it loads) and kept until the file changes. API: `GET /api/jobs/{id}/mediainfo?path=`, limited to the job's own files.

### Fixed

- A plugin rule set built for 0.1.6 or earlier (`detected_flags(track)`, without `original_language`) no longer breaks the job page with a 500: it's called with the track alone.

## [0.1.7] - 2026-11-11

### Added

- Track editor: a subtitle file extracted from the source (gMKVExtract `_trackN_`) that takes its title from that input track now says so: "(title inferred from input track #N)" beside the title, and in the track details. Tracks report it as `title_from` (the input track's id).

### Changed

- Rule sets: `detected_flags` also gets the plan's original language, for flags that depend on it (a dub's subtitle).

## [0.1.6] - 2026-11-11

### Added

- Settings: "Index anyway while it only encodes video" (on by default, under "Wait while an encode reads the same disk"). A job in the index lane on the encode's disk no longer waits for the whole encode: it goes once the running job is only encoding video, and still waits while that job extracts, encodes audio, indexes, or muxes. `PUT /api/config` takes `index_during_video` for the same.
- The queue state (`GET /api/queue`) reports `index_held`: how many jobs in the index lane are waiting for an encode's disk.

### Changed

- Configuration exports are version 8 (they carry the new setting); older backups import with it on.

### Fixed

- Lower bar hiding connected status in bottom
- The sidebar said "Indexing N jobs" when the jobs were only waiting for an encode's disk; it now shows those as "N to index after the encode", apart from the ones being indexed.

## [0.1.5] - 2026-11-10

### Added

- Settings: "Index new jobs" and "Auto-crop new jobs" (both on by default). A new job is put in the index lane as soon as it is probed, and its crop is detected after the index; a template with a fixed crop keeps it and a crop set by hand wins.
- New jobs: paste file paths anywhere in the app (Explorer: Ctrl+Shift+C, then Ctrl+V) and they land on New jobs, matched and ready.
- New jobs: a bar at the bottom says what **Add** will do (job count, template, index and crop, output folder) and, once added, offers **Open queue** and **Add more** without scrolling.
- New jobs: **Index** and **Auto-crop** for the batch, starting from the Settings values. `POST /api/jobs` takes `auto_index` and `auto_crop` for the same.
- Track editor: the Default flag shows what the rule set plans (a rule set that picks the default subtitle itself shows it), so it can be changed by hand.
- Video tab: drag the divider between the preview and the side panel to resize it (arrow keys too); Settings and Script share one width, which is remembered.
- Video tab, Script: **Copy** puts the whole script (generated head and tail included) on the clipboard, and **Save** writes it as a `.vpy` file to open in vsedit.

### Changed

- The preview's **Edges** toggle is now **Boost**: it multiplies each channel by 6 (clipped), so a dirty border row a few levels off black stands out. It replaces the Sobel edge view, which lit up every edge in the picture and hid faint border rows.
- New jobs: encodes, subtitles and chapters sit under **More inputs**, which opens by itself once used. The page's **Job files** row is gone; use **Add jobs from job files** on the Queue page.
- The built-in rule set makes the first audio track the default when the source has none (a default cleared by hand stays cleared).
- EdgeFixer Reference's comment now says which blur each pair of sides uses.
- Configuration exports are version 7 (they carry the new setting); older backups import as before.
- Updated apprise, fastapi, and niquests.
- Video tab: **Expand** moved into the side panel's tab row, giving the preview the empty header row's height.
- Video tab: the preset button reads "Video preset: ..." so it isn't mistaken for the job template; the Script panel's run summary stays in a stable grid, and the Settings panel keeps room for its scrollbar.

## [0.1.4] - 2026-11-07

### Added

- DeeZy 1.5.0 in the Docker image and the Windows portable build. With split DEE encoders, dialnorm, Blu-ray DDP and Blu-ray Atmos now work, and 7.1 DDP is made with the Blu-ray encoder. New DDP options for split DEE: loudness target, peak limit and user data (left out with a warning on a single `dee`; a loudness target can't be combined with a dialnorm or Blu-ray DDP).
- Audio: MP3 encode (ffmpeg's `libmp3lame`) for mono and stereo; MP3 tracks are recognised, and `.mp3` files can be added as external audio.
- Audio: Vorbis encode (ffmpeg's `libvorbis`, `.ogg`) up to 7.1; Vorbis tracks are recognised. MP4 output blocks Vorbis, so use MKV.
- Docker: the container's log says what it found in `/tools` (`videoforge: qaac: found (Wine)`, `dee: not in /tools`).
- Docker: Wine's files are set up in the background at start when a Windows tool is in `/tools`, so the first qaac or DEE run isn't the slow one.
- Docker: DEE and qaac in `/tools` are found with nothing set in Settings, including ones added after the container started.

### Changed

- Docker: `compose.yaml` sets `PUID` / `PGID` instead of `user:`. Started as root first, the container makes `/tools` readable and DEE's Linux programs executable itself, so the host no longer needs `chmod`. If you use `user: "1000:1000"`, switch to `PUID` / `PGID`.
- Docker: if DEE's Linux programs still can't be made executable (a read-only mount), they are run from a copy of `/tools/dee` made at start.
- Tools that can't start say why in plain words (a Windows program without Wine, files that can't be read or run, with the fix).
- Settings shows the `.exe` path you gave for a Windows tool, not the Wine launcher VideoForge runs in its place.
- Docker docs: no host `chmod` step, `PUID` / `PGID` in the Compose example.
- Update fastapi to latest version.

### Fixed

- A path to a Windows `.exe` (`qaac64.exe`, `dee.exe`) now runs through Wine in the Docker image, instead of failing with `Exec format error`.

## [0.1.3] - 2026-11-06

### Added

- Split DEE encoders (`dee_ddp_encoder`, `dee_ddpjoc_encoder`, ...) from newer DEE releases and Dolby Media Encoder, for DeeZy 1.4.0. Set **DEE** to the folder of encoders, or to one of them; a bare `dee` finds them on `PATH`. A single `dee` program still works and is preferred.
- DeeZy 1.4.2 in the Docker image and the Windows portable build (1.3.15 can't take the split encoders).
- Docker: split encoders go in `/tools/dee/` (Linux) or `/tools/wine/dee/` (Windows `.exe` files, run through Wine).
- The split encoders can't make Blu-ray DDP, 7.1 DDP or Blu-ray Atmos: a plan using them is blocked with a message, and a dialnorm setting is left out (DEE measures the level) with a warning.

### Fixed

- A track a rule set plans to encode now shows its saved or plugin audio preset in the Audio tab's preset menu, not a built-in with the same settings. The planned title is part of the match, and a saved or plugin preset wins a tie with a built-in.

## [0.1.2] - 2026-11-05

### Added

- Pause after pass 1: on a 2-pass encode, the Queue's **Pause after pass 1** stops the running job once pass 1 is done. The job shows as Paused and keeps what it finished, so VideoForge can be closed; Run it later to go on with pass 2.
- Job files: a job's whole setup is saved as `videoforge-job.json` in its folder in the source's `_tmp` folder when it runs (or with **Save job file**). **Add jobs from job files** puts jobs back exactly as they were, from a file, a job folder, or a whole `_tmp` folder.
- EdgeFixer Reference filter preset (1 px, 2 px, Empty) beside the existing continuity-mode EdgeFixer: it fixes edges against a blurred copy, blurring along the axis being fixed.
- Settings → Appearance: pick a colour palette (Gold, Indigo, Ocean, Forest, Ember, Rose, Slate), a custom accent colour, UI density (Compact, Default, Comfortable), corner roundness, and a pure-black dark mode, beside the light / dark / system mode. Remembered in the browser.

### Changed

- Settings is split into tabs (General, Tools, Encoding, Presets, Automation, Plugins, Backup & reset) instead of one long page. The tab you had open is remembered.
- Deleting a template now asks first: **Delete** turns into **Confirm?** for a few seconds, and a second click deletes it.
- Settings → Plugin presets: a plugin with many presets to look at now scrolls inside its own box instead of making the page longer.
- The page opens by any IP address (a LAN address, a Docker host) without `VIDEOFORGE_ALLOW_HOST`; IP addresses can't be DNS-rebound. Hostnames still need `VIDEOFORGE_ALLOW_HOST` / `--allow-host`.

## [0.1.1] - 2026-11-05

### Added

- Settings → Plugin presets: "Restore all deleted" brings back every preset of a plugin you deleted, in one click.

### Fixed

- Resetting the presets or restoring a configuration no longer leaves a plugin's presets missing for good: they are shipped again, instead of being read as presets you deleted. A profile left with no presets at all by an older build gets them back at the next start.

## [0.1.0] - 2026-11-05

### Added

- A rule set can be installed as a plugin ZIP (Settings → Plugins → Install ZIP…), for portable and Docker installs that can't add Python packages. Its `videoforge-plugin.toml` names the class with `rule_set = "ClassName"`; `vendor/` holds pure-Python dependencies. It appears in the rule set list after a restart.

- A plugin can ship presets (`presets = "presets/pack.json"` in its manifest): templates and encoder, audio and video presets arrive and update with the plugin, in every profile. A preset the user edited is left alone and marked "update available"; a deleted one stays deleted; either can be reset to the shipped version. See Plugins → Ship presets with a plugin.

### Changed

- A job's Template button names the template the job's muxer settings and AutoQPF match, even after an encoder preset or a detected crop changed it: `Template: <name> + own encoder`, or `Template: custom` when none fits. It used to say `Template` unless every setting matched exactly.

### Fixed

- External subtitles named with a full language name (`English.srt`, `english force.srt`) now get their language (and forced flag) from the file name instead of showing as unknown.
- A track's Audio preset button no longer says `Copy` beside an encode the rule set chose. It shows the planned encode, channels and bitrate (your own changes still win).

## [0.1.0-beta.17] - 2026-11-04

### Changed

- VideoForge no longer has its own desktop window. `serve --tray` (VideoForge.exe) puts an icon in the tray and opens the page in your default browser; Open VideoForge opens it again and Quit stops it. Dropping a file onto a path field now explains how to paste instead (Explorer: Ctrl+Shift+C, then Ctrl+V). `--window` is gone, and with it pywebview, the .NET bridge it needed and the WebView2 requirement.
- Preview log now shows a repeated line once instead of once per frame to prevent spamming the logger.

### Fixed

- The desktop window could fail to open, silently, on a Windows machine where the extracted DLLs were marked as downloaded from the internet (.NET refused to load them). The window is gone, and so is that failure.

### Added

- The tray runs one VideoForge per data folder (a second launch, even during the first's startup, opens its page) and, when its port is taken by another program, uses the next free one.
- Uncaught errors and native crashes are written to the app log (and a `.crash` file beside it) instead of vanishing in the windowed build.

## [0.1.0-beta.16] - 2026-11-02

### Added

- **Saved output folders**: a **Saved** menu beside the output folder (New jobs, and a job's Output tab) lists the folders you've added jobs to, newest first (the last 10), and the ones you pinned. Pin a folder to keep it, star a pinned one to make it the default that pre-fills New jobs (otherwise it's the last folder used), or forget one. A filter box shows once there are more than 8. The list is saved on this machine, in neither templates nor configuration exports.

## [0.1.0-beta.15] - 2026-11-02

### Added

- The Audio tab and track details show an audio track's commercial name (`DTS-HD MA` where it showed `DTS`; `Dolby TrueHD with Dolby Atmos`), as MediaInfo gives it. A track without one shows its raw format, as before; a job probed earlier gets it once it's probed again.

- The track list names a subtitle's language beside its code: `#18 SRT · Spanish (Latin America) · es-419`.

### Changed

- The Dolby Vision enhancement layer, RPU and HDR10+ extraction steps show progress (ffmpeg's frame count against the source's), where their bar sat at 0% until the step ended and indexing looked hung.

- The progress figures say what they count. The bar, the tab title (`job 4% · ...`) and the queue entry are the whole job's, each step weighted (a pass 1 at 0.6% is a few percent of the job); the main panel adds `· job N%` after the step's own, and the queue entry shows the step's percent beside its name.

## [0.1.0-beta.14] - 2026-10-31

The first beta: an encode and mux job queue in the browser, for one user: on Windows (portable zip or from source), or in Docker on Linux.

### Added

- **Keyboard shortcuts**: **?** (outside a text field) or **Shortcuts** in the menu lists every one, for the queue list, the frame preview, the Video tab and the script editor.

- A run checks for free space before its first step, as StaxRip's Minimum Disk Space does: with less than `[pipeline] min_free_gb` (20 GB by default; 0 turns it off) on the disk of the job's work folder or output folder, it fails at once (`Only 12.3 GB free on the disk of ...`) instead of filling the disk hours into an encode, and the queue goes on to the next job.

- A done job's header says what its last run made: `Made 4.5 GB · 25.0% of the source · 6,120 kb/s · took 1:23:45 (2 reused)`. It's taken as the run ends (the job's `made`), so it stays after a move action or a deleted work folder.

- The browser tab's title follows the running job (`42% · Show S01E01 · VideoForge`, `Paused · ` in front while paused), so a background tab shows how far the queue is.

- **CRF search** on the Encoder tab (ab-av1's crf-search, on the test encode's blocks): the highest CRF whose quality still reaches a target, SSIMULACRA2 (the mean, or the worst 5%) or XPSNR. It encodes the sample at the job's CRF, then steps up or down until one CRF passes and a higher one fails, then narrows between them by their scores, up to 8 tries. Each try shows as it ends (CRF, bitrate, whole video's size, scores); **Use CRF N** puts the one found on the job, and the result stays current then (it's out of date once anything else changes). It runs in the index lane like the test encode (Stop cancels it); every try is kept in `sample/search/crf-<n>/`, so a search for another target reuses the CRFs already encoded. `POST /api/queue/search`; `search.started` / `search.finished` events.

- **Test encode** on the Encoder tab (StaxRip's compressibility check): the job's script and encoder settings on 2 s blocks spread over the video (5% by default; 1, 2 or 10%), for the bitrate they give, the whole video's size at it and the whole encode's time. It runs in the index lane beside the queue (indexing the source first if it has to); the job is locked meanwhile, but its preview opens. A 2-pass job is tested as one pass at its bitrate. The result stays with the job, marked once its settings change; the files are in `sample/` in the job's folder. **Settings → Test encode → Score its quality** (off by default) adds SSIMULACRA2 (mean and worst 5%) and XPSNR scores against the encoder's input, measured with the bundled vszip; configuration backups are version 4 (they carry the setting), and older ones import with it off.

- **Compare** on the Video tab: the encoder's input against its output at the same frame, flipped with **C** (Input / Encoded), the other side preloaded so a flip is instant. Against a test encode (the overlay gives each sample frame's frame in the script) or a done job's output file. The encodes open through FFMS2, indexed in the job's folder.

- **Track details** on the Audio and Subtitles tabs: the ⓘ on a track opens what the probe read (format, codec, channels, sample rate, bit depth, bitrate, delay, duration, size and flags; a subtitle's format, line or image count and flags), on a locked or done job too. The track editors' hints are styled tooltips now, and a long track title wraps instead of widening the tab.

- **New jobs** pairs every subtitle format a job takes, not only SRTs: ASS/SSA, SUP and VobSub (by its `.idx`) added to the Subtitles slot, dropped in a mix, or found beside the source.

- Styled tooltips across the app in place of the browser's plain ones: the queue's toolbar, rows and rail, the menu, the Video tab and frame preview, the job, template, encoder and audio editors, the menus and pickers, and Settings. A disabled button still shows why it's disabled.

- Jobs are queued explicitly: a tick on each queue row (and **Queue** at the top of the job's editor) queues the job and locks its settings, and **Queue (N)** queues a selection. **Start queue** runs only queued jobs (it no longer takes every ready job when none is queued), and a job ticked while the queue runs is picked up in its turn. Unticking a job that ran before keeps its last result.

- **Save** on the preview's toolbar (or **S**) downloads the shown frame as a PNG: full size and lossless, without the edges view, crop lines or matte. It's named after the source with the frame number padded to the clip's length (`Show S01E01 - 00042.png`), so a folder of them sorts in order; one saved from the crop view is marked `(crop view)`, as it has the cropped-off margins on. In the desktop window (`serve --window`) downloads now open a Save As dialog: before, pywebview dropped them, so saved frames and preset or configuration exports went nowhere.

- The preview's frame bar scrubs smoothly on long sources: it loads the frame where a drag rests, and the one it's let go on.

- Importing a template or preset with the same name replaces yours instead of adding `Name (2)`, so importing an updated pack again adds no duplicates. The preview marks each entry (**replaces yours**, **already the same**); **Keep both** brings back numbered copies. **Select** on the Templates list and in the preset managers deletes several at once (a folder's box picks everything inside it).

- **Settings → Default subtitles**: subtitle rules every new job gets unless its template sets its own. Subtitle rules (templates and the default) can **name untitled tracks** from their language and flags. Configuration backups are version 3 (they carry the default rules); version 1 and 2 backups still import.

- **Settings → Reset VideoForge**: go back to videoforge.toml's settings, empty the preset and template libraries, and/or remove every job, after typing RESET. A configuration backup is saved to `backups/` in the data folder first (import it to undo); installed plugins, work folders and kept job records stay. It's refused while the queue runs.

- A profile with its own track rules can offer the full track editor (`picks_tracks` with `track_editor`). The editor starts from the profile's picks, titles and encodes, and saves only what you change. Ticking a track the rules left out keeps it (`exclude: false`). The track order is saved only once you move a track. Settings' default subtitle rules leave such a profile's jobs alone.

- **Name subtitles** on a job's Subtitles tab (StaxRip's "Set names"): titles the kept tracks from their language and flags, `English`, `English (Forced)`, `English (SDH)`; the untitled ones, or all.

- Template folders: a folder box before a template's name (`Group / 1080p`, `/` for nested ones). The Templates list shows them as a tree you can fold; New jobs groups its template picker by folder. The folder is part of the name, so defaults, exports and imports keep it.

- Language boxes (template audio and subtitle rules, a track's language, the original language) are a searchable picker: type part of a name or a tag, or pick from the list; rules show their languages as chips. Any other tag can still be typed. It replaces the browser's own suggestion popup.

- The Encoder tab's target size and option name boxes suggest from their own list, like the language picker, in place of the browser's popup. Option names match by name first, then by their help text.

- `serve` reads its settings from `VIDEOFORGE_*` variables too (`VIDEOFORGE_ALLOW_HOST`, `VIDEOFORGE_ALLOW_ORIGIN`, `VIDEOFORGE_PLUGIN_MANAGEMENT`, `VIDEOFORGE_HOST`, `VIDEOFORGE_PORT`, `VIDEOFORGE_DATA_DIR`), so a Docker or Unraid template sets them without replacing the image's command. The image honors `PUID` / `PGID`, `UMASK` and `TZ`: started as root, it runs as that user (through gosu) and hands `/data` to it.

- The Docker image's x264 is Patman's mod (0.165.3223+44, on VideoLAN's r3223), the build StaxRip and the Windows tools use, so its options (`--aq-bias-strength` and others) work in the container too. VideoLAN's x264 refused them ("unrecognized option").

- Auto crop of a Dolby Vision source takes the bars from its RPU's L5 active area (DoviCrop's method), not only the luma: the detected borders stop short of a bar's soft edge (Godzilla Minus One: 274 where L5 says 276 / 277). Per side the smallest bar of the presets in use (a varying-aspect film keeps every frame), rounded down to mod 2, checked against the detected borders (a side where the picture shows inside the bar takes the detected value). The index now extracts the RPU (the encode reuses it). The editor and the job log say where the crop came from.

- The job record keeps the encoder's closing statistics for the final pass (`video.encoder_summary`: x264 / x265's "frame I: ..." to "encoded N frames ..."), the block an NFO quotes. A run that reuses the encode keeps the earlier run's.

- A DDP or Atmos encode no longer fails when the job's folder is too deep for DEE (Windows' 259-character limit: a long source name in a deep folder). DeeZy then works in a short temp folder of its own.

- A standard-mode DDP 7.1 above 1024 kb/s blocks the plan (DEE makes it 1024): Blu-ray mode goes higher.

- DDP Blu-ray 7.1 reads as DDP, not AC-3: some MediaInfo builds report its AC-3 core and E-AC-3 dependent substream as AC-3 "Dep", which failed the output check of a job that made one.

- Job records state what the encode carried of the source's HDR (`video.hdr`): its Dolby Vision (profile, layers, FEL or MEL) and HDR10+, the profile the encode's Dolby Vision is written as, whether a FEL was baked in, and whether HDR10+ was kept. An NFO tool no longer has to read the log for it.

- A profile can set DeeZy's dialogue level (`AudioSettings.dialnorm`, `--custom-dialnorm`) for its DDP and Atmos encodes; a track's own Dialogue level still wins.

- x265's multi-pass analysis (`--multi-pass-opt-analysis` / `-distortion`) goes to `video.analysis` beside the two-pass stats (`--analysis-reuse-file`, as StaxRip does) instead of `x265_analysis.dat` in VideoForge's working directory; pass 2 waits for it like the stats.

- x265 is Patman86's mod, 4.3+22+73 (the one StaxRip ships), on Windows (its generic x86-64 gcc build) and in Docker (built from the same tag), in place of DJATOM's 3.6+30 aMod on Windows and x265 4.1 in Docker. It takes `--dhdr10-info` though its help leaves it out, so `verify_toolchain.py --smoke` now encodes HDR10+ and Dolby Vision and reads them back instead of reading the help.

- The FillBorders filter presets use `fillmargins` (StaxRip's mode) and list the other modes in a comment.

- **Duplicate** on the Queue copies the selected jobs, each right after its original with a label of its own, for a second output from the same source with a few settings changed. The copy reuses the source index and every encode whose settings it kept. Labels now show in the queue list and the job header, and search matches them.

- Each job keeps its files in its own folder in the source's work folder, named by its label (`main/` without one): its script, encodes, chapters, log and records. Files from the source alone (index, HDR metadata) stay shared at the top. A job whose encode would match another job's links that file into its folder instead of encoding again. Actions get `{job_dir}`, and records a `job_dir` field. Work folders made before this keep their files, but jobs encode again once.

- Audio and video encoder preset pickers show **My presets** and custom folders first across all encoders. Search spans folders and encoders, with an optional encoder filter. The same browser is available in preset managers, including Settings.

- Audio **Delay** fields show the total delay, initially filled with the detected source delay. Entering zero cancels that delay; clearing the field restores it. Existing saved corrections retain their timing.

- DDP mode selection for DeeZy: Standard (default) or Blu-ray, retained in audio presets and templates. Blu-ray uses `ddp-bluray`, requires 7.1 output, and defaults to 1280 kb/s.

- Readable Event logger and Jellyfin Library scan examples include setup guides. Releases attach installable example plugin ZIPs generated from the same source folders.

- Settings can install and replace Python plugin ZIPs, edit declared plugin options, and remove folder plugins. File changes and settings activate on restart; settings and plugin data survive replacement and removal. ZIP previews do not execute code. Configuration format version 2 includes saved plugin options and continues to read version 1 backups.

- Optional PGS zlib compression for the MKV muxer, disabled by default. Job output settings and templates control compression for embedded and added PGS subtitles.

- Templates and Settings use the available page width, with columns adapting to the panel's width. New jobs scrolls in short/zoomed windows instead of clipping its form or footer; file slots reflow when there is less room.

- Queue search by name/source path, status filters with counts, and pages of 100 jobs. Matching-job selection spans pages; hidden selections and batch-action scope are explicit. Keyboard focus follows list/rail changes, narrow layouts reflow, and selected rows retain readable contrast. Mounted browser tests cover a 10,000-job queue, keyboard interaction, reflow, and accessibility.

- Templates can be shared as versioned JSON files, individually or as a bundle of selected templates. The export picker includes Select all, Clear selection, and a selected count. Import previews settings and included scripts, supports selecting templates, and keeps existing setups with numbered copies for matching names. Invalid files are rejected before anything is saved.

- Imports show a persistent Added / Kept existing / Unmatched summary with reasons and links to existing jobs. Partial or zero-add imports retain their input draft for correction.

- Clearing a job's output folder now saves the empty value and blocks the job until a folder is set. Edits that omit the folder keep its current value.

- Server controls and WebSockets reject unexpected browser origins, and requests validate Host. Local access remains supported; `--allow-host` and `--allow-origin` configure explicit proxy access.

- Import matching discards stale responses, including failures, and Add uses only the settled input revision shown in the preview. Changing any path disables Add until the new match completes.

- Batch crop merges each eligible job's crop without replacing its other video settings, continues past busy/missing/imported jobs, and reports accurate updated/skipped/failed counts and reasons.

- Initial connection failures retry automatically with capped backoff and a Retry now button. Each reconnect reloads required catalogs, and the sidebar distinguishes connecting, retrying and offline.

- Opening or reconnecting during a run restores job details, step statuses and logs. Snapshot event boundaries retain newer live updates without duplicating log lines; failed log loads offer Retry.

- Waiting jobs can be unqueued from the selection toolbar or editor without removing their settings or files. Running jobs remain separate from this action.

- Rapid Settings edits build on the current draft and save in order. Older replies cannot roll back newer notification, action, plugin or tool changes; failed writes offer Retry or Discard.

- Starting or indexing a job waits for pending editor saves, including debounced video edits. Failed writes pause later edits and offer Retry or Discard before Start can proceed.

- **Drafts survive navigation.** New jobs and template drafts are retained per browser tab across navigation and refresh. Leaving or replacing an edited template offers Save, Discard or Stay.

- **Validate before publishing.** Muxed candidates pass validation before replacing a finished file. Unmanaged existing outputs default to Stop; the Output tab offers Skip, Rename and Replace. Files appearing or changing during a run are kept, and rejected candidates remain available for inspection.

- **Duplicate imports keep existing jobs.** The match preview links to existing jobs. Replacing one requires selecting “Replace and reset its edits”; busy jobs remain protected.

- **Predictable queue starts.** Start queue runs waiting work only, with its job count shown. Completed, failed and cancelled jobs run again only when explicitly selected with Run selected.

- **Safer work-folder cleanup.** Manual deletion previews paths and sizes and requires confirmation. Records and logs are archived before both manual and automatic cleanup; archive failure keeps the working files. Queue-only removal offers Undo with the job's settings and order preserved.

- **Encoder option help and checks.** The Encoder tab's option names come with suggestions and a line on what each does, read from the encoder's own help. A mistyped option (in the options or the extra arguments) warns with the nearest real name before the run, instead of failing when the encoder starts. A pasted command line (`--ref 4 --bframes 8 --no-sao`) in the new option field adds a row per option. Also fixed: editing an encoder preset in the preset manager closed its Advanced section.

- **Starter encoder presets.** Every encoder preset picker now offers x265 SDR (CRF 20), x265 HDR10 / HDR10+ (CRF 18), x265 Dolby Vision (CRF 18, `--level-idc 5.1`, which fills the VBV Dolby Vision needs) and SVT-AV1 (CRF 30, preset 4), all 10-bit, next to the profile's own defaults. Save a copy to change one.

- **Output file checks.** A job whose output file already exists warns that the run replaces it, and two jobs that would write the same file are blocked until one gets a label, name or folder of its own.

- **Interlaced source warning.** The probe reads MediaInfo's scan type and field order; an interlaced source whose filter chain has no IVTC or deinterlacer warns before the run, and the Video tab shows it.

- **Preset manager dialogs.** Audio and video pickers keep quick selection in a compact popup. Manage presets opens a shared dialog with folder browsing and editable encoder settings, separate Save and Apply actions, and protection for unsaved edits.

- **Audio presets.** Pick common or saved encoder/channel/bitrate configurations on individual audio outputs and template slots/rules. Source-incompatible choices show a reason; saved presets support folders, search, and rename/move while preserving each track's metadata.

- **Grouped encoder presets.** Save named configurations under each encoder with nested folders, search, rename/move, and repeated names across folders. Pick them in job, template, batch, and New jobs editors; selections copy encoder settings while keeping the rest of the setup.

- **Correctness fixes: MP4 subtitles.** Source SRT tracks are extracted and aligned before MP4Box imports them, preserving the final cue's duration and timing when the video starts after zero.

- **Correctness fixes: output color.** VP8, VP9, and AV1 container color tags follow encoder overrides, including range and AV1 HDR mastering/light levels. Manual color options also work with source color disabled.

- **Correctness fixes: quoted arguments.** Encoder, audio, and mux extra arguments use one parser that removes double-quote grouping while preserving Windows paths, empty arguments, and escaped literal quotes.

- **Correctness fixes: edited burn files.** Changing an external subtitle invalidates the video encode and preview. VobSub's `.idx` and `.sub` files are tracked together for extraction, presence, and reuse.

- **Correctness fixes: subtitle burn timing.** Source subtitles and identified external extracts are shifted to the first decoded video frame before rendering. Standalone subtitle files keep their own timing.

- **Correctness fixes: VFR timing.** Extracted timestamps are normalized to the first video frame, keeping audio and subtitles aligned when the source video starts after zero.

- **Correctness fixes: completed files.** Resume and explicit reuse check the completed file's size and modification time. An output replaced or truncated by another job is no longer accepted from an old job record; old records without file stamps are revalidated through the work folder or rebuilt.

- **Job queue.** Queue a job or a batch of episodes (a folder of sources); each runs index → VapourSynth script → x264 / x265 / VP8 / VP9 / SVT-AV1 (1 or 2 passes) → audio → mux → validate. Jobs run one at a time and survive restarts; a rerun skips every step whose command and inputs haven't changed, so a crashed job resumes after its last finished step and a changed subtitle flag only muxes again. A job's audio encodes run alongside its video encode, up to 2 at once by default (Settings → Audio encodes; 0 runs them one by one). A running job shows its step, the encoder's speed (fps) and time left, the time since it started and a guess at the job's time left, in the queue and the job's header.
- **Pause and process priority.** The Queue's Pause suspends the running job's tools and the index lane's, children too (DeeZy's ffmpeg / DEE), until Resume; paused time doesn't count in a step's time or the job's time left. Tools run at StaxRip's priorities: the video encode (the encoder and the vspipe feeding it) below normal, other tools normal (Settings → Process priority, `[pipeline] encoder_priority` / `tool_priority`); the toolbar's gauge menu changes the running ones' for the rest of their run. On Linux it's a nice value.
- **Reuse finished files.** When the jobs you start already have a finished video or audio encode in their work folder (from an earlier run, a job removed and added again, or a variant with another label), Start queue / Run selected asks per file: reuse it (the job is then mostly a mux, as in StaxRip) or make it again. Files made with other settings are offered too, marked and unticked.
- **Work folders.** A job's index, encodes and log live in `<source>_tmp/` next to the source. Settings → Work folders deletes it once the job is done (off by default; the job records and log are copied to the data folder's `records/` first, the newest 100 kept), and Remove → "Remove and delete work folders" deletes the folders of the jobs it removes.
- **Video.** One preview of the script's output, as in VapourSynth Editor, with zoom (100% = one screen pixel per frame pixel, nearest-neighbour from there up), pan and crop lines drawn on the real output (the cropped-off margins stacked back on, so a FillBorders after the crop shows); auto crop; resize as in StaxRip (keep aspect ratio: the height follows the width and each crop, on mod 2/4/8/16, with the aspect error shown; anamorphic sources included, and an encode keeps its pixel aspect via --sar); an anamorphic frame previews at the shape it plays at (the AR toggle shows the stored pixels); an ordered filter chain as in StaxRip (crop and resize are steps in it; each filter can move, switch off or be edited) with one-click presets by category, built on the bundled plugins; the generated VapourSynth script, editable. Source filters: FFMS2 (the default, with index progress), L-SMASH, BestSource. The encode is timed by the script's frame rate (`vspipe --info`), as in StaxRip: an IVTC or a double-rate deinterlace muxes at its own rate and AutoQPF places the chapters by it. A script whose length isn't the source's (a trim, a filter that changes the speed) warns on the Video tab and on the finished job: the source's audio, subtitles and chapters would be out of step. A variable frame rate source (MediaInfo's VFR) keeps its timestamps in an MKV, as in StaxRip (`mkvextract timestamps_v2`, mkvmerge `--timestamps`), while the script keeps every frame; one that doesn't (an IVTC) is muxed at its own constant rate and warns, and an MP4 (MP4Box takes no timestamps) warns that it's muxed at a constant rate.
- **Encoder.** x264 and x265 option panels, 1 or 2 passes; AutoQPF chapters to a qpf file. A 2-pass encode takes a bitrate or a target file size (MB, with StaxRip's DVD / BD sizes to pick): the video gets what the size leaves after the audio, subtitles, attachments, HDR metadata and container overhead, over the script's length (StaxRip's sum). Pass 2 waits for the audio encodes and counts their files; the Encoder tab shows the bitrate and where the size goes, and a size that leaves the video nothing blocks the job. The encode is tagged with the source's colour description (primaries, transfer, matrix, range, chroma location, read by MediaInfo) and on x265 its HDR10 metadata (mastering display, MaxCLL / MaxFALL) with StaxRip's flags alongside it (`--hdr10 --repeat-headers --hrd --aud`, `--range limited` when the source doesn't say, the VBV from `--level-idc`); shown on the Encoder tab, "Colour from the source" switches it off, and an option with the same flag wins (`--no-hrd` and so on). The Video tab names the source's HDR formats: HDR10 / HLG, HDR10+, Dolby Vision with its profile, layers and FEL or MEL (read from a second of its RPU).
- **HDR10+.** An x265 encode of an HDR10+ source carries its dynamic metadata ("HDR10+ from the source" on the Encoder tab, on by default): hdr10plus_tool reads it from the source, x265 writes it (`--dhdr10-info`), in MKV and MP4. A check before the encode stops the job when the script's frames aren't the metadata's (a trim, a frame-rate filter); the output is checked for it. x264 drops it (a warning), an 8-bit encode blocks. MP4 output no longer adds HDR boxes of its own (MP4Box `:hdr=none`): the stream carries the HDR metadata, so MediaInfo lists it once.
- **Dolby Vision.** An x265 encode of a profile 8.1 source (or a profile 7 MEL) carries its Dolby Vision as 8.1 ("Dolby Vision from the source" on the Encoder tab, on by default), in MKV and MP4: dovi_tool reads the RPU, its active area (L5) follows the crop and resize, x265 writes it. Checked like HDR10+ (the script's frames before the encode, 8.1 in the output). It needs a 10-bit encode, `--vbv-maxrate` and `--vbv-bufsize` (x265's rule; with `--level-idc` set, the level's max bitrate fills the ones not set, High tier unless `--no-high-tier`, as StaxRip does) and a mastering display; the job blocks without them. A profile 5 source stays profile 5 (StaxRip's flow: the RPU as it is but for its L5; no HDR10 layer, so no mastering display needed); without its RPU (x264, or unticked) a profile 5 encode's colours look wrong, which warns. Not carried yet: 8.4 (HLG); x264 drops it (a warning).
- **Dolby Vision FEL.** A profile 7 FEL's enhancement layer is baked into the picture (felbaker, now among the bundled plugins) and its RPU goes on as 8.1: the index lane demuxes the layer (dovi_tool), muxes it into an MKV with the source's frame rate and indexes it; the script bakes it right after the source, so the preview shows the baked picture (auto crop reads the base layer). The HDR10 values come from the RPU: the mastering display's luminance, and MaxCLL / MaxFALL from its L1 (else L6, else the source's). A source's HDR10+ is left out of a baked FEL (a warning, as DoVi_Scripts' bake leaves it out): it was measured on the base layer, so it doesn't fit the baked picture, which can be brighter; a MEL keeps it. Needs FFMS2 or L-SMASH (BestSource counts frames differently on such sources: it blocks). A profile 7 whose enhancement layer couldn't be read still blocks. A UHD Blu-ray's own M2TS works too: its enhancement layer is a second video track, which MediaInfo reads as plain HDR10, so the probe reads that track's RPU for the profile and FEL / MEL, and the RPU and the layer come from it (ffmpeg copies the track out, no demux); without dovi_tool such a source warns instead of quietly encoding the base layer alone. The preview now lets go of a job's clips when the job is removed and before the index lane works on its source, so a work folder can be deleted and the layer written again.
- **Notifications.** Settings → Notifications sends to any service Apprise supports (Discord, Telegram, ntfy, Pushover, email, ...): each destination picks its events (job done, failed, cancelled, queue finished), can be switched off, and has a Test button that shows the service's own error.
- **Actions.** Settings → Actions runs things after a job ends or the queue finishes: move or copy the output to a folder (through a `.partial` file; the next actions see the new path), run a command with `{tokens}` (`{output}`, `{record}`, `{label}`, ...; arguments split before the tokens go in, no shell), or POST the event to a webhook. Commands run only when videoforge.toml's `[actions] commands` allows them (off in Docker). Outcomes go in the job's log and `events.jsonl`. See docs/actions.md.
- **Plugins.** Python plugins in `<data dir>/plugins/` (or installed packages' `videoforge.plugins` entry points) get each job's start and end, the queue's end and the index lane's, on a thread of their own, with their own settings (`[plugins.<id>]`), data folder and a line in the job's log. Settings → Plugins lists them, why one didn't load, and switches one off. `niquests` ships for them. See docs/plugins.md and `examples/plugins/library_scan`.
- **Audio.** Copy or encode each track, more than one output from one track: DDP and DDP Atmos (DeeZy + DEE, truehdd), AAC (qaac or ffmpeg), Opus (opusenc or ffmpeg), FLAC, AC-3, E-AC-3 (ffmpeg). Each encode lists its layouts and bitrates, and a setting the track can't take is fitted or blocked.
- **Audio normalize.** StaxRip's ffmpeg modes on every encode but DDP (DEE sets its own dialogue level), in the track's Settings: peak to 0 dB (volumedetect), loudness (EBU R128 loudnorm, two passes: target LUFS, true peak and loudness range, default -24 / -2 / 7 as StaxRip) or dynamic (dynaudnorm). The track is measured after its downmix in a step of its own, beside the video encode; the encode applies what it found. A source wider than the loudness range is compressed to fit (loudnorm's dynamic mode), kept at the source's sample rate.
- **Subtitles.** Keep, leave out, reorder, retitle and flag source subtitles and added SRT files (matched by name or SxxEyy). The Select subtitles menu selects all, deselects all, or keeps only one language or type (PGS, VobSub, SRT, ASS, etc.), with track counts and the job's edited languages.
- **Burn in subtitles.** "Burn in" on a subtitle track (a source track or an added SRT / ASS / SUP / IDX file) draws it into the video with the bundled SubText plugin, as StaxRip's hardcoded subtitle, and leaves it out of the mux; one per job, an encode only. A source track is extracted with the index (mkvextract), so the preview shows it too. Text (SRT, ASS) is drawn after the crop, as in StaxRip; an image subtitle (PGS, VobSub) before it, on the frame it was made for (SubText would stretch it onto the cropped one). A template's subtitle rule can burn in too (the first track it matches). The filter menu's Subtitle category has a "Burn in subtitles" preset for a file of your own (its lines to edit: a `style` for an SRT, say).
- **Containers.** MKV (mkvmerge) and MP4 (MP4Box), each with a warning or a block for what it can't hold. MKV keeps the source's attachments (an ASS subtitle's fonts) and global tags, as StaxRip does. MP4Box starts each track it copies at 0, so a copied track gets its delay to the video, as an encoded one does. MP4 holds a 3-letter ISO 639-2 language (StaxRip writes the same): a region or script warns (es-419 is written as es), and the output check compares the language alone (a Fallout MP4 with es-419, fr-CA, nb and zh-Hant subtitles no longer comes out invalid). Basque, Galician, Kannada and Malayalam are known languages.
- **MP4 and M2TS / TS sources.** A source can be an MKV, MP4 (.mp4, .m4v) or MPEG transport stream (.m2ts, .mts, .ts), indexed straight from the file as in StaxRip. ffprobe (found next to ffmpeg) times it: each track's start as a player starts it (a TS's timestamps, an MP4's edit lists, which MediaInfo doesn't always list), for the audio's delay to the video, copied or encoded, and the exact frame rate (mkvmerge has one for an MKV only). Without ffprobe, MediaInfo's (23.976 taken as 24000/1001). A Blu-ray TrueHD track's AC-3 core is a track of its own (to copy into an MKV or encode; MP4Box can't copy it apart, so MP4 blocks that). MP4 output takes a TS track by its PID and an MP4's by its track ID. mkvextract reads Matroska only: a burned-in subtitle and a VFR source's timestamps are first copied into an MKV in the work folder (mkvmerge), which keeps the TS's timing. When MediaInfo gives a TS no frame rate (an x264 TS) or no chapters (a TS's program menu), AutoQPF takes the script's frame rate and chapters every 5% of the runtime.
- **VP8 / VP9.** Through ffmpeg's libvpx, as StaxRip's ffmpeg encoder does: CRF (`-crf` with `-b:v 0`, 0-63; VP8 `-b:v 100M`, since ffmpeg reads VP8's `-b:v 0` as a 256 kbit/s cap, StaxRip's included), 1-pass bitrate or 2 passes (a target size too), the speed as `-cpu-used` (StaxRip's 0-6 list; VP8 at 4 and up warns: it puts a keyframe on every 2nd-3rd frame after a scene cut), StaxRip's VP9 defaults (`-tile-columns 6 -frame-parallel 1 -auto-alt-ref 1 -lag-in-frames 25`, plus `-row-mt 1`) before the job's `-options`; VP8 is 8-bit only, VP9 8 / 10 / 12-bit. The encode is an IVF that both muxers read as it is; the chapters' keyframes are forced (`-force_key_frames`, from the qpfile); the pixel aspect and the colour the stream doesn't hold (VP9 has only the matrix and the range) are tagged by the mux (`--aspect-ratio-factor`, `--colour-*`; MP4Box `:par`, `:colr`). An HDR10 source's mastering display and light levels aren't carried yet (a warning). The Docker image's FFmpeg now has libvpx (rebuild the plugins image).
- **SVT-AV1.** SvtAv1EncApp, as StaxRip runs it (`tools/SvtAv1EncApp/SvtAv1EncApp.exe`; StaxRip ships Patman86's builds): CRF (`--rc 0 --crf`, 1-70 in quarter steps), 1-pass bitrate or 2 passes (`--rc 1 --tbr`, `--pass`; a target size too), the preset (StaxRip's -1 to 13 list, 4 by default) and tune, 8 or 10-bit, `--progress 2` (whose lines the queue reads, frames a minute included). Two passes add `--undershoot-pct 5` (StaxRip doesn't), unless the options or extra arguments set it: at SvtAv1EncApp's 25 a Fallout sample came in 26% under the bitrate (8 minutes of it, 33%; its own `--passes 2` the same), at 5 within 5.5%. It's told the script's frames (`--frames`, as StaxRip does: from a pipe it doesn't know the length). The source's colour goes in as H.273 code points with the HDR10 mastering display (in plain numbers) and light levels, as StaxRip's SetMetaData writes them; the chapters' keyframes are forced (`--force-key-frames`, CRF only: SvtAv1EncApp refuses them with a bitrate, which warns). The encode is an IVF: the MKV's track is tagged with its pixel aspect, colour and HDR10 (mkvmerge copies none of it from the stream); the MP4 gets `:par` and `:colr`, and MP4Box's mdcv / clli from the stream. HDR10+ and Dolby Vision stay x265's (a warning). The Docker image builds SvtAv1EncApp 4.2.0.
- **Templates.** A job's whole setup without a file: video, crop mode (keep, the template's, detect per job), encoder, container, AutoQPF, audio by position or by rules, subtitles by rules. Star one as the default for new jobs; apply one to a job or a batch.
- **Batch index.** Index jobs in the background while encodes run; a job whose source is on the disk an encode is reading waits, and jobs on other disks go first.
- **Output name and label.** A job's own file name in place of the source's; a label added after it to tell runs of one source apart.
- **Folder browser.** Make folders, and delete them (one with anything in it only once you tick that its contents go too).
- **Logs and job records.** A text log in each job's work folder, an app log per session, and for each output a machine-readable record of how it was made plus a live event stream ([job record format](https://jessielw.github.io/VideoForge/job-record/)). The encoders' and vspipe's progress lines are logged at every 1% of the step (the progress bar sees them all), so a long encode keeps the job's first lines in its log.
- **Settings.** Tool paths with a check for each, folder browser roots, the disk wait, Shut down. The version shows in the sidebar (and `/api/health`).
- **Desktop window.** `serve --window`: the app in its own window with a tray icon; Explorer drops carry file paths.
- **Portable build (Windows x64).** A zip with its own Python: unpack, add the tools, run `VideoForge.exe`. dovi_tool and hdr10plus_tool come with it (`scripts/fetch_tools.py` fetches them for a source install).
- **Docker (Linux, amd64).** The server with the free tools (MKVToolNix, x264, x265, FFmpeg 9, MP4Box, opus-tools, DeeZy, truehdd, dovi_tool, hdr10plus_tool), in a browser. Its x265 is Patman86's mod, built with HDR10+. Windows tools run under Wine from `/tools/wine` (qaac, DEE's Windows build).
- **Bundled VapourSynth plugins.** Source filters (BestSource, L-SMASH-Works, FFMS2, d2vsource) and common filters (EdgeFixer, FillBorders, MVTools, znedi3, dfttest2, BM3D, zsmooth, vszip, fmtconv, descale, ...) plus havsfunc, mvsfunc and awsmfunc, from one list (`vsplugins/manifest.toml`): built from source in the Docker image, downloaded (pinned, checked) for the portable build or a source install (`scripts/fetch_plugins.py`).
- **Profiles.** The built-in `manual` profile; other profiles (a release group's rules) install as separate packages under the `videoforge.profiles` entry point group.

[0.1.0]: https://github.com/jessielw/VideoForge/releases/tag/0.1.0
