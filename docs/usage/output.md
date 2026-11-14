# Output and chapters

The job's **Output** tab controls its destination, container, label, chapters, and AutoQPF settings. Inspect the plan after changing the container or supplying an existing video encode.

## Folder, container, and label

Choose **MKV** or **MP4** and a writable destination. MKV uses MKVToolNix; MP4 uses MP4Box. Clearing the output folder saves that empty value and blocks the job until a folder is chosen. An output is written as `<output>.partial`, validated, then published. A rejected candidate is kept as `<name>.unpublished-<id>.<container>` for inspection, and the previous finished file stays intact.

A job label distinguishes outputs made from the same source:

```text
Show.S01E01.mkv
Show.S01E01.dubbed.mkv
Show.S01E01.subbed.mkv
```

The label is part of the output identity and the associated record names. Rule sets can also control the base output name. To make such a job, use **Duplicate** on the Queue; see [Duplicate a job](queue.md#duplicate-a-job).

## Name template and suffix

A **name template** builds a release-style name from what the job makes. Tick **Name the file with it** to name the output file, or **Set the MKV title with it** to write the MKV's segment title. Without either, the file keeps the source's name and the MKV has no title. A name typed in **Output name** still wins for the file. An empty template uses the default:

```text
{title} {release_year} {season_episode} {edition} {hybrid} {resolution} {source} {video_dynamic_range_type} {audio_codec} {audio_channel_s} {atmos} {video_codec}
```

```text
MADE IN ABYSS - Journey's Dawn 2019 1080p BluRay Hybrid-REMUX AVC DTS HD MA 5.1 Dual Audio -ZR-.mkv   (source)
MADE IN ABYSS - Journey's Dawn 2019 Hybrid 1080p BluRay DDP 5.1 x264.mkv                               (output)
```

Codec, channel, resolution and HDR tokens describe the output: the first audio track as it is encoded or copied, the job's encoder and bit depth, the HDR and Dolby Vision the encode carries, and the resolution class after the crop and resize (1920x800 is 1080p). Title, year, season and episode, edition, source medium and Hybrid are read from the source's name with [guessit](https://github.com/guessit-io/guessit). The source's own codecs and group tag are never copied. The **Tokens** button lists every token and adds one to the template.

The syntax matches NfoForge's:

| Syntax | Result |
| --- | --- |
| `{token}` | The value. An empty value is dropped along with the extra space. |
| `{:opt=-:token}` | `-` before the value, only when there is a value. `{token:opt=-:}` puts it after. |
| `{:opt= (:release_year:opt=):}` | ` (2019)`, or nothing without a year. |
| `{token\|upper}`, `\|lower`, `\|dots` | Filters. `dots` turns spaces into dots: `{title\|dots}.{release_year}`. |

Any other text stays as typed, so a group tag is just `-GRP` at the end. An unknown token stays as typed and the plan warns (`name.token`). Characters Windows refuses in file names are dropped.

A **name suffix** goes before the extension, after the label: `<name>.<label>.vf.mkv`. It applies with or without the template.

The template, both switches and the suffix are saved in templates. The Output tab shows the resulting file name and title.

**Settings → Jobs → Output names** decides the two switches for all of a rule set's jobs: **As each template says** (the default), **Always on** or **Always off**. A job takes it when it's added or a template is applied to it, so one setting turns template naming off for every template a rule set has, including a plugin's. The job's own Output tab can still change it afterwards, and the Templates page notes when Settings overrides a template's switch. A rule set's built-in defaults can start with naming on; "its defaults" in the list shows which.

## PGS compression

For MKV, **Compress PGS subtitles with zlib** enables lossless compression for all kept PGS tracks, including added `.sup` files. It is off by default: VideoForge explicitly disables PGS compression in mkvmerge. The option is also saved in templates and has no effect on MP4 or other subtitle formats. Changing it only reruns the mux; video and audio encodes can be reused.

Two jobs that would write the same file are both blocked until one gets a label, another output name, or another folder; a job already queued or running keeps its file. A job whose output file already exists warns with the selected **Existing output** policy: Stop (default), Skip, Rename to a numbered filename, or Replace after validation. Verified results from the same job can be reused or replaced on an explicit rerun. A file appearing or changing during the run prevents publication; the candidate is kept for inspection. The CLI offers the same choices with `--existing-output`.

## Chapters and AutoQPF

Jobs can use source chapters, an added chapter file, or AutoQPF-generated chapters. AutoQPF generates a chapter file and a QP file so supported encoders place keyframes at chapter starts. A reused video encode has already chosen its keyframes.

The completed [job record](../job-record.md#chapters) states where the chapters came from.

## Reuse an existing video encode

Add the encode with the source on **New jobs**. The source still supplies the audio, subtitles, and other source information, while the supplied encode becomes the output video.

Automatic pairing recognizes configured suffixes such as `_job`, `_out`, and `_new`, and matches TV episodes by their `SxxEyy` token. Raw H.264 / HEVC streams and MKVs without audio can count as encodes. Inspect the pairing before starting a batch.

Pairing can also read a StaxRip `<source>_temp` folder for its running status and chapter file. See [configuration](../configuration/settings.md#pairing-settings) for the matching switches.

## Variable frame rate

For a compatible MKV encode, VideoForge carries the source's variable-frame-rate timestamps when they still fit the output. Frame-changing filters can invalidate that relationship. Check the resulting timing and any issues when using deinterlacing, decimation, or custom scripts.

## After the run

Validation checks the finished file against the plan. A written file with blocking validation issues is **invalid**. Preserve its job log and record when investigating.

[Actions](../actions.md) can move or copy a completed output. A move action updates the path seen by later actions; the original job record still describes the path written by the run.
