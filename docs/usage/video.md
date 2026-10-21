# Video and filters

The **Video** tab edits the VapourSynth processing used by both preview and encoding. Index the
source first, then inspect several frames before running the job.

## Source filters

| Filter | VapourSynth namespace | Notes |
| --- | --- | --- |
| FFMS2 | `ffms2` | Default; quick indexing |
| L-SMASH-Works | `lsmas` | Alternative source reader |
| BestSource | `bs` | Exact seeking; the first index decodes the whole video |

Select an installed filter. Changing the source reader can require a new index.
See [Tools and VapourSynth plugins](../configuration/tools.md) if a reader is missing.

## Crop and resize

Use the frame preview's zoom and crop overlay to inspect borders. **Auto crop** samples the source
and proposes crop values. Check bright and dark scenes, credits, and any changing aspect ratios
before accepting a fixed crop for the whole file.

Resize supports kernels such as Spline36, Bicubic, Lanczos, and Point. Aspect-ratio fitting accounts
for the cropped picture and the source's pixel aspect ratio; the output dimensions follow the
selected modulus. A custom script can change the picture independently of these controls.

## Filter chain

The chain contains crop and resize steps plus the filters you add. Order affects the picture.
VideoForge places new filters by category, with field matching and deinterlacing before crop.
Review the chain when combining restoration, denoising, resizing, debanding, and grain.

All bundled filters run on the CPU. Each filter still needs its compatible plugin or Python script.
For the shipped set and API compatibility, see the [plugin list](../configuration/tools.md#bundled-vapoursynth-plugins).

## Interlaced sources

When MediaInfo reports the source as interlaced (Interlaced, MBAFF, or PAFF), the Video tab shows
its scan type and field order. A job whose chain has no enabled Field filter warns before the run.
Add **IVTC** for telecined film or a deinterlacer (**QTGMC**, **Bwdif**) and set its field order
to match. Some progressive video is stored as interlaced: if the preview shows no combing, the
warning can be ignored. A custom script body is not checked.

## Custom VapourSynth code

The editor exposes the generated script. Custom processing reads `src` and assigns the result to
`clip`. For example, a processing body can start with:

```python
clip = src
clip = core.resize.Spline36(clip, width=1280, height=720)
```

Use the script editor's existing imports and source setup as the starting point. Check preview after
changing code. The work folder's `video.vpy` and the [job record](../job-record.md) preserve what ran.

## Burn subtitles into the picture

Choose the subtitle track to burn in the job's subtitle controls. VideoForge uses SubText to render
text or image subtitles into the video. A burned subtitle is removed from the muxed subtitle list.
This changes the picture permanently and requires video encoding.

For HDR sources, review [Encoders and HDR](encoders.md) before changing resolution, frame count,
or color processing.
