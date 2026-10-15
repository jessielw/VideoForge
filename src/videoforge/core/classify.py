"""Turn raw MediaInfo/mkvmerge readings into normalized facts.

Shared by the pymediainfo probe and the MediaInfo-text parser so local files and
MediaInfo text reports are judged identically.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from videoforge.core import lang
from videoforge.core.models import AudioCodec, Layout, SubFormat

_FALLBACK_LAYOUTS = {1: Layout(1, 0), 2: Layout(2, 0), 6: Layout(5, 1), 8: Layout(7, 1)}


def parse_layout(channel_layout: str | None, channels: int | None) -> Layout:
    """Layout from MediaInfo's channel layout ("L R C LFE Ls Rs"), else from the count.

    Legacy display can show "full / core" ("L R C LFE Ls Rs Lb Rb / L R C LFE Ls Rs");
    the first (full) segment wins. "Objects" (DTS:X) is not a channel.
    """
    if channel_layout:
        first = channel_layout.split("/")[0]
        tokens = [t for t in first.split() if t.lower() != "objects"]
        if tokens:
            lfe = sum(1 for t in tokens if t.upper().startswith("LFE"))
            return Layout(len(tokens) - lfe, lfe)
    if channels:
        return _FALLBACK_LAYOUTS.get(channels, Layout(channels, 0))
    return Layout(2, 0)


def parse_channel_count(value: object) -> int | None:
    """Highest channel count in a MediaInfo value (8, "8", "8 channels / 6 channels")."""
    if isinstance(value, int):
        return value
    nums = [int(n) for n in re.findall(r"\d+", str(value or ""))]
    return max(nums) if nums else None


@dataclass(frozen=True, slots=True)
class AudioFormat:
    codec: AudioCodec
    atmos: bool
    dtsx: bool


def parse_audio_format(
    fmt: str | None, commercial_name: str | None = None, additional: str | None = None
) -> AudioFormat:
    """Codec from MediaInfo format fields.

    Handles both pymediainfo ("E-AC-3" + additional "JOC") and MediaInfo text
    ("E-AC-3 JOC", "MLP FBA 16-ch", "DTS XLL X", "AAC LC").
    """
    fmt = (fmt or "").strip()
    commercial = commercial_name or ""
    tokens = set(fmt.upper().split()) | set((additional or "").upper().split())
    head = fmt.upper().split()[0] if fmt else ""
    atmos = "ATMOS" in commercial.upper()

    if head == "AAC":
        return AudioFormat(AudioCodec.AAC, False, False)
    if head == "AC-3":
        return AudioFormat(AudioCodec.AC3, False, False)
    if head == "E-AC-3":
        return AudioFormat(AudioCodec.EAC3, atmos or "JOC" in tokens, False)
    if head in ("MLP", "TRUEHD"):
        return AudioFormat(AudioCodec.TRUEHD, atmos or "16-CH" in tokens, False)
    if head == "DTS":
        dtsx = "X" in tokens or "DTS:X" in commercial.upper()
        if "XLL" in tokens or "MASTER AUDIO" in commercial.upper():
            return AudioFormat(AudioCodec.DTS_HD_MA, False, dtsx)
        if "XBR" in tokens or "HIGH RESOLUTION" in commercial.upper():
            return AudioFormat(AudioCodec.DTS_HD_HRA, False, dtsx)
        return AudioFormat(AudioCodec.DTS, False, dtsx)
    if head == "PCM":
        return AudioFormat(AudioCodec.LPCM, False, False)
    if head == "FLAC":
        return AudioFormat(AudioCodec.FLAC, False, False)
    if head == "OPUS":
        return AudioFormat(AudioCodec.OPUS, False, False)
    return AudioFormat(AudioCodec.OTHER, atmos, False)


def parse_sub_format(fmt: str | None, codec_id: str | None = None) -> SubFormat:
    value = f"{fmt or ''} {codec_id or ''}".upper()
    if "UTF-8" in value or "S_TEXT/UTF8" in value or "SUBRIP" in value or "SRT" in value:
        return SubFormat.SRT
    if "PGS" in value:
        return SubFormat.PGS
    if "ASS" in value or "SSA" in value:
        return SubFormat.ASS
    if "VOBSUB" in value or "S_VOBSUB" in value:
        return SubFormat.VOBSUB
    if "TIMED TEXT" in value or "TX3G" in value:
        return SubFormat.TX3G
    return SubFormat.OTHER


def resolve_sub_language(raw_tag: str, title: str) -> str:
    """Normalized tag, filling a missing family variant from the title."""
    tag = lang.normalize(raw_tag)
    base = lang.base_of(tag)
    if base in lang.FAMILY_VARIANTS and not lang.has_variant(tag):
        return lang.variant_from_title(base, title) or tag
    return tag
