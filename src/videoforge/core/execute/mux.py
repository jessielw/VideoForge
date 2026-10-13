"""The single mkvmerge pass that builds a release from a plan.

Inputs, in order: the encode (video only), the source (copied audio and
subtitles), then one file per encoded audio track, per copied track of an added
audio file, and per external subtitle.

Timing: the encode starts at 0. Source tracks are shifted by the source video's
start offset so they line up with it. DeeZy output already carries the source's
"delay relative to video"; AAC starts at its first sample, so it gets the delay
here. A copied track of an added audio file gets its own delay (e.g. from
"DELAY 42ms" in its name).
gMKVExtract SRTs keep the source's container timestamps, so they get the same
shift as the source tracks; other external SRTs are used as timed.
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from typing import Protocol

from videoforge.core.config import AppConfig
from videoforge.core.execute.audio import delay_in_encode
from videoforge.core.models import AudioAction, Plan, PlannedAudio, PlannedSub

# Frame durations (ns) of common rates, so a raw stream gets an exact fraction
# instead of a rounded nanosecond value.
_RATES = ("24000/1001", "24", "25", "30000/1001", "30", "48", "50", "60000/1001", "60")
_TOLERANCE_NS = 2


class MuxError(ValueError):
    pass


def _known_rate(default_duration_ns: int) -> str | None:
    for rate in _RATES:
        num, _, den = rate.partition("/")
        if abs(1e9 * int(den or 1) / int(num) - default_duration_ns) <= _TOLERANCE_NS:
            return rate
    return None


def frame_rate(default_duration_ns: int) -> Fraction:
    """The exact rate behind a container's (rounded) frame duration, e.g. 41708333 ns -> 24000/1001."""
    rate = _known_rate(default_duration_ns)
    return Fraction(rate) if rate else Fraction(1_000_000_000, default_duration_ns)


def _frame_rate(default_duration_ns: int) -> str:
    rate = _known_rate(default_duration_ns)
    return f"{rate}p" if rate else f"{default_duration_ns}ns"


def _flag(on: bool) -> str:
    return "1" if on else "0"


def _track_args(tid: int, t: PlannedAudio | PlannedSub) -> list[str]:
    """Language, name and every flag, set explicitly so nothing is inherited from the input file."""
    return [
        "--language", f"{tid}:{t.language}",
        "--track-name", f"{tid}:{t.title}",
        "--default-track-flag", f"{tid}:{_flag(t.default)}",
        "--forced-display-flag", f"{tid}:{_flag(t.forced)}",
        "--hearing-impaired-flag", f"{tid}:{_flag(t.hearing_impaired)}",
        "--commentary-flag", f"{tid}:{_flag(t.commentary)}",
        "--original-flag", f"{tid}:{_flag(t.original)}",
    ]


def _sync(tid: int, ms: int) -> list[str]:
    return ["--sync", f"{tid}:{ms}"] if ms else []


def mux_command(
    plan: Plan,
    encoded_audio: dict[int, Path],
    output: Path,
    mkvmerge: str,
    raw_extensions: tuple[str, ...],
) -> list[str]:
    """mkvmerge argv for a plan. encoded_audio maps plan.audio positions to their encoded files."""
    if plan.encode_path is None or plan.source.path is None:
        raise MuxError("Plan has no encode or no source file")
    video = plan.source.video
    start_ms = video.start_ms if video else 0
    external_chapters = plan.chapters_path is not None

    argv: list[str] = [mkvmerge, "--output", str(output)]
    order: list[str] = ["0:0"]

    # 0: the encode, video only.
    if plan.encode_path.suffix.lower() in raw_extensions:
        if not (video and video.default_duration_ns):
            raise MuxError("Raw encode needs the source frame rate, and the source has none")
        argv += ["--default-duration", f"0:{_frame_rate(video.default_duration_ns)}"]
    else:
        # Chapters come from the qpf file or the source, never the encode.
        argv += ["--video-tracks", "0", "--no-audio", "--no-subtitles", "--no-chapters", "--no-attachments", "--no-global-tags"]
    argv += ["--default-track-flag", "0:1", str(plan.encode_path)]

    # 1: the source, copied audio and subtitles only.
    copied = [a for a in plan.audio if a.action is AudioAction.COPY and not a.source.is_external]
    internal_subs = [s for s in plan.subs if not s.source.is_external]
    argv += ["--no-video", "--no-attachments", "--no-global-tags"]
    if external_chapters:
        argv += ["--no-chapters"]
    argv += ["--audio-tracks", ",".join(str(a.source.id) for a in copied)] if copied else ["--no-audio"]
    argv += ["--subtitle-tracks", ",".join(str(s.source.id) for s in internal_subs)] if internal_subs else ["--no-subtitles"]
    for a in copied:
        argv += _track_args(a.source.id, a) + _sync(a.source.id, -start_ms)
    for s in internal_subs:
        argv += _track_args(s.source.id, s) + _sync(s.source.id, -start_ms)
    argv.append(str(plan.source.path))

    # 2+: encoded audio and external subtitles, one file each.
    file_id = 2
    audio_order: list[str] = []
    for pos, a in enumerate(plan.audio):
        if a.action is AudioAction.COPY and a.source.is_external:
            tid = a.source.id
            argv += ["--no-video", "--no-subtitles", "--no-chapters", "--no-attachments", "--no-global-tags",
                     "--audio-tracks", str(tid)]
            argv += _track_args(tid, a) + _sync(tid, a.source.delay_ms)
            argv.append(str(a.source.external_path))
            audio_order.append(f"{file_id}:{tid}")
            file_id += 1
            continue
        if a.action is AudioAction.COPY:
            audio_order.append(f"1:{a.source.id}")
            continue
        path = encoded_audio.get(pos)
        if path is None:
            raise MuxError(f"No encoded file for audio {pos + 1} ({a.title})")
        argv += _track_args(0, a)
        if not delay_in_encode(a.action):
            argv += _sync(0, a.source.delay_ms)
        argv.append(str(path))
        audio_order.append(f"{file_id}:0")
        file_id += 1

    sub_order: list[str] = []
    for s in plan.subs:
        if not s.source.is_external:
            sub_order.append(f"1:{s.source.id}")
            continue
        argv += ["--sub-charset", "0:UTF-8"]
        argv += _track_args(0, s)
        if s.source.extracted_from is not None:
            argv += _sync(0, -start_ms)
        argv.append(str(s.source.external_path))
        sub_order.append(f"{file_id}:0")
        file_id += 1

    if external_chapters:
        argv += ["--chapters", str(plan.chapters_path)]
    argv += ["--track-order", ",".join(order + audio_order + sub_order)]
    return argv


class Muxer(Protocol):
    """Builds the final container from a plan; a profile picks one by its container."""

    extension: str

    def command(self, plan: Plan, encoded_audio: dict[int, Path], output: Path, app: AppConfig) -> list[str]: ...


class MkvMerge:
    extension = ".mkv"

    def command(self, plan: Plan, encoded_audio: dict[int, Path], output: Path, app: AppConfig) -> list[str]:
        return mux_command(plan, encoded_audio, output, app.tools.mkvmerge, app.matching.encode_extensions)


# An MP4 muxer (another group's profile) registers here.
MUXERS: dict[str, Muxer] = {"mkv": MkvMerge()}
