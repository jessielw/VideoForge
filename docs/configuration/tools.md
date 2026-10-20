# Tools and VapourSynth plugins

## External tools


Put the tools in `tools/` (git-ignored) as below, or point to them elsewhere: in `videoforge.toml` /
`videoforge.local.toml`, or on the **Settings** page, which shows each path, checks it and reports what's
missing. A bare name (`ffmpeg`, `MP4Box`) is looked up on `PATH`.

| Tool | Default path | Needed for |
| --- | --- | --- |
| [MKVToolNix](https://mkvtoolnix.download/) | `tools/MKVToolNix/mkvmerge.exe` | reading sources, MKV output |
| x264, x265 | `tools/x264/x264.exe`, `tools/x265/x265.exe` | the video encode |
| SvtAv1EncApp (SVT-AV1) | `tools/SvtAv1EncApp/SvtAv1EncApp.exe` | AV1 encodes ([Patman86's builds](https://github.com/Patman86/SVT-AV1-Mods-by-Patman/releases), as StaxRip ships, or [SVT-AV1](https://gitlab.com/AOMediaCodec/SVT-AV1)'s own) |
| VapourSynth plugins | `tools/vs-plugins/` | source filters (FFMS2, the default; L-SMASH; BestSource) and any filters your scripts use: see [VapourSynth plugins](#bundled-vapoursynth-plugins) |
| [MP4Box](https://gpac.io/) (GPAC) | `MP4Box` on `PATH` | MP4 output |
| ffmpeg | `ffmpeg` on `PATH` | FLAC / Opus / AAC / AC-3 / E-AC-3 encodes, and decoding for the other audio encoders |
| ffprobe | next to ffmpeg | an MP4 / TS source's timing (track starts, frame rate); without it, MediaInfo's |
| [DeeZy](https://github.com/jessielw/DeeZy) + Dolby Encoding Engine | `tools/DeeZy/deezy.exe`, `tools/DEE/dee.exe` | DDP / DDP Atmos |
| truehdd | `tools/truehdd/truehdd.exe` | DDP Atmos from TrueHD Atmos |
| qaac | `tools/qaac/qaac64.exe` | AAC (Apple) |
| opus-tools | `tools/opus-tools/opusenc.exe` | Opus (opusenc) |
| [dovi_tool](https://github.com/quietvoid/dovi_tool), [hdr10plus_tool](https://github.com/quietvoid/hdr10plus_tool) | `tools/dovi_tool/dovi_tool.exe`, `tools/hdr10plus_tool/hdr10plus_tool.exe` | Dolby Vision and HDR10+ metadata (`uv run python scripts/fetch_tools.py` downloads both; the portable build and the image have them) |

Only MKVToolNix, an encoder and the source filter plugin are needed to start; the audio tools are only
needed for the encodes that use them (copying a track needs none).

## Bundled VapourSynth plugins

VideoForge bundles a set of plugins and filter scripts, listed in
[vsplugins/manifest.toml](https://github.com/jessielw/VideoForge/blob/main/vsplugins/manifest.toml) with the source and version of each: the portable build
and the Docker image have them. From source, `uv run python scripts/fetch_plugins.py` downloads the Windows
builds into `tools/vs-plugins/` and the single-file scripts into the `.venv`, and `uv sync --extra filters`
installs the packaged scripts.

| For | Plugins (`core.<namespace>`) and scripts |
| --- | --- |
| Source filters | BestSource (`bs`), L-SMASH-Works (`lsmas`), FFMS2 (`ffms2`), d2vsource (`d2v`) |
| Borders | EdgeFixer (`edgefixer`), FillBorders (`fb`), bore (`bore`), `awsmfunc.bbmod` (BalanceBorders) |
| IVTC, deinterlacing | VIVTC (`vivtc`), Bwdif (`bwdif`), znedi3 (`znedi3`), EEDI3m (`eedi3m`), `havsfunc.QTGMC` |
| Denoising | MVTools (`mv`), dfttest2 (`dfttest2_cpu`, through the `dfttest2` module), BM3D (`bm3d`), TTempSmooth (`ttmpsm`), FFT3DFilter (`fft3dfilter`), zsmooth (`zsmooth`), RemoveGrain (`rgvs`), `havsfunc.SMDegrain` |
| Debanding, resizing, formats | vszip (`vszip`: Deband, RFS, EEDI3, Bilateral, masks, ...), fmtconv (`fmtc`), descale (`descale`) |
| Sharpening, anti-aliasing | CAS (`cas`), SangNom (`sangnom`) |
| Misc | MiscFilters (`misc`), Deblock (`deblock`), AddGrain (`grain`), SubText (`sub`) |
| Python | havsfunc (r33), mvsfunc, awsmfunc, vsutil, vs-rekt, adjust, dfttest2 |

All run on the CPU (no GPU filters yet). VapourSynth R81 only loads API 4 plugins, so older ones
(TDeintMod, EEDI2, CTMF, DFTTest, neo_f3kdb, RemapFrames, nnedi3) are left out: dfttest2, vszip's Deband
and RFS, and znedi3 stand in. Plugins of your own go in `tools/vs-plugins/` (`/tools/vs-plugins` in Docker).
