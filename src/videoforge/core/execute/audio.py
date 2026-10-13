"""Audio encodes: what each one makes (ENCODES) and the command for a planned track.

DeeZy makes DDP and DDP Atmos, ffmpeg | qaac makes AAC, and ffmpeg's own encoders
make FLAC, Opus, AAC, AC-3 and E-AC-3. ENCODES is the one list the planner, the tool
checks and the UI read: a new encode is an AudioAction, an entry here and its command.

Delay: the source's "delay relative to video" is applied exactly once. DeeZy
never reads it from the container (only from --delay or a "DELAY Xms" file name
token), so we pass it explicitly; DeeZy bakes it into the stream (padding or
trimming, plus DEE's own priming) and the output starts at 0. ffmpeg (alone or
into qaac) starts at the first audio sample, so those get the delay at mux
(mkvmerge --sync).
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path

from videoforge.core.config import Tools
from videoforge.core.models import AudioAction, AudioCodec, Layout, PlannedAudio


def _layouts(*names: str) -> tuple[Layout, ...]:
    return tuple(Layout.parse(n) for n in names)


@dataclass(frozen=True, slots=True)
class EncodeOption:
    """One setting of an encode, kept as text in TrackOverride.options / PlannedAudio.options."""

    key: str
    label: str
    default: str
    choices: tuple[tuple[str, str], ...] = ()  # (value, label); a pick list when set
    int_range: tuple[int, int] | None = None  # a whole number in this range when set
    help: str = ""  # anything else is free text

    def problem(self, value: str) -> str:
        """Why this value can't be used ("" when it can)."""
        if self.choices and value not in {v for v, _ in self.choices}:
            return f"{self.label} must be one of {', '.join(v for v, _ in self.choices)}"
        if self.int_range:
            lo, hi = self.int_range
            if not value.lstrip("-").isdigit() or not lo <= int(value) <= hi:
                return f"{self.label} must be a whole number from {lo} to {hi}"
        if not self.choices and not self.int_range and value.count('"') % 2:
            return f"{self.label} has an unclosed quote"
        return ""


_EXTRA = EncodeOption("extra", "Extra ffmpeg arguments", "", help="Added before the output file, e.g. -cutoff 20000")
_DIALNORM = EncodeOption("dialnorm", "Dialogue level (dialnorm)", "-31", int_range=(-31, -1),
                         help="-31 leaves the level alone; players turn quieter dialogue up")


AC3_BITRATES = (32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384, 448, 512, 576, 640)


@dataclass(frozen=True, slots=True)
class AudioEncode:
    """One way to encode an audio track."""

    action: AudioAction
    label: str
    codec: AudioCodec
    suffix: str  # of the encoded file in the work folder
    layouts: tuple[Layout, ...]  # output layouts it takes
    tools: tuple[str, ...]  # Tools field names it needs
    ffmpeg_encoder: str = ""  # an encoder the ffmpeg build must have
    # Default kb/s by output channels (the nearest count for others, the lower on a tie); None = no bitrate (lossless).
    bitrates: dict[int, int] | None = None
    bitrate_range: tuple[int, int] | None = None  # allowed kb/s (None = not checked here)
    bitrate_choices: tuple[int, ...] = ()  # only these, when set
    per_channel_max: int | None = None  # kb/s per channel
    vbr_default: bool = False  # no bitrate set = the encoder's quality VBR
    default_max: Layout | None = None  # the default layout is at most this (a downmix below it is chosen)
    delay_in_encode: bool = False  # it applies the source delay itself, so the mux must not
    options: tuple[EncodeOption, ...] = ()

    def resolve_options(self, given: dict[str, str]) -> tuple[dict[str, str], list[str]]:
        """Every option's value (the given one, else its default), and the problems with given ones.
        Keys this encode doesn't have are dropped (they belong to another encode)."""
        out, problems = {}, []
        for o in self.options:
            value = given.get(o.key, o.default).strip()
            problem = o.problem(value) if value != o.default else ""
            if problem:
                problems.append(problem)
                value = o.default
            out[o.key] = value
        return out, problems

    def default_bitrate(self, layout: Layout) -> int | None:
        if not self.bitrates or self.vbr_default:
            return None
        nearest = min(self.bitrates, key=lambda c: (abs(c - layout.channels), c))
        return self.bitrates[nearest]

    def bitrate_problem(self, kbps: int, layout: Layout) -> str:
        """Why this bitrate can't be used ("" when it can)."""
        if self.bitrates is None:
            return ""
        if self.bitrate_choices and kbps not in self.bitrate_choices:
            return f"{self.label} takes {', '.join(map(str, self.bitrate_choices))} kb/s"
        if self.bitrate_range and not self.bitrate_range[0] <= kbps <= self.bitrate_range[1]:
            return f"{self.label} takes {self.bitrate_range[0]} to {self.bitrate_range[1]} kb/s"
        if self.per_channel_max and kbps > self.per_channel_max * layout.channels:
            return f"{self.label} takes at most {self.per_channel_max} kb/s per channel"
        return ""


_DOLBY = _layouts("1.0", "2.0", "5.0", "5.1")
_ANY = _layouts("1.0", "2.0", "5.0", "5.1", "6.1", "7.1")
ENCODES: dict[AudioAction, AudioEncode] = {e.action: e for e in (
    AudioEncode(AudioAction.DDP, "DDP (DEE)", AudioCodec.EAC3, ".ec3", _layouts("1.0", "2.0", "5.1", "7.1"),
                ("deezy", "dee", "ffmpeg"), bitrates={1: 192, 2: 256, 6: 640, 8: 1024}, delay_in_encode=True),
    AudioEncode(AudioAction.ATMOS, "DDP Atmos (DEE)", AudioCodec.EAC3, ".ec3", _layouts("5.1"),
                ("deezy", "dee", "ffmpeg", "truehdd"), bitrates={6: 768}, delay_in_encode=True),
    AudioEncode(AudioAction.AAC, "AAC (qaac)", AudioCodec.AAC, ".m4a", _layouts("1.0", "2.0", "5.1"),
                ("ffmpeg", "qaac"), bitrates={1: 96, 2: 192, 6: 384}, bitrate_range=(8, 1280), vbr_default=True,
                default_max=Layout(2, 0)),
    AudioEncode(AudioAction.FLAC, "FLAC", AudioCodec.FLAC, ".flac", _ANY, ("ffmpeg",), ffmpeg_encoder="flac",
                options=(EncodeOption("level", "Compression level", "8", int_range=(0, 12),
                                      help="Higher is smaller and slower; every level is lossless"), _EXTRA)),
    AudioEncode(AudioAction.OPUS, "Opus", AudioCodec.OPUS, ".opus", _ANY, ("ffmpeg",), ffmpeg_encoder="libopus",
                bitrates={1: 96, 2: 160, 6: 384, 8: 512}, bitrate_range=(6, 2048), per_channel_max=256,
                options=(EncodeOption("vbr", "Bitrate mode", "on",
                                      choices=(("on", "Variable"), ("constrained", "Constrained variable"), ("off", "Constant"))),
                         EncodeOption("application", "Tuned for", "audio",
                                      choices=(("audio", "Music and film"), ("voip", "Speech"), ("lowdelay", "Low delay"))),
                         EncodeOption("complexity", "Complexity", "10", int_range=(0, 10), help="10 is the best quality"),
                         _EXTRA)),
    AudioEncode(AudioAction.AAC_FFMPEG, "AAC (ffmpeg)", AudioCodec.AAC, ".m4a", _ANY, ("ffmpeg",),
                ffmpeg_encoder="aac", bitrates={1: 96, 2: 192, 6: 384, 8: 512}, bitrate_range=(8, 1536),
                options=(EncodeOption("coder", "Coder", "twoloop", choices=(("twoloop", "Two-loop (better)"), ("fast", "Fast"))),
                         _EXTRA)),
    AudioEncode(AudioAction.AC3, "AC-3", AudioCodec.AC3, ".ac3", _DOLBY, ("ffmpeg",), ffmpeg_encoder="ac3",
                bitrates={1: 192, 2: 224, 6: 640}, bitrate_choices=AC3_BITRATES, options=(_DIALNORM, _EXTRA)),
    AudioEncode(AudioAction.EAC3, "E-AC-3 (ffmpeg)", AudioCodec.EAC3, ".eac3", _DOLBY, ("ffmpeg",),
                ffmpeg_encoder="eac3", bitrates={1: 192, 2: 256, 6: 640}, bitrate_range=(32, 6144),
                options=(_DIALNORM, _EXTRA)),
)}


def delay_in_encode(action: AudioAction) -> bool:
    """True when the encoder applies the source delay itself, so the mux must not."""
    enc = ENCODES.get(action)
    return enc is not None and enc.delay_in_encode


@dataclass(frozen=True, slots=True)
class AudioSettings:
    """Encoder knobs a profile sets once (per-track choices live on PlannedAudio)."""

    atmos_mode: str = "streaming"
    qaac_tvbr: int = 127
    deezy_extra_args: tuple[str, ...] = ()
    qaac_extra_args: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AudioCommand:
    """One encode. With two argvs, the first one's stdout is piped into the second."""

    planned: PlannedAudio
    output: Path
    argvs: tuple[tuple[str, ...], ...]


def output_path(planned: PlannedAudio, position: int, temp_dir: Path) -> Path:
    return temp_dir / f"audio{position}_{planned.language}{ENCODES[planned.action].suffix}"


def _deezy(planned: PlannedAudio, source: Path, output: Path, temp_dir: Path, settings: AudioSettings, tools: Tools) -> tuple[str, ...]:
    track = planned.source
    common = (
        f"--track-index={track.index}",
        f"--delay={track.delay_ms}ms",
        f"--bitrate={planned.bitrate_kbps}",
        "--output", str(output),
        "--temp-dir", str(temp_dir / "deezy"),
        "--overwrite",
        "--ffmpeg", tools.ffmpeg,
        "--dee", tools.dee,
        "--truehdd", tools.truehdd,
    )
    if planned.action is AudioAction.ATMOS:
        mode = ("encode", "atmos", f"--atmos-mode={settings.atmos_mode}")
    else:
        mode = ("encode", "ddp", f"--channels={planned.out_layout.channels}")
        if planned.upmix_50:
            mode += ("--upmix-50-to-51",)
    return (tools.deezy, *mode, *common, *settings.deezy_extra_args, str(source))


def _aac(planned: PlannedAudio, source: Path, output: Path, settings: AudioSettings, tools: Tools) -> tuple[tuple[str, ...], ...]:
    # Float WAV so a lossless 24-bit source isn't truncated and a downmix can't clip.
    ffmpeg = (
        tools.ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error",
        "-i", str(source),
        "-map", f"0:a:{planned.source.index}",
        "-ac", str(planned.out_layout.channels),
        "-c:a", "pcm_f32le", "-f", "wav", "-",
    )
    # --ignorelength: a piped WAV header has no real data size.
    # --no-delay: compensate encoder priming in the stream itself; MKV has no gapless metadata.
    # A bitrate means constrained VBR at about that rate; none means true VBR at the profile's quality.
    mode = ("--cvbr", str(planned.bitrate_kbps)) if planned.bitrate_kbps else ("--tvbr", str(settings.qaac_tvbr))
    qaac = (
        tools.qaac, *mode, "--ignorelength", "--no-delay", "--threading",
        *settings.qaac_extra_args, "-o", str(output), "-",
    )
    return ffmpeg, qaac


# ffmpeg's name for each layout (aformat sets it exactly: libopus refuses 5.1(side), and a
# downmix to a count alone could pick a layout the encoder doesn't take).
_FFMPEG_LAYOUT = {"1.0": "mono", "2.0": "stereo"}
def _opt(p: PlannedAudio, key: str) -> str:
    return p.options.get(key) or next(o.default for o in ENCODES[p.action].options if o.key == key)


_FFMPEG_ARGS = {
    AudioAction.FLAC: lambda p: ("-c:a", "flac", "-compression_level", _opt(p, "level"), "-f", "flac"),
    AudioAction.OPUS: lambda p: ("-c:a", "libopus", "-b:a", f"{p.bitrate_kbps}k", "-vbr", _opt(p, "vbr"),
                                 "-application", _opt(p, "application"), "-compression_level", _opt(p, "complexity"),
                                 "-f", "opus"),
    AudioAction.AAC_FFMPEG: lambda p: ("-c:a", "aac", "-b:a", f"{p.bitrate_kbps}k", "-aac_coder", _opt(p, "coder"),
                                       "-f", "mp4"),
    AudioAction.AC3: lambda p: ("-c:a", "ac3", "-b:a", f"{p.bitrate_kbps}k", "-dialnorm", _opt(p, "dialnorm"), "-f", "ac3"),
    AudioAction.EAC3: lambda p: ("-c:a", "eac3", "-b:a", f"{p.bitrate_kbps}k", "-dialnorm", _opt(p, "dialnorm"),
                                 "-f", "eac3"),
}


def _ffmpeg(planned: PlannedAudio, source: Path, output: Path, tools: Tools) -> tuple[str, ...]:
    layout = str(planned.out_layout)
    return (
        tools.ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
        "-i", str(source),
        "-map", f"0:a:{planned.source.index}", "-vn", "-sn", "-dn", "-map_chapters", "-1", "-map_metadata", "-1",
        "-af", f"aformat=channel_layouts={_FFMPEG_LAYOUT.get(layout, layout)}",
        *_FFMPEG_ARGS[planned.action](planned),
        *shlex.split(planned.options.get("extra", ""), posix=False), str(output),
    )


def audio_command(
    planned: PlannedAudio, position: int, source: Path, temp_dir: Path, settings: AudioSettings, tools: Tools
) -> AudioCommand | None:
    """The encode for one planned track, or None when it is copied from the source."""
    if planned.action is AudioAction.COPY:
        return None
    output = output_path(planned, position, temp_dir)
    if planned.action is AudioAction.AAC:
        argvs = _aac(planned, source, output, settings, tools)
    elif planned.action in _FFMPEG_ARGS:
        argvs = (_ffmpeg(planned, source, output, tools),)
    else:
        argvs = (_deezy(planned, source, output, temp_dir, settings, tools),)
    return AudioCommand(planned, output, argvs)
