"""Chapters as OGM text (CHAPTER01=00:00:00.000 / CHAPTER01NAME=...), the form MP4Box takes.

From a Matroska chapter XML file, or from a source's own chapters (MediaInfo's menu track).
"""

from __future__ import annotations

from pathlib import Path
import re
import xml.etree.ElementTree as ET

from pymediainfo import MediaInfo

Chapter = tuple[int, str]  # start in ms, name

_MENU_KEY = re.compile(r"^_?(\d{2})_(\d{2})_(\d{2})_?(\d{3})$")


def _ms(timestamp: str) -> int:
    """HH:MM:SS(.fraction) -> ms."""
    h, m, s = timestamp.strip().split(":")
    return round((int(h) * 3600 + int(m) * 60 + float(s)) * 1000)


def from_xml(path: Path) -> list[Chapter]:
    """The first edition's chapter atoms (hidden ones skipped)."""
    root = ET.parse(path).getroot()
    edition = root.find("EditionEntry")
    out: list[Chapter] = []
    for atom in edition.findall("ChapterAtom") if edition is not None else []:
        if (atom.findtext("ChapterFlagHidden") or "0").strip() == "1":
            continue
        start = atom.findtext("ChapterTimeStart")
        if start:
            out.append((_ms(start), (atom.findtext("ChapterDisplay/ChapterString") or "").strip()))
    return out


def from_source(path: Path) -> list[Chapter]:
    """A media file's chapters, as MediaInfo lists them in its menu track ("00:05:12.345": "en:Name")."""
    out: list[Chapter] = []
    for track in MediaInfo.parse(str(path)).tracks:
        if track.track_type != "Menu":
            continue
        for key, value in track.to_data().items():
            m = _MENU_KEY.match(key)
            if m:
                h, mi, s, ms = map(int, m.groups())
                name = re.sub(r"^[a-z]{2,3}(-[A-Za-z]+)?:", "", str(value)).strip()
                out.append((((h * 60 + mi) * 60 + s) * 1000 + ms, name))
    return sorted(out)


def ogm_text(chapters: list[Chapter]) -> str:
    lines = []
    for n, (ms, name) in enumerate(chapters, 1):
        h, rest = divmod(ms, 3_600_000)
        m, rest = divmod(rest, 60_000)
        s, ms_ = divmod(rest, 1000)
        lines += [
            f"CHAPTER{n:02d}={h:02d}:{m:02d}:{s:02d}.{ms_:03d}",
            f"CHAPTER{n:02d}NAME={name or f'Chapter {n:02d}'}",
        ]
    return "\n".join(lines) + "\n"
