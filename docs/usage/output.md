# Output and chapters

The job's **Output** tab controls its destination, container, label, chapters, and AutoQPF settings.
Inspect the plan after changing the container or supplying an existing video encode.

## Folder, container, and label

Choose **MKV** or **MP4** and a writable destination. MKV uses MKVToolNix; MP4 uses MP4Box.
An output is written as `<output>.partial` and renamed after muxing completes.

A job label distinguishes outputs made from the same source:

```text
Show.S01E01.mkv
Show.S01E01.dubbed.mkv
Show.S01E01.subbed.mkv
```

The label is part of the output identity and the associated record names. Profiles can also
control the base output name.

Two jobs that would write the same file are both blocked until one gets a label, another output
name, or another folder; a job already queued or running keeps its file. A job whose output file
already exists (and wasn't written by its own last run) warns that the run replaces it.

## Chapters and AutoQPF

Jobs can use source chapters, an added chapter file, or AutoQPF-generated chapters.
AutoQPF generates a chapter file and a QP file so supported encoders place keyframes at chapter
starts. A reused video encode has already chosen its keyframes.

The completed [job record](../job-record.md#chapters) states where the chapters came from.

## Reuse an existing video encode

Add the encode with the source on **New jobs**. The source still supplies the audio, subtitles,
and other source information, while the supplied encode becomes the output video.

Automatic pairing recognizes configured suffixes such as `_job`, `_out`, and `_new`, and matches
TV episodes by their `SxxEyy` token. Raw H.264 / HEVC streams and MKVs without audio can count as
encodes. Inspect the pairing before starting a batch.

Pairing can also read a StaxRip `<source>_temp` folder for its running status and chapter file.
See [configuration](../configuration/settings.md#pairing-settings) for the matching switches.

## Variable frame rate

For a compatible MKV encode, VideoForge carries the source's variable-frame-rate timestamps when
they still fit the output. Frame-changing filters can invalidate that relationship. Check the
resulting timing and any issues when using deinterlacing, decimation, or custom scripts.

## After the run

Validation checks the finished file against the plan. A written file with blocking validation
issues is **invalid**. Preserve its job log and record when investigating.

[Actions](../actions.md) can move or copy a completed output. A move action updates the path seen by
later actions; the original job record still describes the path written by the run.
