"""What the job's script gives: its frame count and frame rate (`vspipe --info`, written to the work folder).

The encode is timed by the script, not the source: an IVTC (29.97 -> 23.976 fps) or a double-rate deinterlace
changes the rate, so the mux (a raw stream's frame duration) and AutoQPF (chapter frames) read it from here, as
StaxRip does (p.Script.GetCachedFrameRate). A script whose length isn't the source's (a trim, a filter that
changes the speed) puts the copied audio, subtitles and chapters out of step: length_warning says so.
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


def length_warning(video: VideoInfo | None, frames: int, fps: Fraction | None) -> str:
    """Why a script of frames at fps would be out of step with the source's audio, subtitles and chapters:
    its length isn't the source's (beyond a few frames). "" when it is, or when either length isn't known."""
    if video is None or not video.frames or not video.default_duration_ns or not fps:
        return ""
    source = video.frames * video.default_duration_ns / 1e9
    script = float(frames / fps)
    if abs(script - source) <= _SLACK_FRAMES * video.default_duration_ns / 1e9:
        return ""
    return (
        f"The script's video is {script:.3f} s long and the source's {source:.3f} s ({script - source:+.3f} s): "
        "the source's audio, subtitles and chapters would be out of step with it (a trim, or a filter that "
        "changes the speed)"
    )


def length_issues(video: VideoInfo | None, info: ScriptInfo | None) -> list[Issue]:
    """length_warning as an issue on the finished job."""
    message = length_warning(video, info.frames, info.fps) if info else ""
    return [Issue(Severity.WARN, "video.length", message)] if message else []
