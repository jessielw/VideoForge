"""VideoSettings -> a VapourSynth script. The one generator behind both the preview and the encode.

Layout of every script:

    import vapoursynth as vs
    core = vs.core
    src = <source filter>(<source>, index in the work folder)
    clip = src
    <a FEL's enhancement layer baked in (bake_lines), when the job bakes one>
    <the filter chain: crop, resize and filters in order>  or  <custom body>
    <a subtitle burned in (burn.lines): before the crop (image) or after it (text); after a custom body>
    <bit depth conversion for the encoder>
    clip.set_output()

`stage="source"` stops after `clip = src` (the uncropped frame, for auto-crop; the base layer only).
`stage="crop"` is the crop editor's view: the output, less a resize after the crop, with the cropped-off
margins stacked back on (vs.crop_view), so the crop lines sit on the uncropped frame's pixels while the
picture between them is the real output. Only the preview worker runs it (it imports VideoForge).
"""

from __future__ import annotations

import glob
from pathlib import Path
from typing import Literal

from videoforge.core.models import SubTrack
from videoforge.core.video import burn as burn_in
from videoforge.core.video.settings import FilterCategory, SourceFilter, VideoSettings

Stage = Literal["source", "crop", "output"]


def _q(path: Path | str) -> str:
    return repr(str(path))  # a valid Python string literal for any Windows path


def source_line(source: Path, source_filter: SourceFilter, index_dir: Path, name: str = "src") -> str:
    if source_filter is SourceFilter.BESTSOURCE:
        # cachemode 4: always read/write the index at cachepath + track + extension.
        index = index_dir / source.name
        return f"{name} = core.bs.VideoSource({_q(source)}, cachemode=4, cachepath={_q(index)})"
    if source_filter is SourceFilter.LSMASH:
        return f"{name} = core.lsmas.LWLibavSource({_q(source)}, cachefile={_q(index_dir / (source.name + '.lwi'))})"
    return f"{name} = core.ffms2.Source({_q(source)}, cachefile={_q(ffms2_index(source, index_dir))})"


def encoded_script(path: Path, index_dir: Path) -> str:
    """A finished encode as a clip (FFMS2, its index in index_dir), for comparing its frames with the script's:
    the job's output, or a test encode's MKV. The file's size and time are in it, so a new encode is a new clip."""
    try:
        st = path.stat()
        stamp = f"# {st.st_size} {st.st_mtime_ns}"
    except OSError:
        stamp = "# missing"
    lines = [
        "import vapoursynth as vs",
        "core = vs.core",
        stamp,
        source_line(path, SourceFilter.FFMS2, index_dir),
        "clip = src",
        "clip.set_output()",
    ]
    return "\n".join(lines) + "\n"


def bake_lines(el: Path, source_filter: SourceFilter, index_dir: Path) -> list[str]:
    """A profile 7 FEL's enhancement layer (el, an MKV) baked into the base layer `clip` (felbaker's fel.Bake,
    StaxRip's lines): the layer at the base layer's size and format, both at 16 bits, baked (12-bit out, limited
    range though the clip says full), the plugin's own frame prop dropped."""
    return [
        source_line(el, source_filter, index_dir, name="_vf_el"),
        "if (_vf_el.width, _vf_el.height, _vf_el.format.id) != (clip.width, clip.height, clip.format.id):",
        "    _vf_el = core.resize.Spline16(_vf_el, width=clip.width, height=clip.height, format=clip.format.id)",
        "if clip.format.bits_per_sample < 16:",
        "    _vf_m = 1 << (16 - clip.format.bits_per_sample)",
        '    clip = core.std.Expr(clip, f"x {_vf_m} *", format=vs.YUV420P16)',
        '    _vf_el = core.std.Expr(_vf_el, f"x {_vf_m} *", format=vs.YUV420P16)',
        "clip = core.fel.Bake(clip, _vf_el, no_resample=1)",
        "clip = core.std.SetFrameProps(clip, _Range=vs.RANGE_LIMITED)",
        'clip = core.std.RemoveFrameProps(clip, props=["_FelBaker_YccToRGB"])',
    ]


def ffms2_index(source: Path, index_dir: Path) -> Path:
    return index_dir / (source.name + ".ffindex")


def index_exists(source: Path, source_filter: SourceFilter, index_dir: Path) -> bool:
    """Whether the source filter's index is in the work folder (opening the job's video is quick)."""
    if source_filter is SourceFilter.BESTSOURCE:
        return any(index_dir.glob(f"{glob.escape(source.name)}.*.bsindex"))  # + the track number
    if source_filter is SourceFilter.LSMASH:
        return (index_dir / (source.name + ".lwi")).is_file()
    return ffms2_index(source, index_dir).is_file()


def processing_lines(
    settings: VideoSettings, *, crop_view: bool = False, burn: SubTrack | None = None, work: Path | None = None
) -> list[str]:
    """The body's lines. crop_view keeps the clip before the crop (`_vf_pre`), leaves out a resize after
    it and ends with the crop view (see the module docstring). burn: a subtitle track drawn on the video, its
    file in (or extracted to) work."""
    sub = burn_in.lines(burn, work or Path()) if burn is not None else []
    if settings.custom is not None:
        lines = settings.custom.splitlines()
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        return lines + sub  # as typed (indentation kept), less blank lines at either end
    lines = []
    c, r = settings.crop, settings.resize
    cropped = False
    image = burn is not None and burn_in.is_image(burn)
    for step in settings.filters:
        if step.category is FilterCategory.CROP:
            if image:
                lines += sub
            if crop_view:
                lines.append("_vf_pre = clip")
                cropped = True
            if not c.is_zero:
                lines.append(
                    f"clip = core.std.Crop(clip, left={c.left}, right={c.right}, top={c.top}, bottom={c.bottom})"
                )
            if not image:
                lines += sub
        elif step.category is FilterCategory.RESIZE:
            if r is not None and not cropped:
                lines.append(f"clip = core.resize.{r.kernel}(clip, width={r.width}, height={r.height})")
        elif step.enabled and step.script.strip():
            lines += step.script.strip().splitlines()
    if cropped:
        lines += [
            "from videoforge.core.video.vs import crop_view as _vf_crop_view",
            f"clip = _vf_crop_view(_vf_pre, clip, left={c.left}, top={c.top}, right={c.right}, bottom={c.bottom})",
        ]
    return lines


def script_parts(
    settings: VideoSettings,
    source: Path,
    index_dir: Path,
    *,
    depth: int | None = None,
    stage: Stage = "output",
    el: Path | None = None,
    burn: SubTrack | None = None,
) -> tuple[list[str], list[str], list[str]]:
    """The script as (head, body, tail) lines. The body is the part the user edits (the filter chain
    or the custom body); head (imports, source, a FEL's bake when el is given) and tail (depth conversion,
    output) are generated. burn: a subtitle track burned in (its lines join the body)."""
    head = [
        "import vapoursynth as vs",
        "core = vs.core",
        source_line(source, settings.source_filter, index_dir),
        "clip = src",
    ]
    if stage == "source":
        return head, [], ["clip.set_output()"]
    if burn is not None and (stamp := burn_in.external_stamp(burn)):
        head.append(stamp)
    if el is not None:
        head += bake_lines(el, settings.source_filter, index_dir)
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
    return head, processing_lines(settings, crop_view=stage == "crop", burn=burn, work=index_dir), tail


def build_script(
    settings: VideoSettings,
    source: Path,
    index_dir: Path,
    *,
    depth: int | None = None,
    stage: Stage = "output",
    el: Path | None = None,
    burn: SubTrack | None = None,
) -> str:
    """The script text. depth converts the output to that bit depth (dithered) when it differs; el is a FEL's
    enhancement layer to bake in; burn a subtitle track to burn in."""
    head, body, tail = script_parts(settings, source, index_dir, depth=depth, stage=stage, el=el, burn=burn)
    return "\n".join(head + body + tail) + "\n"
