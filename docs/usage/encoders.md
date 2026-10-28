# Encoders and HDR

The **Encoder** tab controls the video encoder, rate control, preset, bit depth, structured options,
and additional arguments. It also shows source color and HDR information for the job.

## Encoder choices

| Encoder | Executable | Notes |
| --- | --- | --- |
| x264 | `x264` | H.264 / AVC |
| x265 | `x265` | H.265 / HEVC; supported Dolby Vision and HDR10+ workflows |
| VP8 | `ffmpeg` with libvpx | Intermediate IVF stream |
| VP9 | `ffmpeg` with libvpx-vp9 | Intermediate IVF stream |
| SVT-AV1 | `SvtAv1EncApp` | AV1; intermediate IVF stream |

VideoForge muxes the encoded stream into the chosen MKV or MP4 container. Encoder availability
depends on the tool paths and installed builds; inspect **Settings** if an encoder is unavailable.

## Saved encoder presets

Use **Encoder preset** in a job's Encoder tab, the template editor, or New jobs to select a saved
encoder configuration. The same picker is available when editing selected jobs as a batch.

The compact picker opens with **My presets** and your folders above the built-in configurations,
across all encoders. Select a preset to apply its encoder and settings together. Search by name,
folder, encoder, or settings across the library, or use the **Encoder** filter to narrow the results.
The manager uses the same browser. Choose **Manage presets…** to open the larger editor:

1. Select a preset on the left, or choose **New from current settings**.
2. Edit its name, folder, encoder, quality, speed, and bit depth on the right. Expand
   **Advanced settings and HDR** for structured options, extra arguments, and metadata settings.
3. Choose **Save preset** to update the library, or **Save new preset** to create a copy of a
   built-in configuration. Use `/` in the folder field for nesting, such as `1080p / SDR`.

Saving does not change the current job or template. **Apply encoder settings** applies the edited
configuration and closes the dialog; it does not save library changes. **Cancel** discards the open
draft. Switching presets with unsaved edits offers Save, Discard, or Keep editing.

Names can repeat in different folders or under different encoders. Edit the name or folder in the
manager to rename or move a preset. A new draft matching an existing name, encoder, and folder offers
**Replace preset**; renaming another preset onto it is rejected. Older presets without folders appear
directly under **My presets**.
Use **Duplicate** to create a variation of any selected preset, including its current draft edits.
**New from current settings** also copies the settings and folder open in the editor, with a blank name.

Use **Import** and **Export…** in the manager to share encoder presets as a VideoForge JSON file.
Export one or several saved presets, or choose **Export current settings** to include the open
configuration's unsaved edits, including built-in configurations. Files preserve encoder settings,
names, and nested folders. Import previews the file and lets you choose which presets to add.
Existing presets are kept; a matching name in the same encoder and folder gets a numbered copy.
Importing does not apply settings to jobs or templates. Files support up to 500 presets and 5 MiB.

Built-in choices are marked **profile** (the profile's own defaults) or **starter**. The starters,
all 10-bit:

| Starter | Settings |
| --- | --- |
| x265 SDR | CRF 20, `slow`; HDR10+ and Dolby Vision off |
| x265 HDR10 / HDR10+ | CRF 18, `slow`; Dolby Vision off |
| x265 Dolby Vision | CRF 18, `slow`, `--level-idc 5.1`: the level fills the VBV that Dolby Vision requires |
| SVT-AV1 | CRF 30, preset 4 |

A starter's name says what it is tuned for. Source color and HDR10 metadata are carried whenever
**Colour from the source** is on, whichever preset is picked. Save a starter as your own preset to change it.

Start New jobs with a template, then optionally select an encoder preset. This changes only the
encoder settings; resize, filters, audio, subtitles, and container remain as configured by the template
or job. A folder named `1080p` does not resize video, and a folder named `Dolby Vision` does not
enable metadata preservation: configure those settings explicitly. **Use template settings** clears
the encoder override. Selecting a different template starts with that template's encoder settings.

Templates and jobs keep copies of the applied settings. Updating or deleting a saved preset does
not change them. The picker shows **Custom / modified** when the settings match no available preset.
The encoder's **Speed preset** (`slow`, `slower`, etc.) is separate from these saved configurations.

## Rate control

- **CRF:** select quality and let output size vary with the source.
- **Bitrate:** select an average video bitrate.
- **Two pass:** analyze first, then encode to the selected bitrate or target size, where supported.

Two-pass target size uses **decimal MB**. VideoForge budgets for audio, subtitles, attachments,
HDR metadata, and container overhead before calculating the video bitrate. The Encoder tab shows
the budget for a probed job. Treat the target as a size goal; verify the completed file.

## Options and extra arguments

Structured options and extra arguments are applied after generated defaults. Overrides can change
the color metadata carried by the encoded stream and container. Inspect the generated command
when using advanced flags.

The option name field suggests the names the configured encoder lists in its own help (x264 and x265
`--fullhelp`, SvtAv1EncApp `--help`, ffmpeg's libvpx and codec options) and shows what each one does.
A name the encoder doesn't list, in the options or the extra arguments, shows a warning with the
nearest listed name, and the job gets an `video.option_unknown` warning before it runs. It is a
warning only: some builds take options their help leaves out. Short flags (`-p`) aren't checked.

To add several options at once, paste a command line such as `--ref 4 --bframes 8 --no-sao` into
the new option's name field and press Enter: each option becomes a row (`--name=value` works too),
and an option already in the list takes the new value in place. Short flags and values with no
option before them aren't added; the field names them, for **Extra arguments**.

Values with spaces use double quotes:

```text
--stats "D:\Encode Work\video.stats"
```

Backslashes remain literal except before a double quote. Use `\"` for a literal quote and double
trailing backslashes before a closing quote. Apostrophes and shell operators are literal. This
argument syntax is shared by encoder, audio, and mux extras on Windows and Linux; these fields
do not run a shell.

## HDR10 and color

VideoForge reads source color information and supplies encoder flags because the VapourSynth Y4M
pipe does not carry that information. It also supplies container color tags for IVF-based encoders.
Source tags do not replace the need for correct color processing in a custom script.

## HDR10+ and Dolby Vision

Supported metadata preservation uses **x265** with the relevant option enabled:

| Source | Supported treatment |
| --- | --- |
| HDR10+ | Extract metadata with `hdr10plus_tool` and pass it to x265 |
| Dolby Vision profile 8.1 | Carry as profile 8.1 |
| Dolby Vision profile 7 MEL | Convert to profile 8.1 |
| Dolby Vision profile 7 FEL | Bake the enhancement layer into the picture and carry profile 8.1 metadata |
| Dolby Vision profile 5 | Carry as profile 5 |
| Dolby Vision profile 8.4 (HLG) | Not supported for Dolby Vision preservation |

Dolby Vision requires a **10-bit encode** and x265 VBV values. Set `--vbv-maxrate` and
`--vbv-bufsize`, or use a supported `--level-idc` to fill the missing values. FEL processing uses
FFMS2 or L-SMASH. Crop and resize adjust the RPU's active-area information, and auto crop reads it
(see [Crop and resize](video.md#crop-and-resize)).

Changes to frame count or frame rate can make dynamic metadata incompatible with the output.
Resolve the job's HDR planning issues before starting. Selecting another encoder does not preserve
Dolby Vision metadata; review the warning and intended base-layer output in the editor.
