# Templates

A template saves a job setup without its source file. It can include video processing, encoder
settings, container, AutoQPF, crop policy, and optional audio and subtitle selections.

Template drafts survive navigation and refresh in the same browser tab. Leaving an edited template,
switching profiles, or starting another template offers **Save**, **Discard**, or **Stay**.

## Create and apply

1. Configure a test job and check its output.
2. Save its setup as a template, or create one on **Templates**.
3. Choose whether the template should set audio and subtitle selections.
4. Star a template to make it the default for new jobs.
5. Apply it when adding jobs, or to selected jobs in the queue.

Applying a template copies settings into each job. Verify one episode from a batch before running
the rest, especially when the sources differ in resolution, languages, or channel layouts.

Use **Encoder preset** to choose a saved compression configuration while editing a template, or
override just the encoder in New jobs. Presets are organized under each encoder with optional nested
folders; see [saved encoder presets](encoders.md#saved-encoder-presets). Templates store a copy of
the selected settings, so later preset edits do not alter saved templates or queued jobs.

## Share templates

1. On **Templates**, open a setup and choose **Export current template**. This includes any unsaved
   edits, and also works for a profile's built-in defaults. To share several saved templates, choose
   **Export…**, check the ones to include, and click **Export N selected**. All are selected initially;
   use **Clear selection** to start with none or **Select all** to bundle everything.
2. Share the downloaded `.videoforge.json` file with your group.
3. The recipient chooses **Import**, selects the file, and reviews the templates and included scripts.
4. Select the templates to keep and click **Import**. They appear in the template list, ready to edit,
   star, or apply to jobs.

Import creates new saved templates. A matching name gets a numbered copy, such as `Group setup (2)`;
existing templates, current editor drafts, and default selections stay as they are. Files are checked
in full before any templates are saved. Unsupported versions or settings are rejected rather than
silently dropped. A file can contain up to 500 templates and be up to 5 MiB.

The file includes video processing and scripts, crop policy, encoder settings, audio and subtitle
rules, container settings, and AutoQPF. Encoder and audio settings are embedded, so recipients do not
need the sender's saved presets. Source media, external files, installed tools/plugins, profile
packages, and application settings are not bundled. Paths typed into scripts or extra arguments
remain as typed and may need adjusting on the recipient's computer.

Review scripts from shared templates before using them: they contain Python that runs during video
processing. The import preview displays custom bodies and filter scripts, including disabled filters.
Import itself does not execute them. Recipients still need compatible tools, plugins, and profiles.

Exports use a versioned JSON envelope with `format: "videoforge.templates"`, `version: 1`, and a
`templates` array of `{ "name": "…", "data": { … } }` entries. One template and a group bundle use
the same format.

## Crop policy

| Policy | Behavior |
| --- | --- |
| Keep | Retain each job's current crop |
| Fixed | Apply the template's crop to every job |
| Auto | Detect crop separately for each source after it can be read |

Choose Auto for sources whose borders vary. Fixed crop assumes the same border dimensions on every
source. A job using an existing encode has no video to crop.

## Audio by position

Each primary or extra audio output has an **Audio preset** picker for reusable encoder, channels,
bitrate, encoder options, and an optional custom track title. Presets without a custom title keep
the output's title. Flags and the slot's or rule's matching settings stay as they are;
see [audio presets](tracks.md#audio-presets).

Slot 1 applies to the first source audio track, slot 2 to the second, and so on. You can create
several outputs from a slot. Slots beyond the source's tracks are ignored; choose what to do with
tracks beyond the template's slots.

Use position matching only when the source track order is consistent across the batch.

## Audio by rules

Rules can match language, original language, codec, channels, commentary, and audio description.
**The first matching rule wins for each track.** Put specific rules before broad ones, and choose
whether unmatched tracks should be kept or excluded.

Template audio settings are fitted to the actual source. For example, an Atmos choice on a source
without suitable TrueHD Atmos becomes plain DDP; unsupported layouts and bitrates fall back to
compatible values. Manual choices in the job editor remain strict and can block an impossible encode.

## Subtitle rules

Subtitle rules match language, format, forced, SDH, and commentary traits. They cover source tracks
and added subtitle files. As with audio, the first matching rule wins.

A typical policy is forced English first and default, then full English, with other subtitles
excluded. Check the flags and order on several episodes before using it for a season.

## Templates and profiles

A **profile** defines planning rules and output checks in Python. A **template** saves settings
applied to a job. The built-in manual profile plus templates covers ordinary interactive use;
custom release policies can use a [profile package](../development/profiles.md).
