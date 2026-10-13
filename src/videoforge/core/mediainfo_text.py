"""Parse MediaInfo's text report (as posted with a release) into a SourceInfo."""

from __future__ import annotations

import re
from pathlib import PureWindowsPath

from videoforge.core import lang
from videoforge.core.classify import (
    parse_audio_format,
    parse_channel_count,
    parse_layout,
    parse_sub_format,
    resolve_sub_language,
)
from videoforge.core.models import AudioTrack, SourceInfo, SubTrack, VideoInfo

_SECTION_RE = re.compile(r"^(General|Video|Audio|Text|Menu|Image|Other)(?: #(\d+))?\s*$")


def _sections(text: str) -> list[tuple[str, dict[str, str]]]:
    sections: list[tuple[str, dict[str, str]]] = []
    current: dict[str, str] | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _SECTION_RE.match(line)
        if m:
            current = {}
            sections.append((m.group(1), current))
            continue
        if current is None or ":" not in line:
            continue
        key, _, value = line.partition(":")
        current.setdefault(key.strip(), value.strip())
    return sections


def _number(value: str | None) -> int | None:
    """'1 920 pixels' -> 1920, '2' -> 2."""
    if not value:
        return None
    m = re.match(r"^-?[\d ]+", value.strip())
    if not m:
        return None
    digits = m.group(0).replace(" ", "")
    return int(digits) if digits not in ("", "-") else None


def _kbps(value: str | None) -> int | None:
    if not value:
        return None
    m = re.match(r"^([\d ]+(?:\.\d+)?)\s*(kb/s|Mb/s|b/s)", value.strip())
    if not m:
        return None
    num = float(m.group(1).replace(" ", ""))
    unit = m.group(2)
    if unit == "Mb/s":
        num *= 1000
    elif unit == "b/s":
        num /= 1000
    return round(num)


def _delay_ms(value: str | None) -> int:
    """'-838 ms', '1 s 23 ms', '-1 s 5 ms' -> milliseconds."""
    if not value:
        return 0
    sign = -1 if value.strip().startswith("-") else 1
    total = 0
    for amount, unit in re.findall(r"(\d+)\s*(min|ms|s)\b", value):
        total += int(amount) * {"min": 60000, "s": 1000, "ms": 1}[unit]
    return sign * total


def _yes(value: str | None) -> bool:
    return (value or "").strip().lower().startswith("yes")


def parse_mediainfo_text(text: str, name: str | None = None) -> SourceInfo:
    video: VideoInfo | None = None
    audio: list[AudioTrack] = []
    subs: list[SubTrack] = []
    has_chapters = False
    file_name = name or ""

    for kind, f in _sections(text):
        if kind == "General" and not file_name:
            complete = f.get("Complete name", "")
            file_name = PureWindowsPath(complete).name if complete else ""
        elif kind == "Video" and video is None:
            video = VideoInfo(width=_number(f.get("Width")) or 0, height=_number(f.get("Height")) or 0)
        elif kind == "Menu":
            has_chapters = True
        elif kind == "Audio":
            track_no = _number(f.get("ID"))
            fmt = parse_audio_format(
                f.get("Format"), f.get("Commercial name"), f.get("Format settings, additional")
            )
            channels = parse_channel_count(f.get("Channel(s)"))
            audio.append(
                AudioTrack(
                    id=(track_no - 1) if track_no else len(audio) + 1,
                    index=len(audio),
                    codec=fmt.codec,
                    layout=parse_layout(f.get("Channel layout"), channels),
                    language=lang.from_mediainfo_name(f.get("Language")),
                    title=f.get("Title", ""),
                    default=_yes(f.get("Default")),
                    forced=_yes(f.get("Forced")),
                    atmos=fmt.atmos,
                    dtsx=fmt.dtsx,
                    bitrate_kbps=_kbps(f.get("Bit rate")),
                    delay_ms=_delay_ms(f.get("Delay relative to video")),
                    format_name=f.get("Format", ""),
                )
            )
        elif kind == "Text":
            track_no = _number(f.get("ID"))
            title = f.get("Title", "")
            subs.append(
                SubTrack(
                    id=(track_no - 1) if track_no else len(audio) + len(subs) + 1,
                    index=len(subs),
                    format=parse_sub_format(f.get("Format"), f.get("Codec ID")),
                    language=resolve_sub_language(
                        lang.from_mediainfo_name(f.get("Language")), title
                    ),
                    title=title,
                    default=_yes(f.get("Default")),
                    forced=_yes(f.get("Forced")),
                    hearing_impaired=_yes(f.get("Hearing impaired")),
                    element_count=_number(f.get("Count of elements")),
                    number=track_no,
                )
            )

    return SourceInfo(
        path=None, name=file_name, video=video, audio=audio, subs=subs, has_chapters=has_chapters
    )
