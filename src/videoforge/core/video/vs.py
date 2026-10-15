"""In-process VapourSynth for the preview: load a script's clip, read its info, render frames.

The plugin folder must be known before the VapourSynth core starts, so call
configure() first (the preview worker does at startup). Clips are cached per slot (a job's
stage): the preview asks for many frames of the same script.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import threading
from collections import OrderedDict
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    import numpy as np
    import vapoursynth as vs

PLUGIN_ENV = "VAPOURSYNTH_EXTRA_PLUGIN_PATH"
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


SCRIPT_NAME = "<script>"  # the file name scripts are compiled under; their traceback frames carry it


class ScriptError(RuntimeError):
    """A script that fails to run. line is the script's 1-based line that failed, when known."""

    def __init__(self, message: str, line: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.line = line

    def __str__(self) -> str:
        return f"Line {self.line}: {self.message}" if self.line else self.message


def error_line(e: BaseException) -> int | None:
    """The script line an exception came from: a syntax error's line, else the innermost script frame."""
    if isinstance(e, SyntaxError) and e.filename == SCRIPT_NAME:
        return e.lineno
    line = None
    tb = e.__traceback__
    while tb is not None:
        if tb.tb_frame.f_code.co_filename == SCRIPT_NAME:
            line = tb.tb_lineno
        tb = tb.tb_next
    return line


def configure(plugin_dir: str | Path | None) -> None:
    """Point VapourSynth at the plugin folder: this process's (before the first clip loads)
    and every vspipe it starts, which inherit the environment."""
    if plugin_dir:
        os.environ[PLUGIN_ENV] = str(plugin_dir)


def ensure_vspipe(vspipe: str) -> None:
    """pip's vapoursynth needs `vapoursynth config` once before vspipe can start its Python."""
    ok = subprocess.run([vspipe, "--version"], capture_output=True, creationflags=_NO_WINDOW, check=False)
    if ok.returncode != 0:
        subprocess.run([sys.executable, "-m", "vapoursynth", "config"], capture_output=True,
                       creationflags=_NO_WINDOW, check=True)


def load_clip(script: str) -> vs.VideoNode:
    """Run a script (from script.build_script) and return its `clip`."""
    import vapoursynth as vs

    namespace: dict[str, object] = {"__name__": "__vapoursynth__"}
    try:
        exec(compile(script, SCRIPT_NAME, "exec"), namespace)  # noqa: S102 - running the user's script is the point
    except Exception as e:
        msg = e.msg if isinstance(e, SyntaxError) else str(e)
        raise ScriptError(f"{type(e).__name__}: {msg}", error_line(e)) from e
    clip = namespace.get("clip")
    if not isinstance(clip, vs.VideoNode):
        raise ScriptError("The script must leave a video clip in `clip`")
    return clip


@dataclass(frozen=True, slots=True)
class ClipInfo:
    frames: int
    width: int
    height: int
    fps_num: int
    fps_den: int
    format: str  # e.g. "YUV420P8"
    bits: int

    @property
    def fps(self) -> float:
        return self.fps_num / self.fps_den if self.fps_den else 0.0

    @property
    def frame_duration_ns(self) -> int:
        return round(1e9 * self.fps_den / self.fps_num) if self.fps_num else 0


def clip_info(clip: vs.VideoNode) -> ClipInfo:
    fps = Fraction(clip.fps.numerator, clip.fps.denominator) if clip.fps.denominator else Fraction(0)
    fmt = clip.format
    return ClipInfo(clip.num_frames, clip.width, clip.height, fps.numerator, fps.denominator or 1,
                    fmt.name if fmt else "variable", fmt.bits_per_sample if fmt else 0)


def matrix(frame_props, height: int) -> int:
    """The frame's YUV matrix (_Matrix), or the usual one for its size when unspecified."""
    m = frame_props.get("_Matrix")
    if isinstance(m, int) and m not in (2, 3):  # 2 = unspecified, 3 = reserved
        return m
    return 1 if height > 576 else 6  # BT.709 for HD, BT.601 (170M) for SD


def frame_rgb(clip: vs.VideoNode, n: int) -> np.ndarray:
    """Frame n as an (H, W, 3) uint8 RGB array."""
    import numpy as np  # here, not at the top: numpy's import alone commits ~30 MB per CPU thread
    import vapoursynth as vs

    n = max(0, min(n, clip.num_frames - 1))
    if clip.format.color_family is not vs.RGB:
        props = clip.get_frame(n).props
        clip = clip.resize.Bicubic(format=vs.RGB24, matrix_in=matrix(props, clip.height))
    elif clip.format.id != vs.RGB24:
        clip = clip.resize.Bicubic(format=vs.RGB24)
    f = clip.get_frame(n)
    return np.stack([np.asarray(f[i]) for i in range(3)], axis=-1)


def frame_image(clip: vs.VideoNode, n: int, fmt: Literal["jpeg", "png"] = "jpeg", quality: int = 90) -> bytes:
    from PIL import Image

    img = Image.fromarray(frame_rgb(clip, n), "RGB")
    buf = io.BytesIO()
    if fmt == "png":
        img.save(buf, format="PNG", compress_level=1)
    else:
        img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def frame_props(clip: vs.VideoNode, n: int) -> dict[str, object]:
    """Readable frame properties (picture type, matrix, ...)."""
    n = max(0, min(n, clip.num_frames - 1))
    out: dict[str, object] = {}
    for k, v in clip.get_frame(n).props.items():
        if isinstance(v, bytes):
            v = v.decode("utf-8", "replace")
        if isinstance(v, (int, float, str)):
            out[k] = v
    return out


class ClipCache:
    """The last few clips, so seeking through a preview doesn't reload the source. One clip per slot
    (a job's stage): a new script for a slot (a crop edit) drops the slot's old clip first, since
    each clip has its own source filter and its caches (hundreds of MB at 1080p)."""

    def __init__(self, size: int = 6) -> None:
        self.size = size
        self._clips: OrderedDict[str, tuple[str, vs.VideoNode]] = OrderedDict()  # slot -> (script, clip)
        self._lock = threading.Lock()

    def get(self, script: str, slot: str | None = None) -> vs.VideoNode:
        key = slot or script
        with self._lock:
            held = self._clips.get(key)
            if held is not None and held[0] == script:
                self._clips.move_to_end(key)
                return held[1]
            if held is not None:  # free the old clip (this reference too) before the new one loads
                del self._clips[key]
                held = None
        clip = load_clip(script)  # outside the lock: indexing a source can take minutes
        with self._lock:
            self._clips[key] = (script, clip)
            self._clips.move_to_end(key)
            while len(self._clips) > self.size:
                self._clips.popitem(last=False)
        return clip

    def clear(self) -> None:
        with self._lock:
            self._clips.clear()
