"""A source's dynamic HDR metadata: Dolby Vision and HDR10+ (MediaInfo), and a profile 7 enhancement layer's
kind (FEL or MEL, which MediaInfo can't tell) from a second of its RPU.

The FEL / MEL read is the user's dv_check way (StaxRip's "dv_check" folder): a second of the video stream from
10 s in, through dovi_tool extract-rpu, then `dovi_tool info -f 0` on its first frame for `el_type`.
"""

from __future__ import annotations

import functools
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any

from videoforge.core.config import Tools
from videoforge.core.execute.process import ToolError, run
from videoforge.core.models import VideoHdr

logger = logging.getLogger(__name__)

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_PROFILE = re.compile(r"Profile (\d+)(?:\.(\d+))?")
_DVHE = re.compile(r"\b(?:dvhe|dvh1|dvav|dva1|dav1)\.(\d+)", re.IGNORECASE)


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
