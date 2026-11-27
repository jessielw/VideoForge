# Interlaced and telecined sources

A source stored as fields needs the right treatment before it's encoded, or the output combs (fine horizontal lines on anything that moves). Which treatment depends on what the fields hold, not on how the file is stored:

| Source | What its fields hold | Treatment |
| --- | --- | --- |
| Progressive, stored as fields (PsF) | Both fields of a frame are the same moment | None |
| Telecined film or animation | 23.976 fps film spread over 29.97 fps fields in a 3:2 pattern | **IVTC**: match the fields back into the film frames and drop the repeats |
| Soft telecine (pulldown flags) | The film frames themselves, with flags telling a player to repeat fields | None, unless parts of it are telecined for real (see [below](#soft-telecine)) |
| Interlaced video | Each field is its own moment, 59.94 (or 50) per second | A **deinterlacer** (Bwdif, QTGMC) |

The wrong tool costs quality. A deinterlacer on telecined film guesses at lines that IVTC gets back whole, and keeps the repeated frames. IVTC on interlaced video can't match fields that were never one frame, and VDecimate then drops real motion.

MediaInfo can't tell these apart. It says how a source is stored, so it calls telecined film and interlaced video alike interlaced, calls PsF interlaced, and calls a soft-telecined DVD "Progressive" even where parts of it comb. VideoForge's **field scan** looks at the frames instead.

## Field scan

When MediaInfo reports the source as interlaced (Interlaced, MBAFF, or PAFF) or with pulldown flags, the index lane scans its fields after the index. The scan reads every frame, with the pulldown flags applied, and matches each frame's fields at both field orders (VIVTC's VFM). It takes about 20 seconds for a DVD episode and 2 to 3 minutes for a 1080i one.

Once the index is done, the job shows **Scanning fields**. The preview opens and the job can be edited while the scan runs, but the job can only be queued after the scan. A test encode asked for meanwhile starts when the scan ends. **Stop indexing** stops the scan too. For a job indexed before the field scan existed, **Scan fields** in the Video tab's **Scan** section puts it back in the index lane. Each source is scanned once: other jobs on it (labels, copies) use the same scan, and changing the source filter doesn't scan again.

### Verdicts

| Verdict | What it means | The scan's chain |
| --- | --- | --- |
| Progressive | No frame combs (including PsF) | None |
| Telecined film | Film in 3:2 pulldown: field matching leaves next to nothing combed | IVTC: VFM + VDecimate |
| Progressive, fields shifted | Field matching fixes every frame, but not in the 3:2 pattern | VFM alone: no frame is dropped |
| Telecined film with combed parts | Field matching leaves some frames combed (layers telecined out of step, fades, video inserts) | IVTC, with QTGMC Fast on those frames only |
| Interlaced video | Each field is its own moment: frames stay combed after field matching | Bwdif |
| Too little motion to tell | Fewer than 30 frames move | None: check the preview |

The **Scan** section shows the verdict, a strip of the source (one cell per stretch of time, colored by what field matching does there), how many moving frames field matching leaves combed, and for combed parts the times they are at. The field order is the one that leaves less combing; for video, the one Bwdif deinterlaces without jitter. When the stream is flagged with the other order, the section says so.

### Apply

**Apply** makes the scan's chain the only Field filter, first in the chain. For a source with pulldown flags it also turns on [Apply pulldown](video.md#apply-pulldown), and moves an FFMS2 job to BestSource (whose index the scan made). On a progressive verdict, Apply removes the Field filters. The note beside the button lists what it changes. Apply is off for a job with a custom script body.

The chains, for a top-field-first source:

```python
# Telecined film
clip = core.std.SetFieldBased(clip, 2)  # the field order the scan found: 2 top first, 1 bottom first
clip = core.vivtc.VFM(clip, order=1)
clip = core.vivtc.VDecimate(clip)

# Progressive, fields shifted: the same without VDecimate

# Telecined film with combed parts: QTGMC only on the frames VFM leaves combed
import havsfunc
clip = core.std.SetFieldBased(clip, 2)
fallback = havsfunc.QTGMC(clip, TFF=True, Preset='Fast', FPSDivisor=2)
clip = core.vivtc.VFM(clip, order=1)
clip = core.std.FrameEval(clip, lambda n, f, matched=clip: fallback if f.props['_Combed'] else matched, prop_src=clip)
clip = core.vivtc.VDecimate(clip)

# Interlaced video
clip = core.std.SetFieldBased(clip, 2)
clip = core.bwdif.Bwdif(clip, field=1)
```

The QTGMC fallback needs `havsfunc` from the filters extra, as the QTGMC presets do.

A [template](templates.md#field-policy) with **Field: Scan per job** applies each job's own chain once its scan is done, so one template fits a season that mixes telecined and interlaced episodes.

### Warnings

With a verdict, the job's warnings follow the scan instead of MediaInfo:

- No Field filter where the scan found combing.
- A Field filter of the wrong kind: deinterlacing telecined film, field matching interlaced video, VDecimate on a source that repeats no frames, or no deinterlacer for the frames field matching leaves combed.
- A field order the filter would get wrong: the stream's flag, an override line, or (when the source gives no order) the filter's own argument.
- A Field filter on progressive video, which isn't needed.

Without a verdict (no scan yet, or too little motion), MediaInfo's warning stays: the source is stored as fields, add IVTC or a deinterlacer unless the preview shows no combing. A custom script body isn't checked.

## When to choose otherwise

The scan's chain is a starting point. Check a few frames in the preview, especially fades, credits and fast motion, and choose by hand where the source needs it. A Field filter you choose by hand stays; the warnings only say where it disagrees with the scan.

- **Too little motion to tell.** A short clip, a menu, a slideshow. Step through the frames that move: combing that IVTC removes means telecine, combing that stays means video.
- **Live-action interlaced video.** Bwdif is the scan's choice: it is fast, and on animation woven into interlaced video it scored as well as QTGMC frame by frame. QTGMC is 9 to 33 times slower, but can keep fine detail steadier from one frame to the next on camera video, which a per-frame score doesn't show. If detail shimmers in a test encode, try **QTGMC Fast** or **QTGMC Medium**.
- **A mix of film and video.** A source that is mostly film with some video (a few inserts, scrolling credits) scans as film with combed parts: the video parts become 23.976 fps, with QTGMC on their combed frames. One that is about half video scans as interlaced and gets Bwdif throughout, because decimating the video parts would drop real motion. The strip shows which parts are which.
- **PAL conversions of NTSC material** with blended fields (common on PAL TV and anime DVDs). Neither IVTC nor a deinterlacer gets the original frames back: deinterlacing leaves ghosted frames. They need a blend-restoring filter (sRestore and similar), which isn't bundled; add it as a custom step.
- **Thin combing.** VFM decides per block, so a thin line fading in or out can comb below its threshold and count as clean. Look at fades and credits.
- **The wrong field order.** The scan's chain sets the order it found. If the preview still combs after IVTC, or motion steps back and forth after deinterlacing, change the `SetFieldBased` line's `2` (top field first) to `1` (bottom field first), or the other way.

## Field order

The Field presets (**IVTC**, **QTGMC**, **Bwdif**) take the field order from the source, so they follow its top or bottom field first on their own. Their own order setting (`order=`, `field=`, `TFF=`) only counts when the source doesn't give one. If the source is flagged with the wrong order, uncomment the preset's `SetFieldBased` line: `2` for top field first, `1` for bottom field first. The scan's chains always have that line, set to the order the scan found.

## Soft telecine

Many NTSC DVDs store film as its own 23.976 progressive frames with pulldown flags (soft telecine), and some mix it with parts that are telecined for real, such as credits and effects shots. By default the source filter gives the stored frames, so those parts comb and the frame rate varies. [Apply pulldown](video.md#apply-pulldown) repeats the fields as a player does, so the whole source is telecined at 29.97 fps and IVTC matches every part back into film frames. The field scan always scans with the flags applied, and its Apply turns Apply pulldown on with any chain for a source with flags.

## What can't be fixed

Some frames can't come out clean at 23.976 fps, however they are treated. When two layers are telecined out of step (credits over animation), field matching matches whole frames, so one layer always stays combed. A credit fading at 59.94 fps has moments no 23.976 frame holds. On those frames the fallback rebuilds the missing field with QTGMC, which is clean but softer than a matched frame. The scan lists them under the frames left combed. Keeping those stretches at 29.97 fps (variable frame rate output) isn't supported.

## In the job record

The [job record](../job-record.md) keeps the source's field scan: the verdict, the field order, the counts, the strip, the frames left combed, and whether the job ran with the scan's chain.
