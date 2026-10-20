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

You can make more than one output from a source audio track, for example a copied original plus
an encoded compatibility track. Each encoded output is a separate reusable step.

Audio encodes run alongside the video once indexing is complete. **Settings** controls how many
run at once; see [pipeline settings](../configuration/settings.md#pipeline-settings).

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
