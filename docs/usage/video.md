# Video and filters

The **Video** tab edits the VapourSynth processing used by both preview and encoding. Index the source first, then inspect several frames before running the job.

![The Video tab with frame preview, crop and filters](../assets/screenshots/video.png#only-light) ![The Video tab with frame preview, crop and filters](../assets/screenshots/video-dark.png#only-dark)

## Source filters

| Filter | VapourSynth namespace | Notes |
| --- | --- | --- |
| FFMS2 | `ffms2` | Default; quick indexing |
| L-SMASH-Works | `lsmas` | Alternative source reader |
| BestSource | `bs` | Exact seeking; the first index decodes the whole video |

Select an installed filter under **Advanced**, at the bottom of the side panel. Its title counts the settings there that aren't the default: a filter other than FFMS2, and **Apply pulldown**. Changing the source reader can require a new index. See [Tools and VapourSynth plugins](../configuration/tools.md) if a reader is missing.

### Apply pulldown

Many NTSC DVDs store film as its own 23.976 progressive frames, with pulldown flags telling the player to repeat fields (soft telecine). MediaInfo shows such a source as **Progressive** with a scan order such as **2:3 Pulldown**. By default the source filter gives the stored frames. Some discs mix soft telecine with parts that are telecined for real (credits, effects shots): those parts comb, and the frame rate varies.

**Apply pulldown**, under **Advanced**, repeats the fields as a player does, so the whole source comes out telecined at 29.97 fps. Then **IVTC** matches every part back into 23.976 film frames, the same way. It needs **BestSource** or **L-SMASH Works**: FFMS2 can't apply pulldown flags, and a job with it set on FFMS2 is blocked. BestSource and L-SMASH read the same index with it on or off.

- A source that is soft telecine throughout doesn't need it: its frames are film already. The [field scan](#field-scan)'s **Apply** turns it on with IVTC for any source with pulldown flags, which gives the same film frames either way.
- With it on and no Field filter, the job warns: the telecined frames comb until IVTC matches them.
- With it off on a source with pulldown flags, a chain whose IVTC decimates warns: VDecimate would get the soft-telecined parts as film frames already, and can drop real ones.

## Crop and resize

To go to a frame, type its number in the box under the preview, or a time such as `1:23.5`, `1:02:03` or `83.5s`, and press Enter. The position shows beside it as h:mm:ss.mmm.

Use the frame preview's zoom and crop overlay to inspect borders. **Auto crop** samples the source and proposes crop values. Check bright and dark scenes, credits, and any changing aspect ratios before accepting a fixed crop for the whole file.

For a Dolby Vision source the job carries, auto crop takes the bars from the RPU's L5 active area instead: indexing extracts the RPU too (the encode reuses it). Each side is the smallest bar of the presets in use, so a film whose aspect changes (IMAX scenes) keeps every frame's picture, and the RPU's per-scene presets carry the rest. Presets only in the first or last 1000 frames (a full-frame logo) don't count. An odd bar rounds down: 277 crops 276, and the encode's L5 names the line left. The L5 is checked against the detected borders: where the picture shows more than 4 px inside a bar, that side takes the detected value. An L5 with no bars (or no RPU) leaves the detected borders. The editor (under the button) and the job log say where the crop came from. The crop stays yours to change; the RPU follows any crop.

Resize supports kernels such as Spline36, Bicubic, Lanczos, and Point. Aspect-ratio fitting accounts for the cropped picture and the source's pixel aspect ratio; the output dimensions follow the selected modulus. A custom script can change the picture independently of these controls.

## Filter chain

The chain contains crop and resize steps plus the filters you add. Order affects the picture. VideoForge places new filters by category, with field matching and deinterlacing before crop. Review the chain when combining restoration, denoising, resizing, debanding, and grain.

All bundled filters run on the CPU. Each filter still needs its compatible plugin or Python script. For the shipped set and API compatibility, see the [plugin list](../configuration/tools.md#bundled-vapoursynth-plugins).

## Compare frames

**Compare** on the preview's toolbar (with the Settings panel) shows two versions of the same frames. A choice that isn't available yet says what it needs:

- **Filters:** the script without its filters against the output, to see what a denoise, deband or grain filter does. The "before" side keeps the crop, resize, field filters (IVTC, deinterlacing) and burned-in subtitles, so both sides have the same frames and size. It needs an enabled filter in the chain; a custom script body has no chain to compare.
- **Test encode:** the [test encode](encoders.md#test-encode)'s frames against the script's frames it encoded. The sample's blocks are back to back, so its frame numbers are its own; the label by the buttons says which frame of the script each one is.
- **Encode:** a done job's output file against the script's output.

The two buttons beside it (**Before** / **After**, or **Input** / **Encoded**), or **C**, flip between the sides at the same frame, zoom and scroll; the other side's frame is loaded beside each one, so a flip shows at once. **Split** shows both at once, either side of a line: the picked side on the left. The label by the buttons says which side is which, so nothing covers the frame. Drag the line, or focus it and use ←/→ (Shift for 10%). Boost, zoom and Save work on either side. The encode opens through FFMS2, which indexes it the first time (its index goes in the job's folder). A rerun of the job or of the test encode frees the files the compare holds open.

## Bookmarks

Press **M** in the preview (or the bookmark button under it) to mark the frame, and again to remove the mark. Marks show as ticks on the scrub bar; **[** and **]** (or the buttons either side of the bookmark) go to the previous and next one. They're the same frames in the crop view, the output and every compare; a test encode's compare shows the marks that fall inside its blocks. Bookmarks are kept in this browser, per job, until the job leaves the queue.

## Interlaced sources

When MediaInfo reports the source as interlaced (Interlaced, MBAFF, or PAFF) or with pulldown flags, the Video tab's **Scan** section shows its scan type and field order, and indexing also runs a **field scan** (below). Add **IVTC** for telecined film or a deinterlacer (**QTGMC**, **Bwdif**) from the Field filters, or apply the scan's chain. These filters take the field order from the source, so they follow its top or bottom field first on their own. Their own order setting (`order=`, `field=`, `TFF=`) only counts when the source doesn't give one. If the source is flagged with the wrong order (the preview still combs after IVTC, or motion steps back and forth after deinterlacing), uncomment the step's `SetFieldBased` line: `2` for top field first, `1` for bottom field first. A custom script body is not checked.

### Field scan

MediaInfo says how a source is stored, not what its fields hold: it can't tell telecined film from interlaced video, it calls progressive video stored as fields (PsF) interlaced, and it calls a DVD with pulldown flags progressive even where parts of it comb. The field scan reads every frame after the index, with the pulldown flags applied, and matches each frame's fields at both field orders (VIVTC's VFM). It takes about 20 seconds for a DVD episode and 2 to 3 minutes for a 1080i one. The preview opens as soon as the index is done. For a job indexed before the field scan existed, **Scan fields** in the Scan section puts it back in the index lane.

| Verdict | What it means | The scan's chain |
| --- | --- | --- |
| Progressive | No frame combs (including PsF) | None |
| Telecined film | Film in 3:2 pulldown: field matching leaves next to nothing combed | IVTC: VFM + VDecimate |
| Progressive, fields shifted | Field matching fixes every frame, but not in the 3:2 pattern | VFM alone: no frame is dropped |
| Telecined film with combed parts | Field matching leaves some frames combed (layers telecined out of step, fades, video inserts) | IVTC, with QTGMC Fast on those frames only |
| Interlaced video | Each field is its own moment: frames stay combed after field matching | Bwdif |
| Too little motion to tell | Fewer than 30 frames move | None: check the preview |

The section shows the verdict, a strip of the source (one cell per stretch of time, colored by what field matching does there), how many moving frames field matching leaves combed, and for combed parts the times they are at. The order is the one that leaves less combing; for video, the one Bwdif bobs without jitter. When the stream is flagged with the other order, the section says so.

**Apply** makes the scan's chain the only Field filter, first in the chain, with a `SetFieldBased` line for the order it found. For a source with pulldown flags it also turns on **Apply pulldown**, and moves an FFMS2 job to BestSource (whose index the scan made). On a progressive verdict, Apply removes the Field filters. The note beside the button lists what it changes.

With a verdict, the job's warnings follow the scan instead of MediaInfo:

- No Field filter where the scan found combing.
- A Field filter of the wrong kind: deinterlacing telecined film, field matching interlaced video, VDecimate on a source that repeats no frames, or no deinterlacer for the frames field matching leaves combed.
- A field order the filter would get wrong: the stream's flag, an override line, or (when the source gives no order) the filter's own argument.
- A Field filter on progressive video, which isn't needed.

## Custom VapourSynth code

The editor exposes the generated script; open it with **Edit the whole script…** under **Advanced**, at the bottom of the side panel. Custom processing reads `src` and assigns the result to `clip`. For example, a processing body can start with:

```python
clip = src
clip = core.resize.Spline36(clip, width=1280, height=720)
```

Use the script editor's existing imports and source setup as the starting point. Check preview after changing code. The work folder's `video.vpy` and the [job record](../job-record.md) preserve what ran.

## Burn subtitles into the picture

Choose the subtitle track to burn in the job's subtitle controls. VideoForge uses SubText to render text or image subtitles into the video. A burned subtitle is removed from the muxed subtitle list. This changes the picture permanently and requires video encoding.

For HDR sources, review [Encoders and HDR](encoders.md) before changing resolution, frame count, or color processing.
