"""Probe a source (MKV, MP4, M2TS / TS): mkvmerge -J for track ids/flags/languages, MediaInfo for detail.

The two are joined on the track number (mkvmerge ``properties.number`` == MediaInfo ``track_id``: the MKV
track number, the MP4 track ID, the TS PID). A Blu-ray TrueHD PID carries an AC-3 core that mkvmerge lists as
a track of its own, under the same number; MediaInfo has one track for the PID, the TrueHD's.

Outside Matroska, ffprobe (its stream headers: quick) gives the timing: each track's start, as a player starts
it (an MP4's edit lists, a TS's timestamps), for the audio's delay to the video, and the exact frame rate.
MediaInfo misses some MP4 edit lists, and has no frame rate for an x264 TS; it's the fallback without ffprobe.
Its streams are joined on the number too (``id``), in mkvmerge's order (ffmpeg splits the AC-3 core out too).
A TS's video start (``VideoInfo.start_ms``) is its offset to the earliest stream, from which mkvmerge times it.
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
from videoforge.core.video.remux import MATROSKA

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


TS = "MPEG transport stream"  # mkvmerge's container type for a TS / M2TS


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


def ffprobe_streams(path: Path, ffprobe: str) -> list[dict[str, Any]]:
    """ffprobe's streams (id, type, start time, frame rates); [] when it isn't there or can't read the file."""
    entries = "stream=id,codec_type,start_time,avg_frame_rate,r_frame_rate"
    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", entries, "-of", "json", str(path)],
            capture_output=True,
            check=False,
            encoding="utf-8",
            errors="replace",
            creationflags=_NO_WINDOW,
            timeout=120,
        )
        streams = json.loads(result.stdout).get("streams", []) if result.returncode == 0 else []
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return []
    return streams if isinstance(streams, list) else []


def _by_number(streams: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    """ffprobe's streams by track number (its id: "0x1100"), in its order."""
    out: dict[int, list[dict[str, Any]]] = {}
    for s in streams:
        try:
            out.setdefault(int(str(s.get("id")), 16), []).append(s)
        except ValueError:
            continue
    return out


def _start(stream: dict[str, Any] | None) -> float | None:
    try:
        return float(stream["start_time"]) if stream is not None else None
    except (KeyError, TypeError, ValueError):
        return None


def _ff_rate(stream: dict[str, Any] | None) -> Fraction | None:
    """ffprobe's frame rate: the average (a Blu-ray VC-1's r_frame_rate is the field rate), else the base one."""
    for key in ("avg_frame_rate", "r_frame_rate"):
        try:
            rate = Fraction(str((stream or {}).get(key) or "0"))
        except (ValueError, ZeroDivisionError):
            continue
        if rate > 0:
            return rate
    return None


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


_NTSC = (24, 30, 48, 60, 120)  # the 1000/1001 rates MediaInfo writes rounded (23.976)


def _rate_ns(rate: Fraction | None) -> int | None:
    """A frame rate's frame duration. A rounded NTSC rate is taken as the exact one (23.976 -> 24000/1001), as
    mkvmerge would time it."""
    if rate is None or rate <= 0:
        return None
    rate = next((Fraction(n * 1000, 1001) for n in _NTSC if abs(rate - Fraction(n * 1000, 1001)) < 0.002), rate)
    return round(1_000_000_000 / rate)


def _frame_ns(mi: Any) -> int | None:
    """The frame duration from MediaInfo's frame rate: an MP4's or a TS's (mkvmerge has one for an MKV only)."""
    try:
        return _rate_ns(Fraction(str(getattr(mi, "frame_rate", None) or 0)))
    except (ValueError, ZeroDivisionError):
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


def _delay(mi: Any, video_mi: Any) -> int:
    """An audio track's delay to the video in ms, as MediaInfo has it (without ffprobe's start times): its
    Video_Delay (an MKV's, a TS's), else the tracks' MP4 edit lists (Source_Delay), where it lists them. An empty edit starts a track late; a skipped start (B-frame reordering, encoder priming) is
    negative and starts it at 0, as a player shows it."""
    relative = getattr(mi, "delay_relative_to_video", None)
    if relative is not None:
        return int(relative)
    edit = _int(getattr(mi, "source_delay", None))
    if edit is None:
        return 0
    return max(edit, 0) - max(_int(getattr(video_mi, "source_delay", None)) or 0, 0)


def probe(path: Path, mkvmerge: str, ffprobe: str = "") -> SourceInfo:
    """The source's tracks. With ffprobe, a source that isn't Matroska is timed by it too."""
    ident = mkvmerge_identify(path, mkvmerge)
    streams = ffprobe_streams(path, ffprobe) if ffprobe and path.suffix.lower() not in MATROSKA else []
    ff_tracks = _by_number(streams)
    ff_video_start = _start(next((s for s in streams if s.get("codec_type") == "video"), None))
    ff_starts = [t for t in (_start(s) for s in streams) if t is not None]
    container = str(ident.get("container", {}).get("type") or "")

    def ff_delay(stream: dict[str, Any] | None) -> int | None:
        start = _start(stream)
        return round((start - ff_video_start) * 1000) if start is not None and ff_video_start is not None else None

    ff_seen: dict[int, int] = {}  # tracks taken so far per number (a TrueHD, then its AC-3 core)
    mi_all = MediaInfo.parse(str(path)).tracks
    mi_tracks = {t.track_id: t for t in mi_all if t.track_type in ("Video", "Audio", "Text") and t.track_id is not None}
    # A raw stream (.ac3, .flac, ...) has no track ids in MediaInfo: pair its audio tracks by order.
    mi_audio = [t for t in mi_all if t.track_type == "Audio"]
    mi_video = next((t for t in mi_all if t.track_type == "Video"), None)

    video: VideoInfo | None = None
    audio: list[AudioTrack] = []
    subs: list[SubTrack] = []

    for track in ident.get("tracks", []):
        props = track.get("properties", {})
        number = props.get("number")
        mi = mi_tracks.get(number)
        kind = track.get("type")
        ff = None
        if isinstance(number, int):
            taken = ff_seen.get(number, 0)
            ff_seen[number] = taken + 1
            same = ff_tracks.get(number, [])
            ff = same[taken] if taken < len(same) else None
        language = lang.normalize(props.get("language_ietf") or props.get("language"))
        title = props.get("track_name") or ""

        if kind == "video" and video is None:
            dims = (props.get("pixel_dimensions") or "0x0").split("x")
            width, height = int(dims[0]), int(dims[1])
            if mi is None:  # a raw stream: no track ids to pair by
                mi = mi_video
            sar = _sar(width, height, props, mi)
            video = VideoInfo(
                width=width,
                height=height,
                start_ms=_ms(props.get("minimum_timestamp"))
                if not (container == TS and ff_starts and ff_video_start is not None)
                else round((ff_video_start - min(ff_starts)) * 1000),
                default_duration_ns=props.get("default_duration") or _rate_ns(_ff_rate(ff)) or _frame_ns(mi),
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
            pid = mi  # the stream's own: its delay holds for a core in it too
            delay = ff_delay(ff)
            core = track["id"] in (props.get("multiplexed_tracks") or [])[1:]
            if core:
                mi = None  # MediaInfo's track is the TrueHD's; mkvmerge's details are the core's
            fmt = parse_audio_format(
                getattr(mi, "format", None) or track.get("codec"),
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
                    delay_ms=_delay(pid, mi_video) if delay is None else delay,
                    format_name=getattr(mi, "format", "") or track.get("codec", ""),
                    sample_rate=_int(getattr(mi, "sampling_rate", None)) or props.get("audio_sampling_frequency"),
                    bit_depth=(_int(getattr(mi, "bit_depth", None)) or props.get("audio_bits_per_sample"))
                    if lossless
                    else None,
                    size_bytes=_int(getattr(mi, "stream_size", None)),
                    duration_ms=_int(getattr(mi, "duration", None)),
                    number=props.get("number"),
                    core=core,
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
                    delay_ms=ff_delay(ff) or 0,
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
        container=container,
    )
