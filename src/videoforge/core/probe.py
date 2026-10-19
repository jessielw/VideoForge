"""Probe a local MKV: mkvmerge -J for track ids/flags/languages, MediaInfo for audio detail.

The two are joined on the MKV track number (mkvmerge ``properties.number`` ==
MediaInfo ``track_id``).
"""

from __future__ import annotations

from fractions import Fraction
import json
from pathlib import Path
import subprocess
from typing import Any

from pymediainfo import MediaInfo

from videoforge.core import lang
from videoforge.core.classify import (
    parse_audio_format,
    parse_channel_count,
    parse_layout,
    parse_sub_format,
    resolve_sub_language,
)
from videoforge.core.models import AudioTrack, SourceInfo, SubTrack, VideoInfo
from videoforge.core.video import hdr
from videoforge.core.video.color import from_mediainfo

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class ProbeError(RuntimeError):
    pass


def mkvmerge_identify(path: Path, mkvmerge: str) -> dict[str, Any]:
    result = subprocess.run(
        [mkvmerge, "-J", str(path)],
        capture_output=True,
        check=False,
        encoding="utf-8",
        errors="replace",
        creationflags=_NO_WINDOW,
    )
    if result.returncode not in (0, 1):  # 1 = warnings
        raise ProbeError(f"mkvmerge -J failed for {path.name}: {result.stdout or result.stderr}")
    data = json.loads(result.stdout)
    if not data.get("container", {}).get("recognized", False):
        raise ProbeError(f"{path.name} is not a container mkvmerge recognizes")
    return data


def _ms(ns: int | None) -> int:
    return round((ns or 0) / 1_000_000)


def _default(props: dict[str, Any]) -> bool:
    """Matroska's default flag; an MP4 track has none, its enabled flag plays that part."""
    return bool(props.get("default_track", props.get("enabled_track")))


def _int(value: Any) -> int | None:
    """A MediaInfo number (an int, a float, or text like "48000 / 44100": the first one)."""
    if isinstance(value, (int, float)):
        return int(value)
    head = str(value or "").split("/")[0].strip()
    try:
        return int(float(head)) if head else None
    except ValueError:
        return None


def _sar(width: int, height: int, props: dict[str, Any], mi: Any) -> Fraction:
    """The pixel aspect ratio: from mkvmerge's display size when it has one (exact; it's the container's,
    when it's there: not for an MP4 or a TS), else MediaInfo's, from the stream too. MediaInfo rounds it to
    3 decimals (1.185): the simplest fraction that rounds the same is taken (32:27)."""
    shown = (props.get("display_dimensions") or "").split("x")
    if width > 0 and height > 0 and len(shown) == 2 and all(d.isdigit() and int(d) for d in shown):
        return Fraction(int(shown[0]) * height, int(shown[1]) * width)
    try:
        shown_par = Fraction(str(getattr(mi, "pixel_aspect_ratio", None) or 1))
    except (ValueError, ZeroDivisionError):
        return Fraction(1)
    if shown_par <= 0:
        return Fraction(1)
    simple = shown_par.limit_denominator(100)
    return simple if abs(simple - shown_par) <= Fraction(1, 2000) else shown_par.limit_denominator(10000)


def probe(path: Path, mkvmerge: str) -> SourceInfo:
    ident = mkvmerge_identify(path, mkvmerge)
    mi_all = MediaInfo.parse(str(path)).tracks
    mi_tracks = {t.track_id: t for t in mi_all if t.track_type in ("Video", "Audio", "Text") and t.track_id is not None}
    # A raw stream (.ac3, .flac, ...) has no track ids in MediaInfo: pair its audio tracks by order.
    mi_audio = [t for t in mi_all if t.track_type == "Audio"]

    video: VideoInfo | None = None
    audio: list[AudioTrack] = []
    subs: list[SubTrack] = []

    for track in ident.get("tracks", []):
        props = track.get("properties", {})
        mi = mi_tracks.get(props.get("number"))
        kind = track.get("type")
        language = lang.normalize(props.get("language_ietf") or props.get("language"))
        title = props.get("track_name") or ""

        if kind == "video" and video is None:
            dims = (props.get("pixel_dimensions") or "0x0").split("x")
            width, height = int(dims[0]), int(dims[1])
            if mi is None:  # a raw stream: no track ids to pair by
                mi = next((t for t in mi_all if t.track_type == "Video"), None)
            sar = _sar(width, height, props, mi)
            video = VideoInfo(
                width=width,
                height=height,
                start_ms=_ms(props.get("minimum_timestamp")),
                default_duration_ns=props.get("default_duration"),
                frames=_int(getattr(mi, "frame_count", None)) or 0,
                language=language,
                sar_num=sar.numerator,
                sar_den=sar.denominator,
                color=from_mediainfo(mi),
                hdr=hdr.from_mediainfo(mi),
                id=track["id"],
                vfr=getattr(mi, "frame_rate_mode", None) == "VFR",
                duration_ms=_int(getattr(mi, "duration", None)) or 0,
            )
        elif kind == "audio":
            if mi is None and len(audio) < len(mi_audio) and mi_audio[len(audio)].track_id is None:
                mi = mi_audio[len(audio)]
            fmt = parse_audio_format(
                getattr(mi, "format", None),
                getattr(mi, "commercial_name", None),
                getattr(mi, "format_additionalfeatures", None),
            )
            channels = parse_channel_count(getattr(mi, "channel_s", None)) or props.get("audio_channels")
            bit_rate = getattr(mi, "bit_rate", None)
            lossless = getattr(mi, "compression_mode", None) == "Lossless"
            audio.append(
                AudioTrack(
                    id=track["id"],
                    index=len(audio),
                    codec=fmt.codec,
                    layout=parse_layout(getattr(mi, "channel_layout", None), channels),
                    language=language,
                    title=title,
                    default=_default(props),
                    forced=bool(props.get("forced_track")),
                    hearing_impaired=bool(props.get("flag_hearing_impaired")),
                    commentary=bool(props.get("flag_commentary")),
                    original=bool(props.get("flag_original")),
                    visual_impaired=bool(props.get("flag_visual_impaired")),
                    atmos=fmt.atmos,
                    dtsx=fmt.dtsx,
                    bitrate_kbps=round(bit_rate / 1000) if isinstance(bit_rate, int) else None,
                    delay_ms=int(getattr(mi, "delay_relative_to_video", None) or 0),
                    format_name=getattr(mi, "format", "") or track.get("codec", ""),
                    sample_rate=_int(getattr(mi, "sampling_rate", None)) or props.get("audio_sampling_frequency"),
                    bit_depth=(_int(getattr(mi, "bit_depth", None)) or props.get("audio_bits_per_sample"))
                    if lossless
                    else None,
                    size_bytes=_int(getattr(mi, "stream_size", None)),
                    duration_ms=_int(getattr(mi, "duration", None)),
                )
            )
        elif kind == "subtitles":
            count = props.get("num_index_entries") or getattr(mi, "count_of_elements", None)
            subs.append(
                SubTrack(
                    id=track["id"],
                    index=len(subs),
                    format=parse_sub_format(track.get("codec"), props.get("codec_id")),
                    language=resolve_sub_language(language, title),
                    title=title,
                    default=_default(props),
                    forced=bool(props.get("forced_track")),
                    hearing_impaired=bool(props.get("flag_hearing_impaired")),
                    commentary=bool(props.get("flag_commentary")),
                    original=bool(props.get("flag_original")),
                    visual_impaired=bool(props.get("flag_visual_impaired")),
                    element_count=int(count) if count else None,
                    size_bytes=_int(getattr(mi, "stream_size", None)),
                    number=props.get("number"),
                )
            )

    return SourceInfo(
        path=path,
        name=path.name,
        video=video,
        audio=audio,
        subs=subs,
        has_chapters=bool(ident.get("chapters")),
        attachments_bytes=sum(a.get("size") or 0 for a in ident.get("attachments", [])),
    )
