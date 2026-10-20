---
description: A browser-based encode and mux queue for Windows and Docker, powered by VapourSynth.
---

# VideoForge

**Turn a source file or a season of episodes into an encode and mux queue.**

VideoForge combines VapourSynth processing, video and audio encoding, subtitle selection, and
MKV or MP4 output in one local application. Set up each job in your browser, or use the Windows
desktop window. Jobs survive restarts, and completed encodes can be reused.

[Get started](getting-started/index.md){ .md-button .md-button--primary }
[Create your first job](getting-started/first-job.md){ .md-button }

!!! note "Beta software"
    VideoForge is currently **0.1.0 beta**. Expect changes. Read the
    [changelog](reference/changelog.md) before updating.

## Choose your starting point

| You want to… | Start here |
| --- | --- |
| Run on Windows without installing Python | [Windows portable](getting-started/windows.md) |
| Run in a Linux container | [Docker](getting-started/docker.md) |
| Run or develop from a checkout | [From source](getting-started/source.md) |
| Encode your first file | [Your first job](getting-started/first-job.md) |
| Reuse settings across episodes | [Templates](usage/templates.md) |
| Fix a failed job | [Troubleshooting](reference/troubleshooting.md) |

## The workflow

```text
Source → Index → VapourSynth → Video encode ─┐
                 Audio copy or encode ──────┼→ Mux → Validate
                 Subtitles and chapters ────┘
```

- **Video:** crop, resize, CPU filters, editable VapourSynth scripts, x264, x265, VP8, VP9, and SVT-AV1.
- **Tracks:** copy or encode audio, make several outputs from one track, select subtitles, and set titles and flags.
- **Queue:** batch indexing, pause and resume, per-step reuse, and persistent job settings.
- **Automation:** templates, notifications, command and webhook actions, and Python plugins.

## Current boundaries

Sources are **MKV, MP4, and M2TS / TS**. Remux other containers to MKV before adding them.
Filters run on the CPU. VideoForge is a single-user application and has no login.
The [Docker guide](getting-started/docker.md#network-access) explains how to keep access local.

Dolby Vision and HDR10+ processing is available for supported x265 workflows; profile 8.4 (HLG)
is not supported. See [Encoders and HDR](usage/encoders.md).

## Project

[Source code](https://github.com/jessielw/VideoForge) ·
[Releases](https://github.com/jessielw/VideoForge/releases) ·
[Report an issue](https://github.com/jessielw/VideoForge/issues) ·
[MIT license](https://github.com/jessielw/VideoForge/blob/main/LICENSE)
