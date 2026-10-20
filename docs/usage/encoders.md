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
FFMS2 or L-SMASH. Crop and resize adjust the RPU's active-area information.

Changes to frame count or frame rate can make dynamic metadata incompatible with the output.
Resolve the job's HDR planning issues before starting. Selecting another encoder does not preserve
Dolby Vision metadata; review the warning and intended base-layer output in the editor.
