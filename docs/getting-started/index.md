# Getting started

Choose an installation, check the tools it needs, and run one job before adding a batch.

## Pick an installation

| Installation | Included | You supply |
| --- | --- | --- |
| [Windows portable](windows.md) | Application, Python, frontend, VapourSynth plugins, HDR metadata tools | MKVToolNix, your video encoder, and any extra audio tools |
| [Docker on Linux](docker.md) | Application, frontend, free media tools, VapourSynth and plugins, Wine | Writable media and data folders; DEE or qaac if you use them |
| [From source](source.md) | Application source | Python 3.12+, uv, Node.js, and media tools |

## Before the first job

1. Open **Settings** and check the paths for MKVToolNix, your encoder, and VapourSynth plugins.
2. Choose a short source in MKV, MP4, or M2TS / TS format.
3. Make sure its folder is writable and has room for an index and intermediate encodes.
4. Follow [Your first job](first-job.md).

The built-in **manual** profile keeps source tracks in source order and copies them unless you
change their settings. Start with that profile and use a separate output folder for the test.

## After a successful test

Save the setup as a [template](../usage/templates.md), add a batch, and use
[batch indexing](../usage/queue.md#batch-indexing) to prepare previews ahead of the encode queue.
