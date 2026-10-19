"""A 2-pass encode's bitrate from a target file size, as StaxRip works it out (Misc.vb Calc.GetVideoBitrate).

    video kb/s = (target - audio - subtitles - attachments - HDR metadata - container overhead) * 8 / 1000 / seconds

The seconds and frames are the script's (its info step), the source's before that; a VFR source's timestamps time
an MKV by the source's length. Pass 1 counts the audio as planned: a copy's stream size (MediaInfo), an encode's
bitrate over the length, qaac TVBR by StaxRip's estimate from its quality (GUIAudioProfile.GetBitrate), FLAC by the
lossless source's bitrate. Pass 2 waits for the audio encodes and counts their files, as StaxRip corrects the
bitrate once the audio is done (AudioProfile.vb). The HDR10+ JSON and Dolby Vision RPU count as their files' sizes
(StaxRip's GetVideoMetadataBytes), the overhead as its bytes per video frame. Unlike StaxRip, subtitles count
their whole size (it takes a third of a demuxed file's; mkvmerge doesn't compress them) and an MKV counts the
source's attachments (the mux keeps them).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from videoforge.core.models import AudioAction, Issue, Plan, PlannedAudio, Severity, VideoInfo
from videoforge.core.video import info, vfr
from videoforge.core.video.settings import EncoderSettings, RateControl

MB = 1_000_000  # StaxRip's size unit (decimal: its binary prefix setting is off by default)
_OVERHEAD_KIB = {"mkv": 0.014, "mp4": 0.013}  # per video frame (Calc.GetOverheadBytes)


@dataclass(frozen=True, slots=True)
class Budget:
    """Where a target size goes, in bytes."""

    target: int
    seconds: float
    audio: int
    subs: int
    attachments: int
    metadata: int  # HDR10+ / Dolby Vision
    overhead: int
    unknown: tuple[str, ...] = ()  # tracks whose size isn't known (counted as nothing)

    @property
    def video(self) -> int:
        return self.target - self.audio - self.subs - self.attachments - self.metadata - self.overhead

    @property
    def kbps(self) -> int:
        """The video's bitrate, rounded down (at least 1, as StaxRip's)."""
        return max(1, int(self.video * 8 / 1000 / self.seconds))


def applies(settings: EncoderSettings) -> bool:
    return settings.rate_control is RateControl.TWO_PASS and settings.target_mb is not None


def length(video: VideoInfo | None, found: info.ScriptInfo | None, container: str) -> tuple[float, int] | None:
    """The encode's seconds and frames: the script's once its info step has run, else the source's. A VFR
    source's MKV is timed by the source's timestamps while the script keeps its frames (vfr.py), so it's as long
    as the source. None when neither says."""
    frames = found.frames if found else (video.frames if video else 0)
    if video is not None and vfr.carries(video, container) and video.duration_ms and frames == video.frames:
        return video.duration_ms / 1000, frames
    if found is not None and found.seconds:
        return found.seconds, found.frames
    if video is None or not video.frames:
        return None
    if video.default_duration_ns and not video.vfr:
        return video.frames * video.default_duration_ns / 1e9, video.frames
    return (video.duration_ms / 1000, video.frames) if video.duration_ms else None


def _file_size(path: Path | None) -> int | None:
    try:
        return path.stat().st_size if path is not None else None
    except OSError:
        return None


def _qaac_tvbr_kbps(quality: int, channels: int) -> float:
    """StaxRip's guess at a qaac TVBR quality's bitrate: 50 kb/s per 8 channels at 0 up to 1000 at 127."""
    low, high = 50 / 8 * channels, 1000 / 8 * channels
    return low + (high - low) * quality / 127


def audio_bytes(a: PlannedAudio, seconds: float) -> int | None:
    """One planned audio track's size before it's encoded; None when it isn't known."""
    if a.action is AudioAction.COPY:
        if a.source.size_bytes:
            return a.source.size_bytes
        kbps: float | None = a.source.bitrate_kbps
    elif a.bitrate_kbps:
        kbps = a.bitrate_kbps
    elif a.action is AudioAction.AAC:
        try:
            quality = int(a.options.get("quality", "127"))
        except ValueError:
            quality = 127
        kbps = _qaac_tvbr_kbps(quality, a.out_layout.channels)
    elif a.action is AudioAction.FLAC and a.source.codec.lossless:
        kbps = a.source.bitrate_kbps
    else:
        kbps = None
    return int(kbps * 1000 / 8 * seconds) if kbps else None


def budget(
    target_mb: int,
    plan: Plan,
    container: str,
    found: info.ScriptInfo | None,
    encoded: Mapping[int, Path] | None = None,
    metadata: Iterable[Path | None] = (),
) -> Budget | None:
    """The target size's budget for the plan's encode, with found the script's info (None before its step has
    run). encoded: plan.audio position -> its encoded file, counted by that file's size where it's there (pass 2).
    metadata: the HDR10+ JSON / Dolby Vision RPU the encode reads (nothing while they aren't extracted). None when
    the encode's length isn't known."""
    video = plan.source.video
    timing = length(video, found, container)
    if timing is None or timing[0] <= 0:
        return None
    seconds, frames = timing
    unknown: list[str] = []
    audio = 0
    for pos, a in enumerate(plan.audio):
        size = _file_size((encoded or {}).get(pos))
        size = size if size is not None else audio_bytes(a, seconds)
        if size is None:
            unknown.append(f"audio {pos + 1} ({a.title or a.language})")
        audio += size or 0
    subs = 0
    for pos, s in enumerate(plan.subs):
        size = _file_size(s.source.external_path) if s.source.is_external else s.source.size_bytes
        if size is None:
            unknown.append(f"subtitle {pos + 1} ({s.title or s.language})")
        subs += size or 0
    return Budget(
        target=target_mb * MB,
        seconds=seconds,
        audio=audio,
        subs=subs,
        attachments=plan.source.attachments_bytes if container == "mkv" else 0,
        metadata=sum(_file_size(p) or 0 for p in metadata),
        overhead=int(frames * _OVERHEAD_KIB.get(container, 0) * 1024),
        unknown=tuple(unknown),
    )


def issues(settings: EncoderSettings, plan: Plan, container: str) -> list[Issue]:
    """A target size that leaves the video nothing (or can't be worked out), and tracks it can't count."""
    if not applies(settings) or settings.target_mb is None:
        return []
    found = budget(settings.target_mb, plan, container, None)
    if found is None:
        return [
            Issue(Severity.BLOCK, "video.target_length", "The source's length isn't known: set a bitrate, not a size")
        ]
    out = []
    if found.video <= 0:
        rest = (found.target - found.video) / MB
        out.append(
            Issue(
                Severity.BLOCK,
                "video.target_small",
                f"The target size ({settings.target_mb} MB) leaves nothing for the video: the rest takes {rest:.0f} MB",
            )
        )
    if found.unknown:
        out.append(
            Issue(
                Severity.WARN,
                "video.target_unknown",
                f"The size of {', '.join(found.unknown)} isn't known: the target size counts it as nothing (an "
                "encoded track's file is counted at pass 2)",
            )
        )
    return out
