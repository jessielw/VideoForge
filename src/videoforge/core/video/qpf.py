"""Chapters and the encoder's qpfile from the source, through the user's AutoQPF library.

AutoQPF reads the source's chapters (or generates them every N% of the runtime
when there are none) into an OGM chapter file, then writes the qpfile: one
"<frame> K" line per chapter start, so the encoder puts a keyframe there and the
chapters land on clean cuts. A TS's program shows in MediaInfo as a menu with no
chapters in it, which AutoQPF can't read: the chapters are generated here instead,
and AutoQPF makes the qpfile from that chapter file.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path


@dataclass(frozen=True, slots=True)
class QpfFiles:
    qpfile: Path
    chapters: Path  # OGM text, muxed as the release's chapters


def qpf_paths(work_dir: Path) -> QpfFiles:
    # AutoQPF names the chapter file after the qpfile: <stem>_chapters.txt
    return QpfFiles(work_dir / "chapters.qpf", work_dir / "chapters_chapters.txt")


def make_qpf(source: Path, work_dir: Path, fps: Fraction, chunk_percent: float = 5.0) -> QpfFiles | None:
    """Write the qpfile and chapter file; None when the source has no usable chapters."""
    from auto_qpf.qpf import QpfGenerator
    from auto_qpf.qpf_exceptions import ChapterIndexError, ImproperChapterError, NoChapterDataError

    files = qpf_paths(work_dir)
    try:
        try:
            QpfGenerator().generate_qpf(
                file_input=source,
                file_output=files.qpfile,
                fps=float(fps),
                auto_detect_fps=False,  # the clip's exact rate, not MediaInfo's rounded one
                generate_chapters=True,
                generated_chapter_chunks=chunk_percent,
            )
        except ValueError:  # a menu without chapters (a TS's program)
            if not _generate_chapters(source, files.chapters, chunk_percent):
                return None
            QpfGenerator().generate_qpf(
                file_input=files.chapters, file_output=files.qpfile, fps=float(fps), auto_detect_fps=False
            )
    except (NoChapterDataError, ImproperChapterError, ChapterIndexError):
        return None
    return files if files.qpfile.is_file() and files.chapters.is_file() else None


def _generate_chapters(source: Path, out: Path, chunk_percent: float) -> bool:
    """Numbered chapters every chunk_percent of the source's runtime (MediaInfo's), from the start, as OGM text."""
    from pymediainfo import MediaInfo

    from videoforge.core.execute.chapters import ogm_text

    general = MediaInfo.parse(str(source)).general_tracks
    duration_ms = float(general[0].duration or 0) if general else 0
    if duration_ms <= 0:
        return False
    count = max(1, int(100 / chunk_percent))
    out.write_text(ogm_text([(round(duration_ms * n / count), "") for n in range(count)]), encoding="utf-8")
    return True
