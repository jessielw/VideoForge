"""What the job's script gives: its frame count and frame rate (`vspipe --info`, written to the work folder).

The encode is timed by the script, not the source: an IVTC (29.97 -> 23.976 fps) or a double-rate deinterlace
changes the rate, so the mux (a raw stream's frame duration) and AutoQPF (chapter frames) read it from here, as
StaxRip does (p.Script.GetCachedFrameRate). A script whose length isn't the source's (a trim, a filter that
changes the speed) puts the copied audio, subtitles and chapters out of step: length_warning says so. A VFR
source's encode is timed by its timestamps (vfr.py) while the script keeps every frame; one that doesn't is muxed
at the script's constant rate, which length_warning says too.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
import re

from videoforge.core.models import Issue, Severity, VideoInfo

SCRIPT_INFO = "video.info.txt"  # in the work folder
_FRAMES = re.compile(r"^Frames:\s*(\d+)", re.MULTILINE)
_FPS = re.compile(r"^FPS:\s*(\d+)/(\d+)", re.MULTILINE)  # "FPS: 24000/1001 (23.976 fps)"; "FPS: Variable"
_SLACK_FRAMES = 3  # an IVTC's decimation can end a frame or two off the source's length


@dataclass(frozen=True, slots=True)
class ScriptInfo:
    frames: int
    fps: Fraction | None  # None: a variable frame rate

    @property
    def seconds(self) -> float | None:
        return float(self.frames / self.fps) if self.fps else None


def info_argv(vspipe: str, script: Path, out: Path) -> tuple[str, ...]:
    """vspipe writes the clip's info to out."""
    return (vspipe, "--info", str(script), str(out))


def parse(text: str) -> ScriptInfo | None:
    """vspipe --info's text; None without a frame count."""
    frames = _FRAMES.search(text)
    if frames is None:
        return None
    fps = _FPS.search(text)
    rate = Fraction(int(fps.group(1)), int(fps.group(2))) if fps and int(fps.group(2)) else None
    return ScriptInfo(int(frames.group(1)), rate or None)


def read(path: Path) -> ScriptInfo | None:
    """The info a job's info step wrote; None when it isn't there (yet) or can't be read."""
    try:
        return parse(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None


def _out_of_step(script: float, source: float) -> str:
    return (
        f"The script's video is {script:.3f} s long and the source's {source:.3f} s ({script - source:+.3f} s): "
        "the source's audio, subtitles and chapters would be out of step with it (a trim, or a filter that "
        "changes the speed)"
    )


def _vfr_warning(video: VideoInfo, frames: int, fps: Fraction | None) -> str:
    """A VFR source: its timestamps time a script that keeps every frame; one that doesn't is muxed at its own
    constant rate, so its length is checked against the source's (MediaInfo's duration)."""
    if not video.frames or frames == video.frames:
        return ""
    rate = f"a constant {float(fps):.3f} fps" if fps else "the source's first frame duration (the script has no rate)"
    dropped = (
        f"The script has {frames} frames and the source {video.frames}: the source's variable frame rate "
        f"timestamps don't fit it, so it's muxed at {rate}"
    )
    if not fps or not video.duration_ms:
        return dropped
    script, source = float(frames / fps), video.duration_ms / 1000
    if abs(script - source) <= _SLACK_FRAMES / fps:
        return dropped
    return f"{dropped}. {_out_of_step(script, source)}"


def length_warning(video: VideoInfo | None, frames: int, fps: Fraction | None) -> str:
    """Why a script of frames at fps would be out of step with the source's audio, subtitles and chapters:
    its length isn't the source's (beyond a few frames), or (a VFR source) it doesn't keep the source's frames.
    "" when it does, or when either length isn't known."""
    if video is not None and video.vfr:
        return _vfr_warning(video, frames, fps)
    if video is None or not video.frames or not video.default_duration_ns or not fps:
        return ""
    source = video.frames * video.default_duration_ns / 1e9
    script = float(frames / fps)
    if abs(script - source) <= _SLACK_FRAMES * video.default_duration_ns / 1e9:
        return ""
    return _out_of_step(script, source)


def length_issues(video: VideoInfo | None, info: ScriptInfo | None) -> list[Issue]:
    """length_warning as an issue on the finished job."""
    message = length_warning(video, info.frames, info.fps) if info else ""
    return [Issue(Severity.WARN, "video.length", message)] if message else []
