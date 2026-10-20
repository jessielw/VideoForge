"""A subtitle track burned into the video (StaxRip's hardcoded subtitle: Project.AddHardcodedSubtitleFilter).

The track editor marks one subtitle track to burn in (TrackOverride.burn; a template's subtitle rule can too): the
plan leaves it out of the mux (plan.burn) and the script draws it with the bundled SubText plugin, text formats
(SRT, ASS) with sub.TextFile, image ones (PGS, VobSub) with sub.ImageFile. A source track is extracted to the work
folder first (mkvextract, with the index); an added file is read where it is.

StaxRip puts the filter right after the crop. Text is drawn there (libass lays it out on the cropped picture, so
it can't land in black bars the crop removes). An image subtitle is a picture of the source's whole frame, which
SubText stretches onto a clip of another size: it's drawn before the crop, on the frame it was made for.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from videoforge.core.models import Issue, Overrides, Severity, SubFormat, SubTrack, VideoInfo, track_key

# What SubText reads, and the extension mkvextract's file takes (VobSub: it writes the .idx and its .sub).
EXTENSIONS = {SubFormat.SRT: ".srt", SubFormat.ASS: ".ass", SubFormat.PGS: ".sup", SubFormat.VOBSUB: ".idx"}
IMAGE = frozenset({SubFormat.PGS, SubFormat.VOBSUB})


def picked(tracks: Iterable[SubTrack], overrides: Overrides) -> list[SubTrack]:
    """The tracks marked to burn in, in the order given (the first one is burned)."""
    out = []
    for t in tracks:
        ov = overrides.tracks.get(track_key(t))
        if ov is not None and ov.burn:
            out.append(t)
    return out


def issues(marked: list[SubTrack]) -> list[Issue]:
    """A format SubText can't draw blocks; more than one marked warns (only the first is burned)."""
    found = []
    if marked and marked[0].format not in EXTENSIONS:
        found.append(
            Issue(Severity.BLOCK, "subs.burn_format", f"{label(marked[0])}: {marked[0].format} can't be burned in")
        )
    if len(marked) > 1:
        rest = ", ".join(label(t) for t in marked[1:])
        found.append(
            Issue(Severity.WARN, "subs.burn_many", f"Only one subtitle is burned in ({label(marked[0])}): not {rest}")
        )
    return found


def label(track: SubTrack) -> str:
    return track.external_path.name if track.external_path is not None else f"Subtitle #{track.id}"


def is_image(track: SubTrack) -> bool:
    return track.format in IMAGE


def file(track: SubTrack, work: Path) -> Path:
    """The file the script reads: an added one where it is (a VobSub by its .idx), a source track's extract."""
    if track.external_path is not None and track.extracted_from is None:
        path = track.external_path
        return path.with_suffix(".idx") if track.format is SubFormat.VOBSUB else path
    return work / f"burn.{track.id}{EXTENSIONS.get(track.format, '.sub')}"


def shift_ms(track: SubTrack, source: Path, video: VideoInfo | None) -> int:
    """Shift a source subtitle to the decoded video's origin; MP4 remux starts its selected track at zero."""
    if track.external_path is not None:
        return -(video.start_ms if video else 0) if track.extracted_from is not None else 0
    if source.suffix.lower() == ".mp4":
        return track.delay_ms
    return -(video.start_ms if video else 0)


def extract_argv(mkvextract: str, source: Path, track: SubTrack, out: Path) -> tuple[str, ...]:
    """mkvextract writes the source's subtitle track to out."""
    return (mkvextract, "--ui-language", "en", "tracks", str(source), f"{track.id}:{out}")


def files(path: Path, image_pair: bool = False) -> tuple[Path, ...]:
    """A VobSub's index and bitmap payload are one input/output."""
    return (path.with_suffix(".idx"), path.with_suffix(".sub")) if image_pair else (path,)


def dependencies(track: SubTrack, work: Path) -> tuple[Path, ...]:
    return files(file(track, work), track.format is SubFormat.VOBSUB)


def external_stamp(track: SubTrack) -> str:
    """A script/cache key for added subtitles, including an extract's original files."""
    if track.external_path is None:
        return ""
    stamps = []
    for path in files(track.external_path, track.format is SubFormat.VOBSUB):
        try:
            st = path.stat()
            stamps.append((str(path), st.st_size, st.st_mtime_ns))
        except OSError:
            stamps.append((str(path), None, None))
    return f"# Subtitle inputs: {stamps!r}"


def present(track: SubTrack | None, work: Path) -> bool:
    """Whether the file to burn is there (a source track's once the index steps extracted it)."""
    return track is None or all(p.is_file() for p in dependencies(track, work))


def lines(track: SubTrack, work: Path) -> list[str]:
    plugin = "ImageFile" if is_image(track) else "TextFile"
    return [f"clip = core.sub.{plugin}(clip, file={str(file(track, work))!r})"]
