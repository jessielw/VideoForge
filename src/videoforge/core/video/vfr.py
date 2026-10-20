"""A variable frame rate source's timestamps, carried onto the encode (as StaxRip does: Demux.vb, Muxer.vb).

MediaInfo says an MKV's video is VFR (FrameRate_Mode); mkvextract writes its timestamps (v2: one per frame, in
ms) to the work folder, and mkvmerge times the encode by them instead of a fixed frame duration. They only fit a
script that keeps every frame: one that drops or adds some (an IVTC, a trim, a double-rate deinterlace) is muxed
at the script's constant rate instead, and info.length_warning says so. MP4Box takes no timestamps file: an MP4
is muxed at a constant rate (a WARN, mux.Mp4Box.issues).
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from videoforge.core.models import VideoInfo

TIMESTAMPS = "timestamps.txt"  # in the work folder
SOURCE_TIMESTAMPS = "timestamps.source.txt"


def normalize(source: Path, output: Path) -> None:
    """Put the first video frame at zero without changing any interval, including the final end time."""
    values = [
        Decimal(line.strip())
        for line in source.read_text(encoding="utf-8-sig").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not values or any(not value.is_finite() for value in values):
        raise ValueError("No valid video timestamps")
    output.write_text(
        "# timestamp format v2\n" + "".join(f"{value - values[0]:f}\n" for value in values), encoding="utf-8"
    )


def extract_argv(mkvextract: str, source: Path, track: int, out: Path) -> tuple[str, ...]:
    """mkvextract writes the source video's timestamps (v2) to out."""
    return (mkvextract, "--ui-language", "en", "timestamps_v2", str(source), f"{track}:{out}")


def count(path: Path) -> int | None:
    """How many frames a v2 timestamps file times (its lines that aren't comments); None when it can't be read."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    return sum(1 for line in lines if line.strip() and not line.lstrip().startswith("#"))


def fits(path: Path, frames: int) -> bool:
    """Whether the timestamps time a script of this many frames: one timestamp each, and mkvextract's last one
    (the last frame's end)."""
    return count(path) in (frames, frames + 1)


def carries(video: VideoInfo | None, container: str) -> bool:
    """Whether a job's mux takes the source's timestamps: a VFR source, into an MKV."""
    return video is not None and video.vfr and container == "mkv"
