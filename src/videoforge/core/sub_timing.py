"""Does a text subtitle fit its source's length? A coarse check for the wrong episode or cut, not sync drift.

The last cue's end (SRT, ASS/SSA; image subtitles aren't read) is set against the source's length:
"late" when it ends more than LATE_MS after the source does, "early" when it ends more than
max(EARLY_MIN_MS, EARLY_SHARE of the source) before (room for credits). A forced subtitle has a few cues
anywhere, so only "late" counts for one.
"""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import re
import subprocess

LATE_MS = 60_000
EARLY_MIN_MS = 5 * 60_000
EARLY_SHARE = 0.15
TEXT_FORMATS = (".srt", ".ass", ".ssa")

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
# SRT "00:01:02,345 --> 00:01:04,000" (a "." also seen); ASS "Dialogue: 0,0:01:02.34,0:01:04.00,..."
_SRT_END = re.compile(r"-->\s*(\d+):(\d{1,2}):(\d{1,2})[,.](\d{1,3})")
_ASS_END = re.compile(r"(?m)^\s*Dialogue:\s*[^,]*,\s*[^,]*,\s*(\d+):(\d{1,2}):(\d{1,2})\.(\d{1,3})")


def _text(path: Path) -> str:
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", errors="replace")
    return raw.decode("utf-8-sig", errors="replace")


def _ms(h: str, m: str, s: str, frac: str) -> int:
    return ((int(h) * 60 + int(m)) * 60 + int(s)) * 1000 + int(frac.ljust(3, "0"))


def last_cue_ms(path: Path) -> int | None:
    """When the subtitle's last cue ends, or None for an image subtitle, an unreadable file or one with no cues."""
    pattern = {".srt": _SRT_END, ".ass": _ASS_END, ".ssa": _ASS_END}.get(path.suffix.lower())
    if pattern is None:
        return None
    try:
        text = _text(path)
    except OSError:
        return None
    ends = [_ms(*m.groups()) for m in pattern.finditer(text)]
    return max(ends) if ends else None


def verdict(last_ms: int, source_ms: int, *, forced: bool = False) -> str | None:
    """The gap that matters, "late" or "early", or None when the subtitle fits."""
    if last_ms > source_ms + LATE_MS:
        return "late"
    if not forced and last_ms < source_ms - max(EARLY_MIN_MS, EARLY_SHARE * source_ms):
        return "early"
    return None


def source_length_ms(path: Path, mkvmerge: str) -> int | None:
    """The source's length: mkvmerge -J's (an MKV's header: quick), else MediaInfo's. Cached while unchanged."""
    try:
        stat = path.stat()
    except OSError:
        return None
    return _length(str(path), stat.st_size, stat.st_mtime_ns, mkvmerge)


@lru_cache(maxsize=512)
def _length(path: str, _size: int, _mtime_ns: int, mkvmerge: str) -> int | None:
    try:
        result = subprocess.run(
            [mkvmerge, "-J", path],
            capture_output=True,
            check=False,
            encoding="utf-8",
            errors="replace",
            creationflags=_NO_WINDOW,
            timeout=120,
        )
        ns = json.loads(result.stdout).get("container", {}).get("properties", {}).get("duration")
        if isinstance(ns, int) and ns > 0:
            return ns // 1_000_000
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, AttributeError):
        pass
    try:
        from pymediainfo import MediaInfo

        general = next((t for t in MediaInfo.parse(path).tracks if t.track_type == "General"), None)
        duration = getattr(general, "duration", None)
        return int(float(duration)) if duration else None
    except Exception:  # no length: the subtitle just isn't checked
        return None
