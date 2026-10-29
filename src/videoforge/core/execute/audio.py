"""Audio encodes: what each one makes (ENCODES) and the command for a planned track.

DeeZy makes DDP and DDP Atmos, ffmpeg | qaac makes AAC, ffmpeg | opusenc makes Opus,
and ffmpeg's own encoders make FLAC, Opus, AAC, AC-3 and E-AC-3. ENCODES is the one list
the planner, the tool checks and the UI read: a new encode is an AudioAction, an entry
here and its command. Each encode's options are per-track settings; a profile's
AudioSettings can change some of their defaults (option_defaults).

Delay: the source's "delay relative to video" is applied exactly once. DeeZy
never reads it from the container (only from --delay or a "DELAY Xms" file name
token), so we pass it explicitly; DeeZy bakes it into the stream (padding or
trimming, plus DEE's own priming) and the output starts at 0. ffmpeg (alone or
into qaac or opusenc) starts at the first audio sample, so those get the delay at mux
(mkvmerge --sync).

Normalize (StaxRip's ffmpeg modes; DeeZy's DEE measures its own dialogue level): peak and loudnorm read the
track first (measure_argv, core/execute/loudness.py) and the encode applies what that found; dynaudnorm is one
pass. The measure runs the encode's own downmix first, so the level it reads is the output's.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
import sys

from videoforge.core.arguments import split_args
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
    num_range: tuple[float, float] | None = None  # a number (decimals too) in this range when set
    help: str = ""  # anything else is free text
    when: tuple[str, str] | None = None  # (key, value): used only while that option has that value

    @property
    def range(self) -> tuple[float, float] | None:
        return self.int_range or self.num_range

    def problem(self, value: str) -> str:
        """Why this value can't be used ("" when it can)."""
        if self.choices and value not in {v for v, _ in self.choices}:
            return f"{self.label} must be one of {', '.join(v for v, _ in self.choices)}"
        if self.int_range:
            lo, hi = self.int_range
            if not value.lstrip("-").isdigit() or not lo <= int(value) <= hi:
                return f"{self.label} must be a whole number from {lo} to {hi}"
        if self.num_range:
            lo, hi = self.num_range
            try:
                ok = lo <= float(value) <= hi  # False for nan
            except ValueError:
                ok = False
            if not ok:
                return f"{self.label} must be a number from {lo:g} to {hi:g}"
        if not self.choices and not self.range and value.count('"') % 2:
            return f"{self.label} has an unclosed quote"
        return ""


def _extra(tool: str, example: str) -> EncodeOption:
    return EncodeOption("extra", f"Extra {tool} arguments", "", help=f"Added to the {tool} command, e.g. {example}")


_EXTRA = _extra("ffmpeg", "-cutoff 20000")
_DRC = (
    ("", "DeeZy's default"),
    ("film_standard", "Film standard"),
    ("film_light", "Film light"),
    ("music_standard", "Music standard"),
    ("music_light", "Music light"),
    ("speech", "Speech"),
)
_DEEZY = (
    EncodeOption("drc_line", "DRC line mode", "", choices=_DRC, help="Dynamic range compression"),
    EncodeOption("drc_rf", "DRC RF mode", "", choices=_DRC, help="Dynamic range compression"),
    EncodeOption("dialnorm", "Dialogue level (dialnorm)", "0", int_range=(-31, 0), help="0 lets DEE measure it"),
)
_DIALNORM = EncodeOption(
    "dialnorm",
    "Dialogue level (dialnorm)",
    "-31",
    int_range=(-31, -1),
    help="-31 leaves the level alone; players turn quieter dialogue up",
)


_LOUDNORM = ("normalize", "loudnorm")
_NORMALIZE = (
    EncodeOption(
        "normalize",
        "Normalize",
        "",
        choices=(
            ("", "Off"),
            ("peak", "Peak to 0 dB (volumedetect)"),
            ("loudnorm", "Loudness, EBU R128 (loudnorm)"),
            ("dynaudnorm", "Dynamic (dynaudnorm)"),
        ),
        help="Peak and loudness read the whole track first",
    ),
    EncodeOption("loudnorm_i", "Target loudness (LUFS)", "-24", num_range=(-70, -5), when=_LOUDNORM),
    EncodeOption("loudnorm_tp", "Highest true peak (dBTP)", "-2", num_range=(-9, 0), when=_LOUDNORM),
    EncodeOption(
        "loudnorm_lra",
        "Loudness range (LU)",
        "7",
        num_range=(1, 50),
        help="A source with a wider range is compressed to fit",
        when=_LOUDNORM,
    ),
)


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
    channels_max: Mapping[int, int] | None = None  # the most kb/s for an output channel count
    vbr_default: bool = False  # no bitrate set = the encoder's quality VBR
    default_max: Layout | None = None  # the default layout is at most this (a downmix below it is chosen)
    delay_in_encode: bool = False  # it applies the source delay itself, so the mux must not
    options: tuple[EncodeOption, ...] = ()

    def configured(self, options: Mapping[str, str]) -> AudioEncode:
        """The layouts and defaults for the selected encoder mode."""
        if self.action is AudioAction.DDP and options.get("ddp_mode") == "bluray":
            return replace(self, layouts=_layouts("7.1"), bitrates={8: 1280}, channels_max=None)
        return self

    def resolve_options(
        self, given: dict[str, str], defaults: dict[str, str] | None = None
    ) -> tuple[dict[str, str], list[str]]:
        """Every option's value (the given one, else the profile's default, else the option's own),
        and the problems with given ones. Keys this encode doesn't have are dropped (another encode's)."""
        out, problems = {}, []
        for o in self.options:
            default = (defaults or {}).get(o.key, o.default)
            value = given.get(o.key, default).strip()
            problem = o.problem(value) if value != default else ""
            if problem:
                problems.append(problem)
                value = default
            out[o.key] = value
        return out, problems

    def default_layout(self, source: Layout) -> Layout:
        """The source's layout when this encode takes it (up to its default_max); else the biggest one it
        takes that is no bigger. DDP makes 5.1 from 5.0 (DeeZy adds the LFE)."""
        if self.upmix_50(source, Layout(5, 1)):
            return Layout(5, 1)
        cap = self.default_max.channels if self.default_max else source.channels
        fits = [lay for lay in self.layouts if lay.channels <= min(source.channels, cap)]
        if source in fits:
            return source
        return max(fits, key=lambda lay: (lay.channels, lay.lfe)) if fits else self.layouts[0]

    def upmix_50(self, source: Layout, layout: Layout) -> bool:
        """True for DDP's 5.1 from a 5.0 source, the one upmix allowed (DeeZy adds the LFE)."""
        return (
            self.action is AudioAction.DDP
            and source == Layout(5, 0)
            and layout == Layout(5, 1)
            and layout in self.layouts
        )

    def upmixes(self, source: Layout, layout: Layout) -> bool:
        """True when this layout needs channels the source doesn't have."""
        return layout.channels > source.channels and not self.upmix_50(source, layout)

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
        if self.channels_max and kbps > (most := self.channels_max.get(layout.channels, kbps)):
            return f"{self.label} takes at most {most} kb/s at {layout}"
        return ""


_DOLBY = _layouts("1.0", "2.0", "5.0", "5.1")
_ANY = _layouts("1.0", "2.0", "5.0", "5.1", "6.1", "7.1")
ENCODES: dict[AudioAction, AudioEncode] = {
    e.action: e
    for e in (
        AudioEncode(
            AudioAction.DDP,
            "DDP (DEE)",
            AudioCodec.EAC3,
            ".ec3",
            _layouts("1.0", "2.0", "5.1", "7.1"),
            ("deezy", "dee", "ffmpeg"),
            bitrates={1: 192, 2: 256, 6: 640, 8: 1024},
            # DEE's streaming DDP stops at 1024 for 7.1, and a higher bitrate comes out at that; Blu-ray goes higher
            channels_max={8: 1024},
            delay_in_encode=True,
            options=(
                EncodeOption(
                    "ddp_mode",
                    "DDP mode",
                    "standard",
                    choices=(("standard", "Standard"), ("bluray", "Blu-ray")),
                    help="Blu-ray requires 7.1 output; auto bitrate is 1280 kb/s",
                ),
                *_DEEZY,
                EncodeOption(
                    "stereo_downmix",
                    "Stereo downmix",
                    "",
                    choices=(
                        ("", "DeeZy's default"),
                        ("loro", "Lo/Ro"),
                        ("ltrt", "Lt/Rt"),
                        ("dpl2", "Dolby Pro Logic II"),
                    ),
                    help="Used when making 2.0 from more channels",
                ),
                _extra("DeeZy", "--metering-mode 1770_3"),
            ),
        ),
        AudioEncode(
            AudioAction.ATMOS,
            "DDP Atmos (DEE)",
            AudioCodec.EAC3,
            ".ec3",
            _layouts("5.1"),
            ("deezy", "dee", "ffmpeg", "truehdd"),
            bitrates={6: 768},
            delay_in_encode=True,
            options=(
                EncodeOption(
                    "atmos_mode", "Atmos mode", "streaming", choices=(("streaming", "Streaming"), ("bluray", "Blu-ray"))
                ),
                *_DEEZY,
                EncodeOption(
                    "warp",
                    "Warp mode",
                    "",
                    choices=(
                        ("", "DeeZy's default"),
                        ("normal", "Normal"),
                        ("warping", "Warping"),
                        ("prologiciix", "Pro Logic IIx"),
                        ("loro", "Lo/Ro"),
                    ),
                    help="Used when the TrueHD doesn't say",
                ),
                EncodeOption("bed_conform", "Bed conformance", "off", choices=(("off", "Off"), ("on", "On"))),
                _extra("DeeZy", "--metering-mode 1770_3"),
            ),
        ),
        AudioEncode(
            AudioAction.AAC,
            "AAC (qaac)",
            AudioCodec.AAC,
            ".m4a",
            _layouts("1.0", "2.0", "5.1"),
            ("ffmpeg", "qaac"),
            bitrates={1: 96, 2: 192, 6: 384},
            bitrate_range=(8, 1280),
            vbr_default=True,
            default_max=Layout(2, 0),
            options=(
                EncodeOption(
                    "quality",
                    "Quality (TVBR)",
                    "127",
                    int_range=(0, 127),
                    help="Used when no bitrate is set; 127 is the best",
                ),
                *_NORMALIZE,
                _extra("qaac", "--lowpass 20000"),
            ),
        ),
        AudioEncode(
            AudioAction.FLAC,
            "FLAC",
            AudioCodec.FLAC,
            ".flac",
            _ANY,
            ("ffmpeg",),
            ffmpeg_encoder="flac",
            options=(
                EncodeOption(
                    "level",
                    "Compression level",
                    "8",
                    int_range=(0, 12),
                    help="Higher is smaller and slower; every level is lossless",
                ),
                *_NORMALIZE,
                _EXTRA,
            ),
        ),
        AudioEncode(
            AudioAction.OPUS,
            "Opus (ffmpeg)",
            AudioCodec.OPUS,
            ".opus",
            _ANY,
            ("ffmpeg",),
            ffmpeg_encoder="libopus",
            bitrates={1: 96, 2: 160, 6: 384, 8: 512},
            bitrate_range=(6, 2048),
            per_channel_max=256,
            options=(
                EncodeOption(
                    "vbr",
                    "Bitrate mode",
                    "on",
                    choices=(("on", "Variable"), ("constrained", "Constrained variable"), ("off", "Constant")),
                ),
                EncodeOption(
                    "application",
                    "Tuned for",
                    "audio",
                    choices=(("audio", "Music and film"), ("voip", "Speech"), ("lowdelay", "Low delay")),
                ),
                EncodeOption("complexity", "Complexity", "10", int_range=(0, 10), help="10 is the best quality"),
                *_NORMALIZE,
                _EXTRA,
            ),
        ),
        AudioEncode(
            AudioAction.OPUSENC,
            "Opus (opusenc)",
            AudioCodec.OPUS,
            ".opus",
            _ANY,
            ("ffmpeg", "opusenc"),
            bitrates={1: 96, 2: 160, 6: 384, 8: 512},
            bitrate_range=(6, 2048),
            per_channel_max=256,
            options=(
                EncodeOption(
                    "mode",
                    "Bitrate mode",
                    "vbr",
                    choices=(("vbr", "Variable"), ("cvbr", "Constrained variable"), ("hard-cbr", "Constant")),
                ),
                EncodeOption(
                    "tune",
                    "Tuned for",
                    "",
                    choices=(("", "Automatic"), ("music", "Music"), ("speech", "Speech")),
                    help="Matters at low bitrates",
                ),
                EncodeOption("comp", "Complexity", "10", int_range=(0, 10), help="10 is the best quality"),
                *_NORMALIZE,
                _extra("opusenc", "--framesize 40"),
            ),
        ),
        AudioEncode(
            AudioAction.AAC_FFMPEG,
            "AAC (ffmpeg)",
            AudioCodec.AAC,
            ".m4a",
            _ANY,
            ("ffmpeg",),
            ffmpeg_encoder="aac",
            bitrates={1: 96, 2: 192, 6: 384, 8: 512},
            bitrate_range=(8, 1536),
            options=(
                EncodeOption("coder", "Coder", "twoloop", choices=(("twoloop", "Two-loop (better)"), ("fast", "Fast"))),
                *_NORMALIZE,
                _EXTRA,
            ),
        ),
        AudioEncode(
            AudioAction.AC3,
            "AC-3",
            AudioCodec.AC3,
            ".ac3",
            _DOLBY,
            ("ffmpeg",),
            ffmpeg_encoder="ac3",
            bitrates={1: 192, 2: 224, 6: 640},
            bitrate_choices=AC3_BITRATES,
            options=(_DIALNORM, *_NORMALIZE, _EXTRA),
        ),
        AudioEncode(
            AudioAction.EAC3,
            "E-AC-3 (ffmpeg)",
            AudioCodec.EAC3,
            ".eac3",
            _DOLBY,
            ("ffmpeg",),
            ffmpeg_encoder="eac3",
            bitrates={1: 192, 2: 256, 6: 640},
            bitrate_range=(32, 6144),
            options=(_DIALNORM, *_NORMALIZE, _EXTRA),
        ),
    )
}


def delay_in_encode(action: AudioAction) -> bool:
    """True when the encoder applies the source delay itself, so the mux must not."""
    enc = ENCODES.get(action)
    return enc is not None and enc.delay_in_encode


@dataclass(frozen=True, slots=True)
class AudioSettings:
    """Encoder knobs a profile sets once (per-track choices live on PlannedAudio)."""

    atmos_mode: str = "streaming"
    qaac_tvbr: int = 127
    deezy_extra_args: tuple[str, ...] = ()  # before each track's own extra arguments
    qaac_extra_args: tuple[str, ...] = ()
    dialnorm: int | None = None  # DeeZy's --custom-dialnorm (-31..-1) for DDP / Atmos; None: DEE measures it

    def option_defaults(self, action: AudioAction) -> dict[str, str]:
        """This profile's defaults for an encode's options (ENCODES[action].options keys)."""
        out: dict[str, str] = {}
        if self.dialnorm is not None and action in (AudioAction.DDP, AudioAction.ATMOS):
            out["dialnorm"] = str(self.dialnorm)
        if action is AudioAction.ATMOS:
            out["atmos_mode"] = self.atmos_mode
        if action is AudioAction.AAC:
            out["quality"] = str(self.qaac_tvbr)
        return out


@dataclass(frozen=True, slots=True)
class AudioCommand:
    """One encode. With two argvs, the first one's stdout is piped into the second."""

    planned: PlannedAudio
    output: Path
    argvs: tuple[tuple[str, ...], ...]


def output_path(planned: PlannedAudio, position: int, temp_dir: Path) -> Path:
    return temp_dir / f"audio{position}_{planned.language}{ENCODES[planned.action].suffix}"


def measure_path(planned: PlannedAudio, position: int, temp_dir: Path) -> Path:
    """What a track's measure step found (core/execute/loudness.py), beside its encode."""
    return output_path(planned, position, temp_dir).with_suffix(".loudness.json")


def _normalize(planned: PlannedAudio) -> str:
    """The track's normalize mode; "" for none, or an encode without the option (a copy, DeeZy's)."""
    enc = ENCODES.get(planned.action)
    return _opt(planned, "normalize") if enc and any(o.key == "normalize" for o in enc.options) else ""


def needs_measure(planned: PlannedAudio) -> bool:
    """True when the encode applies what a measure step reads first (peak and loudness normalizing)."""
    return _normalize(planned) in ("peak", "loudnorm")


def _chain(*filters: str) -> str:
    return ",".join(f for f in filters if f)


def _layout_filter(planned: PlannedAudio) -> str:
    layout = str(planned.out_layout)
    return f"aformat=channel_layouts={_FFMPEG_LAYOUT.get(layout, layout)}"


def _pre(planned: PlannedAudio) -> str:
    """The encode's own filter before normalizing: its output layout. qaac's comes from -ac, after any filter,
    so a normalized downmix makes it a filter (only a downmix: at the same count -ac keeps the source's layout)."""
    if planned.action is AudioAction.AAC and planned.out_layout.channels >= planned.source.layout.channels:
        return ""
    return _layout_filter(planned)


def _loudnorm(planned: PlannedAudio) -> str:
    return f"loudnorm=I={_opt(planned, 'loudnorm_i')}:TP={_opt(planned, 'loudnorm_tp')}:LRA={_opt(planned, 'loudnorm_lra')}"


# loudnorm's second-pass options, by the first pass's JSON keys
_MEASURED = {"input_i": "I", "input_tp": "TP", "input_lra": "LRA", "input_thresh": "thresh"}


def normalize_filter(planned: PlannedAudio, measured: Mapping[str, float] | None) -> str:
    """The encode's normalize filter ("" for none) from what its measure step found. Before that step has run
    (measured None), peak has no gain yet and loudnorm shows as one pass."""
    mode = _normalize(planned)
    if mode == "dynaudnorm":
        return "dynaudnorm"
    if mode == "peak":
        gain = -(measured or {}).get("max_volume", 0.0)
        return f"volume={gain:.1f}dB" if gain > 0 else ""
    if mode != "loudnorm":
        return ""
    # loudnorm resamples to 192 kHz when it can't stay linear (a source wider than the range, or a peak that
    # would pass the limit): back to the source's rate.
    rate = f"aresample={planned.source.sample_rate or 48000}"
    if measured is None:
        return _chain(_loudnorm(planned), rate)
    if any(key not in measured for key in (*_MEASURED, "target_offset")):
        return ""  # silence: no loudness to set
    values = ":".join(f"measured_{name}={measured[key]:.2f}" for key, name in _MEASURED.items())
    return _chain(f"{_loudnorm(planned)}:{values}:offset={measured['target_offset']:.2f}:linear=true", rate)


def measure_argv(planned: PlannedAudio, source: Path, out: Path, tools: Tools) -> tuple[str, ...]:
    """The measure step for normalize_filter: ffmpeg reads the track (after the encode's downmix) through
    core/execute/loudness.py, which writes what it found to out."""
    probe = "volumedetect" if _normalize(planned) == "peak" else f"{_loudnorm(planned)}:print_format=json"
    return (
        sys.executable,
        "-m",
        "videoforge.core.execute.loudness",
        str(out),
        str(planned.source.duration_ms or 0),
        tools.ffmpeg,
        "-hide_banner",
        "-nostdin",
        "-i",
        str(source),
        "-map",
        f"0:a:{planned.source.index}",
        "-vn",
        "-sn",
        "-dn",
        "-af",
        _chain(_pre(planned), probe),
        "-f",
        "null",
        "-",
    )


# DEE can't open a path past Windows' MAX_PATH (259), and DeeZy refuses a --temp-dir with no room left in it for
# its job folder (at most 44: a 29-character name, a track label, a run suffix) and a job file (56).
_DEEZY_TEMP_MAX = 259 - 56 - 44


def _deezy_temp(path: Path) -> tuple[str, ...]:
    """DeeZy's --temp-dir in the job's folder, or none when that is too deep (a long source name in a deep folder):
    DeeZy then uses a short folder of its own, unique to the run, and removes it after."""
    if sys.platform == "win32" and len(str(path.absolute())) > _DEEZY_TEMP_MAX:
        return ()
    return ("--temp-dir", str(path))


def _deezy(
    planned: PlannedAudio, source: Path, output: Path, temp_dir: Path, settings: AudioSettings, tools: Tools
) -> tuple[str, ...]:
    track = planned.source
    common = (
        f"--track-index={track.index}",
        f"--delay={track.delay_ms}ms",
        f"--bitrate={planned.bitrate_kbps}",
        "--output",
        str(output),
        *_deezy_temp(temp_dir / f"deezy.{output.stem}"),  # its own: audio encodes may run at the same time
        # logs and batch results; DeeZy's default is beside its exe, which may not be writable (/usr/local/bin)
        "--working-dir",
        str(temp_dir / "deezy-work"),
        "--overwrite",
        "--ffmpeg",
        tools.ffmpeg,
        "--dee",
        tools.dee,
        "--truehdd",
        tools.truehdd,
    )
    if planned.action is AudioAction.ATMOS:
        mode = ("encode", "atmos", f"--atmos-mode={_opt(planned, 'atmos_mode', settings)}")
    else:
        encoder = "ddp-bluray" if _opt(planned, "ddp_mode") == "bluray" else "ddp"
        mode = ("encode", encoder, f"--channels={planned.out_layout.channels}")
        if planned.upmix_50:
            mode += ("--upmix-50-to-51",)
    chosen = ()
    for key, flag in (
        ("drc_line", "--drc-line-mode"),
        ("drc_rf", "--drc-rf-mode"),
        ("stereo_downmix", "--stereo-down-mix"),
        ("warp", "--thd-warp-mode"),
    ):
        if value := _opt(planned, key):
            chosen += (f"{flag}={value}",)
    if (dialnorm := _opt(planned, "dialnorm", settings)) not in ("", "0"):
        chosen += (f"--custom-dialnorm={dialnorm}",)
    if _opt(planned, "bed_conform") == "on":
        chosen += ("--bed-conform",)
    return (tools.deezy, *mode, *common, *chosen, *settings.deezy_extra_args, *_extra_args(planned), str(source))


def _aac(
    planned: PlannedAudio,
    source: Path,
    output: Path,
    settings: AudioSettings,
    tools: Tools,
    measured: Mapping[str, float] | None,
) -> tuple[tuple[str, ...], ...]:
    # Float WAV so a lossless 24-bit source isn't truncated and a downmix can't clip.
    norm = normalize_filter(planned, measured)
    ffmpeg = (
        tools.ffmpeg,
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-i",
        str(source),
        "-map",
        f"0:a:{planned.source.index}",
        *(("-af", _chain(_pre(planned), norm)) if norm else ()),
        "-ac",
        str(planned.out_layout.channels),
        "-c:a",
        "pcm_f32le",
        "-f",
        "wav",
        "-",
    )
    # --ignorelength: a piped WAV header has no real data size.
    # --no-delay: compensate encoder priming in the stream itself; MKV has no gapless metadata.
    # A bitrate means constrained VBR at about that rate; none means true VBR at the profile's quality.
    mode = (
        ("--cvbr", str(planned.bitrate_kbps))
        if planned.bitrate_kbps
        else ("--tvbr", _opt(planned, "quality", settings))
    )
    qaac = (
        tools.qaac,
        *mode,
        "--ignorelength",
        "--no-delay",
        "--threading",
        *settings.qaac_extra_args,
        *_extra_args(planned),
        "-o",
        str(output),
        "-",
    )
    return ffmpeg, qaac


def _opusenc(
    planned: PlannedAudio, source: Path, output: Path, tools: Tools, measured: Mapping[str, float] | None
) -> tuple[tuple[str, ...], ...]:
    # Float WAV with the exact layout, so opusenc's channel mapping reads the right speakers.
    # No metadata and bitexact: opusenc warns about every LIST chunk ffmpeg would add.
    ffmpeg = (
        tools.ffmpeg,
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-i",
        str(source),
        "-map",
        f"0:a:{planned.source.index}",
        "-vn",
        "-sn",
        "-dn",
        "-map_metadata",
        "-1",
        "-fflags",
        "+bitexact",
        "-af",
        _chain(_pre(planned), normalize_filter(planned, measured)),
        "-c:a",
        "pcm_f32le",
        "-f",
        "wav",
        "-",
    )
    tune = _opt(planned, "tune")
    opusenc = (
        tools.opusenc,
        "--quiet",
        "--bitrate",
        str(planned.bitrate_kbps),
        f"--{_opt(planned, 'mode')}",
        *((f"--{tune}",) if tune else ()),
        "--comp",
        _opt(planned, "comp"),
        "--ignorelength",
        *_extra_args(planned),
        "-",
        str(output),
    )
    return ffmpeg, opusenc


# ffmpeg's name for each layout (aformat sets it exactly: libopus refuses 5.1(side), and a
# downmix to a count alone could pick a layout the encoder doesn't take).
_FFMPEG_LAYOUT = {"1.0": "mono", "2.0": "stereo"}


def _opt(p: PlannedAudio, key: str, settings: AudioSettings | None = None) -> str:
    """A track's option: its own value, else the profile's default, else the encode's ("" for a key it lacks)."""
    if value := p.options.get(key):
        return value
    if settings and (value := settings.option_defaults(p.action).get(key)):
        return value
    return next((o.default for o in ENCODES[p.action].options if o.key == key), "")


def _extra_args(p: PlannedAudio) -> list[str]:
    return split_args(p.options.get("extra", ""))


_FFMPEG_ARGS = {
    AudioAction.FLAC: lambda p: ("-c:a", "flac", "-compression_level", _opt(p, "level"), "-f", "flac"),
    AudioAction.OPUS: lambda p: (
        "-c:a",
        "libopus",
        "-b:a",
        f"{p.bitrate_kbps}k",
        "-vbr",
        _opt(p, "vbr"),
        "-application",
        _opt(p, "application"),
        "-compression_level",
        _opt(p, "complexity"),
        "-f",
        "opus",
    ),
    AudioAction.AAC_FFMPEG: lambda p: (
        "-c:a",
        "aac",
        "-b:a",
        f"{p.bitrate_kbps}k",
        "-aac_coder",
        _opt(p, "coder"),
        "-f",
        "mp4",
    ),
    AudioAction.AC3: lambda p: (
        "-c:a",
        "ac3",
        "-b:a",
        f"{p.bitrate_kbps}k",
        "-dialnorm",
        _opt(p, "dialnorm"),
        "-f",
        "ac3",
    ),
    AudioAction.EAC3: lambda p: (
        "-c:a",
        "eac3",
        "-b:a",
        f"{p.bitrate_kbps}k",
        "-dialnorm",
        _opt(p, "dialnorm"),
        "-f",
        "eac3",
    ),
}


def _ffmpeg(
    planned: PlannedAudio, source: Path, output: Path, tools: Tools, measured: Mapping[str, float] | None
) -> tuple[str, ...]:
    return (
        tools.ffmpeg,
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-map",
        f"0:a:{planned.source.index}",
        "-vn",
        "-sn",
        "-dn",
        "-map_chapters",
        "-1",
        "-map_metadata",
        "-1",
        "-af",
        _chain(_pre(planned), normalize_filter(planned, measured)),
        *_FFMPEG_ARGS[planned.action](planned),
        *_extra_args(planned),
        str(output),
    )


def audio_command(
    planned: PlannedAudio,
    position: int,
    source: Path,
    temp_dir: Path,
    settings: AudioSettings,
    tools: Tools,
    measured: Mapping[str, float] | None = None,
) -> AudioCommand | None:
    """The encode for one planned track, or None when it is copied from the source. measured: what its measure
    step found (needs_measure), once that has run."""
    if planned.action is AudioAction.COPY:
        return None
    output = output_path(planned, position, temp_dir)
    if planned.action is AudioAction.AAC:
        argvs = _aac(planned, source, output, settings, tools, measured)
    elif planned.action is AudioAction.OPUSENC:
        argvs = _opusenc(planned, source, output, tools, measured)
    elif planned.action in _FFMPEG_ARGS:
        argvs = (_ffmpeg(planned, source, output, tools, measured),)
    else:
        argvs = (_deezy(planned, source, output, temp_dir, settings, tools),)
    return AudioCommand(planned, output, argvs)
