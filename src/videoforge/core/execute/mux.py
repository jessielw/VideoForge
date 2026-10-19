"""The single mux pass that builds a release from a plan: mkvmerge (MKV) or MP4Box (MP4).

mkvmerge:
Inputs, in order: the encode (video only), the source (copied audio and
subtitles, its attachments and global tags), then one file per encoded audio track, per copied track of an added
audio file or copy of a track (Overrides.copies: mkvmerge takes a track once per
input), and per external subtitle.

Timing: the encode starts at 0. Source tracks are shifted by the source video's
start offset so they line up with it. DeeZy output already carries the source's
"delay relative to video"; AAC starts at its first sample, so it gets the delay
here. A copied track of an added audio file gets its own delay (e.g. from
"DELAY 42ms" in its name).
gMKVExtract SRTs keep the source's container timestamps, so they get the same
shift as the source tracks; other external SRTs are used as timed.

MP4Box takes the same inputs and timing (`:delay=`), each track straight from its
file (`#trackID=` = mkvmerge id + 1). MP4 has no track flags as such: the default
track of each kind is the enabled one in its alternate group, a forced SRT gets
the timed-text forced flags, and the other flags are left out (a WARN says so).
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
import re
import shlex
from typing import Protocol

from videoforge.core.config import AppConfig
from videoforge.core.execute.audio import delay_in_encode
from videoforge.core.models import (
    AudioAction,
    AudioCodec,
    Issue,
    Plan,
    PlannedAudio,
    PlannedSub,
    Severity,
    SubFormat,
    VideoInfo,
    track_key,
)

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


def _raw_rate(video: VideoInfo | None, fps: Fraction | None) -> str:
    """A raw encode's frame rate as MP4Box takes it ("24000/1001"): the script's (fps), else the source's."""
    if fps:
        return str(fps)
    if not (video and video.default_duration_ns):
        raise MuxError("Raw encode needs the source frame rate, and the source has none")
    return _known_rate(video.default_duration_ns) or f"1000000000/{video.default_duration_ns}"


def _flag(on: bool) -> str:
    return "1" if on else "0"


def _track_args(tid: int, t: PlannedAudio | PlannedSub) -> list[str]:
    """Language, name and every flag, set explicitly so nothing is inherited from the input file."""
    return [
        "--language",
        f"{tid}:{t.language}",
        "--track-name",
        f"{tid}:{t.title}",
        "--default-track-flag",
        f"{tid}:{_flag(t.default)}",
        "--forced-display-flag",
        f"{tid}:{_flag(t.forced)}",
        "--hearing-impaired-flag",
        f"{tid}:{_flag(t.hearing_impaired)}",
        "--commentary-flag",
        f"{tid}:{_flag(t.commentary)}",
        "--original-flag",
        f"{tid}:{_flag(t.original)}",
        "--visual-impaired-flag",
        f"{tid}:{_flag(t.visual_impaired)}",
    ]


def _sync(tid: int, ms: int) -> list[str]:
    return ["--sync", f"{tid}:{ms}"] if ms else []


def mux_command(
    plan: Plan,
    encoded_audio: dict[int, Path],
    output: Path,
    mkvmerge: str,
    raw_extensions: tuple[str, ...],
    extra: list[str] | None = None,
    fps: Fraction | None = None,
) -> list[str]:
    """mkvmerge argv for a plan. encoded_audio maps plan.audio positions to their encoded files;
    extra (the user's arguments) goes before the first input. fps is a raw encode's frame rate (the script's,
    which an IVTC or a double-rate deinterlace changed); without it, the source's."""
    if plan.encode_path is None or plan.source.path is None:
        raise MuxError("Plan has no encode or no source file")
    video = plan.source.video
    start_ms = video.start_ms if video else 0
    external_chapters = plan.chapters_path is not None

    argv: list[str] = [mkvmerge, "--output", str(output), *(extra or [])]
    order: list[str] = ["0:0"]

    # 0: the encode, video only.
    if plan.encode_path.suffix.lower() in raw_extensions:
        if fps:
            rate = f"{fps}p"
        elif video and video.default_duration_ns:
            rate = _frame_rate(video.default_duration_ns)
        else:
            raise MuxError("Raw encode needs the source frame rate, and the source has none")
        argv += ["--default-duration", f"0:{rate}"]
    else:
        # Chapters come from the qpf file or the source, never the encode.
        argv += [
            "--video-tracks",
            "0",
            "--no-audio",
            "--no-subtitles",
            "--no-chapters",
            "--no-attachments",
            "--no-global-tags",
        ]
    argv += [
        "--language",
        f"0:{video.language if video else 'und'}",
        "--default-track-flag",
        "0:1",
        str(plan.encode_path),
    ]

    # 1: the source, copied audio and subtitles, and its attachments (an ASS subtitle's fonts) and global tags
    # (as StaxRip carries them).
    copied = [a for a in plan.audio if a.action is AudioAction.COPY and not a.source.is_external and not a.source.copy]
    internal_subs = [s for s in plan.subs if not s.source.is_external]
    argv += ["--no-video"]
    if external_chapters:
        argv += ["--no-chapters"]
    argv += ["--audio-tracks", ",".join(str(a.source.id) for a in copied)] if copied else ["--no-audio"]
    argv += (
        ["--subtitle-tracks", ",".join(str(s.source.id) for s in internal_subs)]
        if internal_subs
        else ["--no-subtitles"]
    )
    for a in copied:
        argv += _track_args(a.source.id, a) + _sync(a.source.id, -start_ms)
    for s in internal_subs:
        argv += _track_args(s.source.id, s) + _sync(s.source.id, -start_ms)
    argv.append(str(plan.source.path))

    # 2+: encoded audio and external subtitles, one file each.
    file_id = 2
    audio_order: list[str] = []
    for pos, a in enumerate(plan.audio):
        if a.action is AudioAction.COPY and (a.source.is_external or a.source.copy):
            tid = a.source.id
            argv += [
                "--no-video",
                "--no-subtitles",
                "--no-chapters",
                "--no-attachments",
                "--no-global-tags",
                "--audio-tracks",
                str(tid),
            ]
            shift = a.source.delay_ms if a.source.is_external else -start_ms
            argv += _track_args(tid, a) + _sync(tid, shift)
            argv.append(str(a.source.external_path or plan.source.path))
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


def _mp4_title(title: str) -> str:
    """MP4Box splits its track options on ':' and has no escape for it."""
    return re.sub(r"\s*:\s*", " - ", title).strip(" -")


def _set_by_hand(plan: Plan, t: PlannedAudio | PlannedSub, flag: str) -> bool:
    ov = plan.overrides.tracks.get(track_key(t.source))
    return bool(ov and ov.flags.get(flag))


# Plan flags an MP4 can't carry (default is the enabled track; forced only on timed text). An original
# flag carried over from the source (most releases set it on every track) is left out without a warning;
# one set by hand in the track editor warns like the others.
_MP4_DROPPED = ("hearing_impaired", "commentary", "original", "visual_impaired")
_MP4_FORCED_TEXT = "C0000000"  # tx3g display flags: some + all samples forced


def _mp4_options(t: PlannedAudio | PlannedSub, group: int, delay_ms: int) -> str:
    opts = [f"lang={t.language}", f"group={group}"]
    if t.title:
        opts.append(f"name={_mp4_title(t.title)}")
    if not t.default:
        opts.append("disable")
    if delay_ms:
        opts.append(f"delay={delay_ms}")
    if isinstance(t, PlannedSub) and t.forced and t.source.format is SubFormat.SRT:
        opts.append(f"txtflags={_MP4_FORCED_TEXT}")
    return ":" + ":".join(opts)


def mp4box_command(
    plan: Plan,
    encoded_audio: dict[int, Path],
    output: Path,
    mp4box: str,
    raw_extensions: tuple[str, ...],
    extra: list[str] | None = None,
    fps: Fraction | None = None,
) -> list[str]:
    """MP4Box argv for a plan (the same inputs, timing and fps as mux_command). chapters_path must
    be OGM text; extra goes just before -new."""
    if plan.encode_path is None or plan.source.path is None:
        raise MuxError("Plan has no encode or no source file")
    video = plan.source.video
    start_ms = video.start_ms if video else 0

    argv: list[str] = [mp4box, "-noprog"]
    # the source's language; an empty handler name (MP4Box would write its own, e.g. "264:fps=24@GPAC..."); no HDR
    # boxes (hdr=none): the stream's own SEI carries it, and MediaInfo would list it twice
    opts = f":hdr=none:lang={video.language if video else 'und'}:name="
    if plan.encode_path.suffix.lower() in raw_extensions:
        argv += ["-add", f"{plan.encode_path}:fps={_raw_rate(video, fps)}{opts}"]
    else:
        argv += ["-add", f"{plan.encode_path}#video{opts}"]

    for pos, a in enumerate(plan.audio):
        if a.action is AudioAction.COPY:
            path = a.source.external_path or plan.source.path
            delay = a.source.delay_ms if a.source.is_external else -start_ms
            argv += ["-add", f"{path}#trackID={a.source.id + 1}" + _mp4_options(a, 1, delay)]
            continue
        encoded = encoded_audio.get(pos)
        if encoded is None:
            raise MuxError(f"No encoded file for audio {pos + 1} ({a.title})")
        delay = 0 if delay_in_encode(a.action) else a.source.delay_ms
        argv += ["-add", str(encoded) + _mp4_options(a, 1, delay)]

    for s in plan.subs:
        if s.source.is_external:
            delay = -start_ms if s.source.extracted_from is not None else 0
            argv += ["-add", str(s.source.external_path) + _mp4_options(s, 2, delay)]
        else:
            argv += ["-add", f"{plan.source.path}#trackID={s.source.id + 1}" + _mp4_options(s, 2, -start_ms)]

    if plan.chapters_path is not None:
        argv += ["-chap", str(plan.chapters_path)]
    argv += [*(extra or []), "-new", str(output)]
    return argv


def split_args(text: str) -> list[str]:
    """The user's extra arguments, split like a command line (Windows paths keep their backslashes)."""
    return shlex.split(text, posix=False)


@dataclass(slots=True)
class MuxSettings:
    """A job's muxer: the container ("" = the profile's) and extra arguments for its tool."""

    container: str = ""
    extra: str = ""


class Muxer(Protocol):
    """Builds the final container from a plan."""

    label: str
    extension: str
    tool: str  # the Tools field it runs
    carries_titles: bool  # titles and every flag can be read back by the output check

    def command(
        self,
        plan: Plan,
        encoded_audio: dict[int, Path],
        output: Path,
        app: AppConfig,
        extra: list[str] | None = None,
        fps: Fraction | None = None,
    ) -> list[str]:
        """fps: a raw encode's frame rate (the script's); None for the source's."""
        ...

    def issues(self, plan: Plan) -> list[Issue]:
        """What this container can't hold as planned: BLOCK (can't mux) or WARN (left out)."""
        ...

    def written_format(self, fmt: SubFormat) -> SubFormat:
        """A subtitle format as the output holds it."""
        ...


class MkvMerge:
    label = "MKV (mkvmerge)"
    extension = ".mkv"
    tool = "mkvmerge"
    carries_titles = True

    def command(
        self,
        plan: Plan,
        encoded_audio: dict[int, Path],
        output: Path,
        app: AppConfig,
        extra: list[str] | None = None,
        fps: Fraction | None = None,
    ) -> list[str]:
        return mux_command(plan, encoded_audio, output, app.tools.mkvmerge, app.matching.encode_extensions, extra, fps)

    def issues(self, plan: Plan) -> list[Issue]:
        return []

    def written_format(self, fmt: SubFormat) -> SubFormat:
        return fmt


class Mp4Box:
    label = "MP4 (MP4Box)"
    extension = ".mp4"
    tool = "mp4box"
    carries_titles = False  # mkvmerge doesn't read MP4 handler names or kinds back

    SUBS = (SubFormat.SRT, SubFormat.TX3G, SubFormat.VOBSUB)

    def command(
        self,
        plan: Plan,
        encoded_audio: dict[int, Path],
        output: Path,
        app: AppConfig,
        extra: list[str] | None = None,
        fps: Fraction | None = None,
    ) -> list[str]:
        return mp4box_command(plan, encoded_audio, output, app.tools.mp4box, app.matching.encode_extensions, extra, fps)

    def issues(self, plan: Plan) -> list[Issue]:
        issues: list[Issue] = []
        for i, a in enumerate(plan.audio, 1):
            if a.out_codec in (AudioCodec.LPCM, AudioCodec.OTHER):
                issues.append(
                    Issue(
                        Severity.BLOCK,
                        "mux.mp4_audio",
                        f"Audio {i} ({a.out_codec.value}) can't go into MP4: encode it (e.g. FLAC) or use MKV",
                    )
                )
        for i, s in enumerate(plan.subs, 1):
            if s.source.format not in self.SUBS:
                issues.append(
                    Issue(
                        Severity.BLOCK,
                        "mux.mp4_subs",
                        f"Subtitle {i} ({s.source.format.value}) can't go into MP4 (SRT and VobSub can): "
                        "leave it out or use MKV",
                    )
                )
        kinds: tuple[tuple[str, list[PlannedAudio] | list[PlannedSub]], ...] = (
            ("Audio", plan.audio),
            ("Subtitle", plan.subs),
        )
        for label, tracks in kinds:
            for i, t in enumerate(tracks, 1):
                dropped = [
                    k.replace("_", " ")
                    for k in _MP4_DROPPED
                    if getattr(t, k) and (k != "original" or _set_by_hand(plan, t, k))
                ]
                if t.forced and not (isinstance(t, PlannedSub) and t.source.format is SubFormat.SRT):
                    dropped.insert(0, "forced")
                if dropped:
                    issues.append(
                        Issue(
                            Severity.WARN,
                            "mux.mp4_flags",
                            f"{label} {i}: MP4 has no {', '.join(dropped)} flag; left out",
                        )
                    )
                if t.title and _mp4_title(t.title) != t.title:
                    issues.append(
                        Issue(
                            Severity.WARN,
                            "mux.mp4_title",
                            f"{label} {i}: MP4Box can't write ':' in a title; written as '{_mp4_title(t.title)}'",
                        )
                    )
        return issues

    def written_format(self, fmt: SubFormat) -> SubFormat:
        return SubFormat.TX3G if fmt is SubFormat.SRT else fmt


MUXERS: dict[str, Muxer] = {"mkv": MkvMerge(), "mp4": Mp4Box()}


def muxer_for(output: Path) -> Muxer:
    """The muxer that writes files like this one (by extension); mkvmerge's for anything else."""
    return next((m for m in MUXERS.values() if m.extension == output.suffix.lower()), MUXERS["mkv"])


def mux_issues(plan: Plan, container: str) -> list[Issue]:
    """What the container can't hold as planned."""
    return MUXERS[container].issues(plan)
