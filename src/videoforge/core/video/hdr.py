"""A source's dynamic HDR metadata: Dolby Vision and HDR10+ (MediaInfo), a profile 7 enhancement layer's
kind (FEL or MEL, which MediaInfo can't tell) from a second of its RPU, and carrying both into an x265
encode.

The FEL / MEL read is dv_check's (StaxRip's "dv_check" folder): a second of the video stream from 10 s in,
through dovi_tool extract-rpu, then `dovi_tool info -f 0` on its first frame for `el_type`.

HDR10+ (as StaxRip does it): `ffmpeg ... -f hevc - | hdr10plus_tool extract -o hdr10plus.json -` into the
work folder, then x265 `--dhdr10-info hdr10plus.json`. The JSON has one entry per frame of the source, so
the script must give the same frames: a check step compares them before the encode (a trim, a frame-rate
filter or a source filter counting frames its own way would put the metadata out of step).

Dolby Vision (profile 8.1, and a profile 7 MEL as 8.1; StaxRip's flow): `ffmpeg ... | dovi_tool extract-rpu`
writes the source's RPU to the work folder. An edit step moves its L5 active area (the letterbox offsets) by
the job's crop and resize (DoviCrop's: `dovi_tool export`, each offset less the crop, at least 0) and makes it
profile 8.1 (`dovi_tool editor`, mode 2); a check compares its frames with the script's, as for HDR10+; x265
writes it (`--dolby-vision-profile 8.1 --dolby-vision-rpu`). x265 needs VBV for it (HRD; with only
`--level-idc` set, the level's max bitrate fills it, as StaxRip does), a 10-bit encode and a mastering display.
Profile 5 (StaxRip's too) stays profile 5: its base layer is IPTPQc2, not HDR10 (no mastering display; x265
writes its own colour signalling), and the edit leaves the RPU as it is but for the L5 (mode 0). 8.4 (HLG) isn't
carried yet.

A profile 7 FEL's enhancement layer is baked into the picture (StaxRip's flow, felbaker's fel.Bake): the index
lane demuxes it (`dovi_tool demux --el-only`), muxes it into an MKV with the source's frame duration (so the
source filter can seek it) and indexes it; the script's head bakes it into the base layer right after the
source (script.bake_lines), and the RPU goes on as above. The HDR10 SEI then comes from the RPU, as
Parse-Fel-Master-Data and DoVi_Scripts do it (fel_color): the mastering display's luminance from "RPU
mastering display" and MaxCLL / MaxFALL from the whole RPU's L1 (measured on the reconstructed picture, which
can be brighter than the base layer), else L6, else the source's.
"""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
import functools
import json
import logging
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any

from videoforge.core.config import Tools
from videoforge.core.execute.process import LogFn, ToolError, run
from videoforge.core.models import Issue, Severity, SourceInfo, VideoColor, VideoHdr, VideoInfo
from videoforge.core.tools import locate
from videoforge.core.video.encoders import level_vbv
from videoforge.core.video.settings import Encoder, EncoderSettings, FilterCategory, SourceFilter, VideoSettings

logger = logging.getLogger(__name__)

# In the work folder
HDR10PLUS_JSON = "hdr10plus.json"
DV_SOURCE_RPU = "dv_source.bin"  # the source's RPU
DV_RPU = "dv_rpu.bin"  # the encode's: cropped, resized, profile 8.1 (or 5)
DV_EL_HEVC = "dv_el.hevc"  # a FEL's enhancement layer, as demuxed
DV_EL = "dv_el.mkv"  # the same in an MKV, which the source filter opens
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
# vspipe --info's and dovi_tool info -s's; process.run tags lines "[vspipe] "
_FRAMES = re.compile(r"(?:^|\] )\s*Frames:\s*(\d+)", re.MULTILINE)
_L5 = ("left", "right", "top", "bottom")
_PROFILE = re.compile(r"Profile (\d+)(?:\.(\d+))?")
_DVHE = re.compile(r"\b(?:dvhe|dvh1|dvav|dva1|dav1)\.(\d+)", re.IGNORECASE)
# dovi_tool info -s: "RPU mastering display: 0.0050/4000 nits", "RPU content light level (L1): MaxCLL: 0.01 nits,
# MaxFALL: 0.00 nits", "L6 metadata: Mastering display: 0.0050/4000 nits. MaxCLL: 2573 nits, MaxFALL: 684 nits"
_RPU_DISPLAY = re.compile(r"RPU mastering display:\s*([\d.]+)/([\d.]+) nits")
_RPU_L1 = re.compile(r"RPU content light level[^:]*:\s*MaxCLL:\s*([\d.]+) nits,\s*MaxFALL:\s*([\d.]+) nits")
_RPU_L6 = re.compile(r"L6 metadata:.*?MaxCLL:\s*([\d.]+) nits,\s*MaxFALL:\s*([\d.]+) nits")


def _parts(track: Any, name: str) -> list[str]:
    """A MediaInfo field with one value per HDR format ("Dolby Vision / SMPTE ST 2086"), split."""
    value = getattr(track, name, None)
    return [p.strip() for p in str(value).split(" / ")] if value else []


def _at(values: list[str], index: int) -> str:
    return values[index] if index < len(values) else ""


def from_mediainfo(track: Any) -> VideoHdr:
    """A MediaInfo video track's Dolby Vision profile, compatibility, level and layers, and HDR10+."""
    if track is None:
        return VideoHdr()
    formats = _parts(track, "hdr_format")
    hdr10plus = any("2094 App 4" in f for f in formats) or any(
        "HDR10+" in c for c in _parts(track, "hdr_format_commercial")
    )
    dv = next((n for n, f in enumerate(formats) if f.startswith("Dolby Vision")), None)
    if dv is None:
        return VideoHdr(hdr10plus=hdr10plus)
    other = getattr(track, "other_hdr_format", None) or []
    text = _at([str(o) for o in other], 0).split(" / ")[0] if other else ""
    profile, compat = 0, None
    if m := _PROFILE.search(text):  # "Dolby Vision, Version 1.0, Profile 7.6, dvhe.07.06, BL+EL+RPU, ..."
        profile, compat = int(m.group(1)), int(m.group(2)) if m.group(2) else None
    elif m := _DVHE.search(_at(_parts(track, "hdr_format_profile"), dv)):  # "dvhe.07"
        profile = int(m.group(1))
    level = _at(_parts(track, "hdr_format_level"), dv)
    return VideoHdr(
        dv_profile=profile,
        dv_compat=compat,
        dv_level=int(level) if level.isdigit() else 0,
        dv_layers=_at(_parts(track, "hdr_format_settings"), dv),
        hdr10plus=hdr10plus,
    )


def video_stream_argv(ffmpeg: str, source: Path, *, start_s: float = 0, seconds: float = 0) -> list[str]:
    """ffmpeg writing the source's first video stream as raw HEVC (Annex B) to stdout, as dovi_tool and
    hdr10plus_tool read it (StaxRip's command); start_s / seconds take a part of it."""
    argv = [ffmpeg, "-hide_banner", "-loglevel", "error", "-analyzeduration", "100M", "-probesize", "50M"]
    argv += ["-ss", f"{start_s:g}"] if start_s else []
    argv += ["-i", str(source)]
    argv += ["-t", f"{seconds:g}"] if seconds else []
    return [*argv, "-map", "0:v:0", "-c:v:0", "copy", "-bsf:v", "hevc_mp4toannexb", "-f", "hevc", "-"]


def rpu_info(dovi_tool: str, rpu: Path, frame: int = 0) -> dict[str, Any]:
    """`dovi_tool info -f N` of an RPU file: that frame's RPU as JSON (dovi_profile, el_type, header, ...)."""
    out = subprocess.run(
        [dovi_tool, "info", "-f", str(frame), "-i", str(rpu)],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        creationflags=_NO_WINDOW,
    )
    start = out.stdout.find("{")  # after "Parsing RPU file..."
    if out.returncode != 0 or start < 0:
        raise ToolError(f"dovi_tool info failed: {(out.stderr or out.stdout).strip()[-300:]}", out.returncode)
    return json.loads(out.stdout[start:])


def read_el_type(source: Path, tools: Tools) -> str:
    """ "FEL" or "MEL" for a profile 7 source, from a second of its RPU (10 s in, or the start of a shorter
    file); "" when it can't be read. Cached per file, size and mtime."""
    try:
        st = source.stat()
    except OSError:
        return ""
    return _el_type(str(source), st.st_size, st.st_mtime_ns, tools.ffmpeg, tools.dovi_tool)


@functools.lru_cache(maxsize=64)
def _el_type(source: str, _size: int, _mtime: int, ffmpeg: str, dovi_tool: str) -> str:
    with tempfile.TemporaryDirectory(prefix="vf_dv_") as tmp:
        rpu = Path(tmp) / "sample.bin"
        for start in (10, 0):
            dovi = [dovi_tool, "extract-rpu", "-", "-o", str(rpu)]
            try:
                run([video_stream_argv(ffmpeg, Path(source), start_s=start, seconds=1), dovi], lambda _line: None)
                if rpu.is_file() and os.path.getsize(rpu) > 0:
                    return str(rpu_info(dovi_tool, rpu).get("el_type") or "")
            except (OSError, ToolError, ValueError) as ex:
                logger.info("%s: no RPU sample from %s s: %s", Path(source).name, start, ex)
    return ""


def keeps_hdr10plus(video: VideoInfo | None, settings: EncoderSettings) -> bool:
    """Whether the encode carries the source's HDR10+: x265, the source has it, and the job didn't untick it."""
    return video is not None and video.hdr.hdr10plus and settings.hdr10plus and settings.encoder is Encoder.X265


def keeps_dv(video: VideoInfo | None, settings: EncoderSettings) -> bool:
    """Whether the encode carries the source's Dolby Vision: x265, a profile 5, 7 or 8 source, and the job didn't
    untick it (issues() blocks the ones it can't carry yet)."""
    return (
        video is not None
        and video.hdr.dv_profile in (5, 7, 8)
        and settings.dolby_vision
        and settings.encoder is Encoder.X265
    )


def dv_profile(video: VideoInfo | None) -> str:
    """The profile the encode's Dolby Vision is written as (x265's --dolby-vision-profile): 5 for a profile 5
    source, 8.1 for the others (a profile 7 MEL or FEL, 8.1), as StaxRip writes them."""
    return "5" if video is not None and video.hdr.dv_profile == 5 else "8.1"


# MediaInfo's (profile, compatibility) of each written profile
_DV_FOUND = {"5": (5, None), "8.1": (8, 1)}
# dovi_tool's editor mode per written profile: 0 leaves the RPU as it is, 2 makes it 8.1 (StaxRip's)
_DV_MODES = {"5": 0, "8.1": 2}


def bakes_fel(video: VideoInfo | None, settings: EncoderSettings) -> bool:
    """Whether the encode bakes a profile 7 FEL's enhancement layer into the picture (and carries its RPU)."""
    return keeps_dv(video, settings) and video is not None and video.hdr.dv_profile == 7 and video.hdr.dv_el == "FEL"


def _missing_tools(tools: Tools | None, names: tuple[str, ...]) -> list[str]:
    return [n for n in names if not locate(getattr(tools, n))] if tools is not None else []


def _flags(settings: EncoderSettings) -> set[str]:
    """The flag names the job's options and extra arguments set ("vbv-maxrate", ...)."""
    extra = (a.lstrip("-").split("=")[0] for a in settings.extra.split() if a.startswith("--"))
    return {n.lstrip("-") for n in settings.options} | set(extra)


def issues(
    video: VideoInfo | None,
    settings: EncoderSettings,
    tools: Tools | None = None,
    video_settings: VideoSettings | None = None,
) -> list[Issue]:
    """What stands in the way of carrying the source's HDR10+ and Dolby Vision (the Encoder tab's "HDR10+ /
    Dolby Vision from the source")."""
    if video is None:
        return []
    return _hdr10plus_issues(video, settings, tools) + _dv_issues(video, settings, tools, video_settings)


def _dv_issues(
    video: VideoInfo, settings: EncoderSettings, tools: Tools | None, video_settings: VideoSettings | None
) -> list[Issue]:
    dv = video.hdr
    if dv.dv_profile == 5 and not keeps_dv(video, settings):
        return [
            Issue(
                Severity.WARN,
                "hdr.dv_profile5",
                "Dolby Vision profile 5 has no HDR10 layer: without its RPU (not x265, or Dolby Vision from the source "
                "unticked) the encode's colours look wrong, unless the script maps them",
            )
        ]
    if dv.dv_profile not in (5, 7, 8) or not settings.dolby_vision:
        return []
    untick = "or untick Dolby Vision from the source on the Encoder tab"
    if settings.encoder is not Encoder.X265:
        return [
            Issue(
                Severity.WARN,
                "hdr.dv_x264",
                f"{settings.encoder.label} can't carry Dolby Vision: the encode keeps the HDR10 layer",
            )
        ]
    out = []

    def block(code: str, message: str) -> None:
        out.append(Issue(Severity.BLOCK, code, f"{message}, {untick}"))

    if dv.dv_compat == 4:
        block("hdr.dv_hlg", "Dolby Vision 8.4 (HLG) isn't carried yet: unticked, the encode keeps the HLG layer")
    if dv.dv_profile == 7 and dv.dv_el not in ("MEL", "FEL"):
        block(
            "hdr.dv_el",
            "The enhancement layer's kind (FEL or MEL) couldn't be read (is dovi_tool set?): unticked, the encode "
            "keeps the base layer",
        )
    tools_needed: tuple[str, ...] = ("ffmpeg", "dovi_tool")
    if dv.dv_profile == 7 and dv.dv_el == "FEL":
        tools_needed += ("mkvmerge",)
        if video_settings is not None and video_settings.source_filter is SourceFilter.BESTSOURCE:
            block(
                "hdr.dv_bake_bs",
                "Baking a FEL needs FFMS2 or L-SMASH as the source filter (BestSource counts this source's frames "
                "differently, so the enhancement layer and the RPU would be out of step)",
            )
    if settings.depth != 10:
        block("hdr.dv_depth", "Dolby Vision needs a 10-bit encode: set the bit depth")
    flags = _flags(settings)
    if level_vbv(settings) is None:
        block(
            "hdr.dv_vbv",
            "x265 needs --vbv-maxrate and --vbv-bufsize for Dolby Vision (HRD): set them in the options, or "
            "--level-idc to fill them with its max bitrate",
        )
    if (
        dv.dv_profile != 5
        and not (settings.source_color and video.color.master_display)
        and "master-display" not in flags
    ):
        block(
            "hdr.dv_master",
            "x265's Dolby Vision 8.1 needs a mastering display: the source has none, or the source's colour is off",
        )
    if video_settings is not None and video_settings.custom is not None:
        block(
            "hdr.dv_custom", "Dolby Vision follows the Video tab's crop and resize, and a custom script's aren't known"
        )
    if missing := _missing_tools(tools, tools_needed):
        block("tools.missing", f"Dolby Vision needs {' and '.join(missing)}: set it in Settings")
    return out


def _hdr10plus_issues(video: VideoInfo, settings: EncoderSettings, tools: Tools | None) -> list[Issue]:
    if not video.hdr.hdr10plus or not settings.hdr10plus:
        return []
    untick = "or untick HDR10+ from the source on the Encoder tab"
    if settings.encoder is not Encoder.X265:
        return [
            Issue(
                Severity.WARN,
                "hdr.hdr10plus_x264",
                f"{settings.encoder.label} can't carry HDR10+: the encode keeps HDR10 only",
            )
        ]
    out = []
    if settings.depth < 10:
        out.append(
            Issue(Severity.BLOCK, "hdr.hdr10plus_depth", f"HDR10+ needs a 10-bit encode: set the bit depth, {untick}")
        )
    if missing := _missing_tools(tools, ("ffmpeg", "hdr10plus_tool")):
        out.append(
            Issue(
                Severity.BLOCK, "tools.missing", f"HDR10+ needs {' and '.join(missing)}: set it in Settings, {untick}"
            )
        )
    return out


def hdr10plus_argvs(tools: Tools, source: Path, out: Path) -> tuple[tuple[str, ...], ...]:
    """The source's HDR10+ metadata into a JSON file: ffmpeg | hdr10plus_tool extract."""
    extract = (tools.hdr10plus_tool, "extract", "-o", str(out), "-")
    return (tuple(video_stream_argv(tools.ffmpeg, source)), extract)


def script_frames(vspipe: str, script: Path) -> int:
    """The frames a VapourSynth script gives (`vspipe --info`)."""
    lines: list[str] = []
    run([(vspipe, "--info", str(script), "-")], lines.append)
    m = _FRAMES.search("\n".join(lines))
    if m is None:
        raise ToolError(f"vspipe --info printed no frame count for {script.name}")
    return int(m.group(1))


def hdr10plus_frames(path: Path) -> int:
    """The frames an hdr10plus_tool JSON describes."""
    with path.open(encoding="utf-8") as f:
        return len(json.load(f).get("SceneInfo") or [])


def _same_frames(frames: int, meta: int, what: str, setting: str, log: LogFn) -> None:
    if frames != meta:
        raise ToolError(
            f"The script gives {frames} frames and the source's {what} has {meta}: they would be out of step "
            "(a trim or a frame-rate filter, or a source filter counting frames differently: try FFMS2). Untick "
            f"{setting} from the source on the Encoder tab to encode without it."
        )
    log(f"{what}: {meta} frames, as the script")


def check_frames(vspipe: str, script: Path, metadata: Path, log: LogFn) -> None:
    """Raise ToolError when the script's frame count isn't the HDR10+ metadata's."""
    _same_frames(script_frames(vspipe, script), hdr10plus_frames(metadata), "HDR10+ metadata", "HDR10+", log)


def rpu_argvs(tools: Tools, source: Path, out: Path) -> tuple[tuple[str, ...], ...]:
    """The source's Dolby Vision RPU into a file: ffmpeg | dovi_tool extract-rpu (as it is: mode 0)."""
    extract = (tools.dovi_tool, "-m", "0", "extract-rpu", "-", "-o", str(out))
    return (tuple(video_stream_argv(tools.ffmpeg, source)), extract)


def rpu_frames(dovi_tool: str, rpu: Path) -> int:
    """The frames an RPU file describes (`dovi_tool info -s`)."""
    lines: list[str] = []
    run([(dovi_tool, "info", "-s", "-i", str(rpu))], lines.append)
    m = _FRAMES.search("\n".join(lines))
    if m is None:
        raise ToolError(f"dovi_tool info printed no frame count for {rpu.name}")
    return int(m.group(1))


def check_rpu_frames(vspipe: str, dovi_tool: str, script: Path, rpu: Path, log: LogFn) -> None:
    """Raise ToolError when the script's frame count isn't the RPU's."""
    _same_frames(script_frames(vspipe, script), rpu_frames(dovi_tool, rpu), "Dolby Vision RPU", "Dolby Vision", log)


def el_argvs(tools: Tools, source: Path, out: Path) -> tuple[tuple[str, ...], ...]:
    """A profile 7 source's enhancement layer into a raw HEVC file: ffmpeg | dovi_tool demux --el-only."""
    demux = (tools.dovi_tool, "demux", "--el-only", "-", "-e", str(out))
    return (tuple(video_stream_argv(tools.ffmpeg, source)), demux)


def el_mkv_argv(mkvmerge: str, hevc: Path, out: Path, default_duration_ns: int) -> tuple[str, ...]:
    """The raw enhancement layer into an MKV with the source's frame duration (raw HEVC has no timestamps, and
    the source filters seek by them)."""
    return (mkvmerge, "-o", str(out), "--default-duration", f"0:{default_duration_ns}ns", str(hevc))


def rpu_summary(dovi_tool: str, rpu: Path) -> str:
    """`dovi_tool info -s` of an RPU file. Cached per file, size and mtime (the encode's command reads it)."""
    st = rpu.stat()
    return _summary(dovi_tool, str(rpu), st.st_size, st.st_mtime_ns)


@functools.lru_cache(maxsize=16)
def _summary(dovi_tool: str, rpu: str, _size: int, _mtime: int) -> str:
    lines: list[str] = []
    run([(dovi_tool, "info", "-s", "-i", rpu)], lines.append)
    return "\n".join(lines)


def fel_color(color: VideoColor, summary: str) -> VideoColor:
    """A baked FEL's HDR10 values from its RPU's summary (rpu_summary), as Parse-Fel-Master-Data and DoVi_Scripts
    take them: the mastering display's primaries from the source (MediaInfo) and its luminance from "RPU
    mastering display"; MaxCLL / MaxFALL from L1 (the whole RPU's), else L6, else the source's."""
    out = replace(color)
    if (m := _RPU_DISPLAY.search(summary)) and color.master_display:
        lo, hi = float(m.group(1)), float(m.group(2))
        primaries = color.master_display.split("L(")[0]
        out.master_display = f"{primaries}L({math.floor(hi * 10000)},{math.floor(lo * 10000)})"
    for pattern in (_RPU_L1, _RPU_L6):
        if (m := pattern.search(summary)) and int(float(m.group(1))) > 0:
            out.max_cll, out.max_fall = int(float(m.group(1))), int(float(m.group(2)))
            break
    return out


def l5_offsets(offsets: dict[str, Any], video_settings: VideoSettings, width: int, height: int) -> dict[str, int]:
    """An L5 active area (the letterbox bars, in pixels of the width x height source) on the encode's picture:
    each side less the crop (at least 0: cropped past the bar), then scaled by the resize, in the chain's order."""
    out = {k: int(offsets.get(k) or 0) for k in _L5}
    for s in video_settings.filters:
        if s.category is FilterCategory.CROP:
            c = video_settings.crop
            out = {k: max(0, v - getattr(c, k)) for k, v in out.items()}
            width, height = width - c.left - c.right, height - c.top - c.bottom
        elif s.category is FilterCategory.RESIZE and (r := video_settings.resize) is not None and width and height:
            scale = {"left": Fraction(r.width, width), "top": Fraction(r.height, height)}
            scale |= {"right": scale["left"], "bottom": scale["top"]}
            out = {k: math.floor(v * scale[k] + Fraction(1, 2)) for k, v in out.items()}
            width, height = r.width, r.height
    return out


def rpu_edit(
    level5: dict[str, Any], video_settings: VideoSettings, width: int, height: int, profile: str = "8.1"
) -> dict[str, Any]:
    """dovi_tool editor's config for the encode's RPU, from `dovi_tool export --data level5=`: the written profile
    (8.1: mode 2; 5: mode 0, as it is) and each L5 preset on the encode's picture."""
    area = level5.get("active_area") or level5  # dovi_tool < 2.3.3 exports the bare active area (DoviCrop)
    presets = area.get("presets") or []
    config: dict[str, Any] = {"mode": _DV_MODES[profile]}
    if presets:
        config["active_area"] = {
            "crop": True,
            "presets": [{**p, **l5_offsets(p, video_settings, width, height)} for p in presets],
            "edits": area.get("edits") or {"all": presets[0].get("id", 0)},
        }
    return config


def edit_rpu(
    dovi_tool: str,
    rpu: Path,
    out: Path,
    video_settings: VideoSettings,
    width: int,
    height: int,
    log: LogFn,
    profile: str = "8.1",
) -> None:
    """The source's RPU (rpu) as the encode's (out): its L5 offsets following the crop and resize, as the profile
    it's written as (dv_profile). The L5 export and the editor's config are left next to out."""
    level5, config = out.with_name(out.stem + "_l5.json"), out.with_name(out.stem + "_edit.json")
    run([(dovi_tool, "export", "--data", f"level5={level5}", "-i", str(rpu))], log)
    with level5.open(encoding="utf-8") as f:
        edit = rpu_edit(json.load(f), video_settings, width, height, profile)
    config.write_text(json.dumps(edit, indent=2), encoding="utf-8")
    run([(dovi_tool, "editor", "-i", str(rpu), "-j", str(config), "-o", str(out))], log)
    presets = edit.get("active_area", {}).get("presets", [])
    areas = "; ".join(" ".join(f"{k}={p[k]}" for k in _L5) for p in presets) or "none"
    log(f"Dolby Vision RPU: profile {profile}, L5 offsets {areas}")


def output_issues(video: VideoInfo | None, settings: EncoderSettings, output: SourceInfo) -> list[Issue]:
    """A BLOCK when the output was meant to carry HDR10+ or Dolby Vision and MediaInfo finds none in it."""
    found = output.video.hdr if output.video is not None else None
    if found is None:
        return []
    out = []
    if keeps_hdr10plus(video, settings) and not found.hdr10plus:
        out.append(Issue(Severity.BLOCK, "hdr.hdr10plus_missing", "The output has no HDR10+ metadata"))
    want = dv_profile(video)
    if keeps_dv(video, settings) and (found.dv_profile, found.dv_compat) != _DV_FOUND[want]:
        what = f"Dolby Vision {found.dv_name}" if found.dv_profile else "no Dolby Vision"
        out.append(Issue(Severity.BLOCK, "hdr.dv_missing", f"The output has {what}, not {want}"))
    return out
