"""One track of an MP4 or a TS source into an MKV in the work folder, for mkvextract (it reads Matroska only).

The burn-in subtitle's extract (burn.py) and a VFR source's timestamps (vfr.py) read the source with mkvextract;
from another container, mkvmerge copies the track into an MKV first and mkvextract reads that (its track 0).
mkvmerge times the copy as it times the mux: a TS keeps its offset to the earliest stream, the tracks left out too.
"""

from __future__ import annotations

from pathlib import Path

MATROSKA = (".mkv", ".mka", ".mks", ".webm")


def needed(source: Path) -> bool:
    """Whether mkvextract can't read the source as it is."""
    return source.suffix.lower() not in MATROSKA


def argv(mkvmerge: str, source: Path, kind: str, track: int, out: Path, shift_ms: int = 0) -> tuple[str, ...]:
    """mkvmerge copying the source's track (kind: "video" or "subtitles", by mkvmerge id) alone into out."""
    pick = {
        "video": ("--video-tracks", str(track), "--no-subtitles"),
        "subtitles": ("--no-video", "--subtitle-tracks", str(track)),
    }[kind]
    rest = ("--no-audio", "--no-chapters", "--no-attachments", "--no-global-tags", "--no-track-tags")
    sync = ("--sync", f"{track}:{shift_ms}") if shift_ms else ()
    return (mkvmerge, "--ui-language", "en", "--output", str(out), *pick, *rest, *sync, str(source))
