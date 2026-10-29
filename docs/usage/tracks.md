# Audio and subtitles

The built-in **manual** profile starts with source tracks in source order, copied with their titles,
languages, and flags. Use the job's **Audio** and **Subtitles** tabs to change the output.

## Select and arrange tracks

1. Exclude tracks you do not want in the output.
2. Reorder retained tracks.
3. Check language, title, and flags such as default, forced, commentary, and hearing impaired.
4. For audio, choose copy or an encode and review its layout and bitrate.
5. Review planning issues after choosing MKV or MP4.

The available controls also depend on the selected profile. A profile can impose its own track
rules instead of offering the full manual editor.

### Name subtitles

**Name subtitles** on the Subtitles tab titles the kept tracks from their language and flags:
`English`, `English (Forced)`, `English (SDH)`, `Spanish (Latin America) (Commentary)`. **Name untitled
tracks** fills only the empty titles; **Rename all kept tracks** replaces every title. Each is an
ordinary title edit, so it can be changed or reset afterwards. Template subtitle rules can do the same
on their own ([Name untitled tracks](templates.md#subtitle-rules)).

## Audio encoders

| Output | Tools |
| --- | --- |
| Copy | No separate audio encoder |
| DDP / DDP Atmos | DeeZy and Dolby Encoding Engine; truehdd for the TrueHD Atmos workflow |
| AAC through qaac | qaac and its required Apple components; ffmpeg for decoding |
| Opus through opusenc | opus-tools; ffmpeg for decoding |
| FLAC, Opus, AAC, AC-3, E-AC-3 through ffmpeg | ffmpeg |

The editor exposes each encoder's supported layouts and bitrates. An Atmos encode requires a
suitable TrueHD Atmos source. Manually chosen settings that cannot be satisfied block the plan.

For **DDP (DEE)**, open the track's **Settings** and select **DDP mode → Standard / Blu-ray**.
Standard is the default. Blu-ray uses DeeZy's `ddp-bluray` encoder, requires a source with at least
eight channels and 7.1 output, and defaults to 1280 kb/s when bitrate is automatic. Bitrate never
switches the mode automatically. The mode is saved with audio presets and template outputs under
**Advanced settings**. When a template is fitted to a source with fewer than eight channels, it
uses Standard DDP and the source's default layout and bitrate.

You can make more than one output from a source audio track, for example a copied original plus
an encoded compatibility track. Each encoded output is a separate reusable step.

### Adjust audio delay

Each audio track has a **Delay** field showing its total delay relative to video in milliseconds:
a positive value plays the track later, a negative one earlier. It starts with the detected source
delay, so a track detected at +24 ms shows **24**. Entering **0** cancels that delay; clearing the
field restores the detected delay. Changes are applied when muxing, so changing Delay does not
encode the track again. A negative value drops the audio before the video's first frame.
A track that ends up more than 2 seconds off the video warns, which often
means the wrong file or a wrong value.

Audio encodes run alongside the video once indexing is complete. **Settings** controls how many
run at once; see [pipeline settings](../configuration/settings.md#pipeline-settings).

## Audio presets

Use **Audio preset** on any audio output to load a saved encoder, channels, bitrate, and encoder
options. Common configurations such as **AC-3 → 5.1 640 kb/s** are available immediately, along
with encoder defaults and Copy. The picker opens with **My presets** and your folders above the
built-in choices, across all encoders. Selecting a preset applies its encoder and settings together.
Search by name, folder, encoder, or settings across the library, or narrow the results with the
optional **Encoder** filter. The preset manager uses the same browser.

1. Open **Audio preset → Manage presets…**. Choose a preset on the left, or **New from current settings**.
2. Set its name, optional folder, encoder, channels, and bitrate on the right. Expand **Advanced
   settings** for normalization, quality controls, and extra arguments supported by that encoder.
3. Choose **Save preset** to update the library, or **Save new preset** to save your own copy of a
   built-in configuration. A folder such as `Surround / Compatibility` creates nested groups.

Saving does not change the output. **Apply to this output** applies the edited configuration and
closes the dialog without saving it to the library. **Cancel** discards the open draft. Rename or move
a preset by editing its name and folder; a new draft with an existing name and folder offers **Replace preset**.
Unsaved changes are checked before switching presets or closing with Escape or the close button.
Use **Duplicate** to create a variation of a selected preset without updating the original.

Audio presets are also available for every primary and extra output in template audio slots and
rules. The same preset name can exist under different encoders or folders. Templates and jobs
keep copies, so editing or deleting a saved preset does not change existing setups.

Audio titles start with each selected source track's title and can be edited. A preset's optional
**Track title** saves a custom output name: a DDP 5.1 preset with the title `Bob` restores `Bob`
whenever selected. Leaving that field blank keeps the output's current title, or its source title
when no custom title has been set. Templates retain custom titles for primary and extra outputs.

Open **Settings → Encoder presets → Manage audio presets** to manage the same library without
a job. **Import**, **Export…**, and **Export current settings** share audio preset JSON files,
including custom titles, encoder options, and folders. Import previews name conflicts and creates
numbered copies instead of replacing saved presets; you can select which entries to import or export.

Applying a preset preserves the track's language, flags, inclusion, timing, and position.
It replaces encoder options rather than keeping options from a previous encoder. Copy clears
encoding settings and copies the source audio.

In the compact picker for an individual track, incompatible choices are disabled with a reason: for example, a 5.1
preset cannot upmix stereo, Atmos needs TrueHD Atmos, and required tools must be installed.
The manager allows editing these presets for other sources, while disabling **Apply to this output**
until they fit the current track. DDP retains its supported 5.0-to-5.1 treatment. Template outputs have no source yet, so their
presets are fitted to each track when applied, following the existing [template audio rules](templates.md#audio-by-rules).

## External files

Add subtitle files with the job. Pairing can also scan beside the source and one folder below it
for SRTs sharing its name or episode token. Review the matched files before running a batch.
Profiles determine whether external subtitles and audio are accepted.

## MKV versus MP4

MKV supports a wider range of tracks. MP4 output uses MP4Box and has container-specific restrictions.
Compatible SRT subtitles become `tx3g` tracks in MP4. Bitmap subtitles and other formats may require
exclusion or burning into the video; resolve the planning issues instead of only changing the extension.

Burned subtitles become part of the picture and are removed from the muxed subtitle list. See
[Video and filters](video.md#burn-subtitles-into-the-picture).

## Reuse choices across a season

Use [template audio and subtitle rules](templates.md) when language or track order changes between
episodes. Set the job's original language when a rule matches **original language**.
