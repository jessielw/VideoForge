"""VideoSettings -> a VapourSynth script. The one generator behind both the preview and the encode.

Layout of every script:

    import vapoursynth as vs
    core = vs.core
    src = <source filter>(<source>, index in the work folder)
    clip = src
    <crop, resize, filters>  or  <custom body>
    <bit depth conversion for the encoder>
    clip.set_output()

`stage="source"` stops after `clip = src` (the crop editor shows the uncropped frame).
"""

from __future__ import annotations

import glob
from pathlib import Path
from typing import Literal

from videoforge.core.video.settings import SourceFilter, VideoSettings

Stage = Literal["source", "output"]


def _q(path: Path | str) -> str:
    return repr(str(path))  # a valid Python string literal for any Windows path


def source_line(source: Path, source_filter: SourceFilter, index_dir: Path) -> str:
    if source_filter is SourceFilter.BESTSOURCE:
        # cachemode 4: always read/write the index at cachepath + track + extension.
        index = index_dir / source.name
        return f"src = core.bs.VideoSource({_q(source)}, cachemode=4, cachepath={_q(index)})"
    if source_filter is SourceFilter.LSMASH:
        return f"src = core.lsmas.LWLibavSource({_q(source)}, cachefile={_q(index_dir / (source.name + '.lwi'))})"
    return f"src = core.ffms2.Source({_q(source)}, cachefile={_q(ffms2_index(source, index_dir))})"


def ffms2_index(source: Path, index_dir: Path) -> Path:
    return index_dir / (source.name + ".ffindex")


def index_exists(source: Path, source_filter: SourceFilter, index_dir: Path) -> bool:
    """Whether the source filter's index is in the work folder (opening the job's video is quick)."""
    if source_filter is SourceFilter.BESTSOURCE:
        return any(index_dir.glob(f"{glob.escape(source.name)}.*.bsindex"))  # + the track number
    if source_filter is SourceFilter.LSMASH:
        return (index_dir / (source.name + ".lwi")).is_file()
    return ffms2_index(source, index_dir).is_file()


def processing_lines(settings: VideoSettings) -> list[str]:
    if settings.custom is not None:
        lines = settings.custom.splitlines()
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        return lines  # as typed (indentation kept), less blank lines at either end
    lines = []
    c = settings.crop
    if not c.is_zero:
        lines.append(f"clip = core.std.Crop(clip, left={c.left}, right={c.right}, top={c.top}, bottom={c.bottom})")
    if settings.resize is not None:
        r = settings.resize
        lines.append(f"clip = core.resize.{r.kernel}(clip, width={r.width}, height={r.height})")
    if settings.filters.strip():
        lines += settings.filters.strip().splitlines()
    return lines


def script_parts(
    settings: VideoSettings, source: Path, index_dir: Path, *, depth: int | None = None, stage: Stage = "output"
) -> tuple[list[str], list[str], list[str]]:
    """The script as (head, body, tail) lines. The body is the part the user edits (crop/resize/filters
    or the custom body); head (imports, source) and tail (depth conversion, output) are generated."""
    head = [
        "import vapoursynth as vs",
        "core = vs.core",
        source_line(source, settings.source_filter, index_dir),
        "clip = src",
    ]
    if stage == "source":
        return head, [], ["clip.set_output()"]
    tail = []
    if depth is not None:
        tail += [
            f"if clip.format.bits_per_sample != {depth}:",
            (
                f"    clip = core.resize.Point(clip, format=clip.format.replace(bits_per_sample={depth}),"
                ' dither_type="error_diffusion")'
            ),
        ]
    tail.append("clip.set_output()")
    return head, processing_lines(settings), tail


def build_script(
    settings: VideoSettings, source: Path, index_dir: Path, *, depth: int | None = None, stage: Stage = "output"
) -> str:
    """The script text. depth converts the output to that bit depth (dithered) when it differs."""
    head, body, tail = script_parts(settings, source, index_dir, depth=depth, stage=stage)
    return "\n".join(head + body + tail) + "\n"
