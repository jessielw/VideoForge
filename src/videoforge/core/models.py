"""Plain data models shared by probing, planning, execution and validation."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path


class Severity(StrEnum):
    INFO = "info"
    WARN = "warn"
    BLOCK = "block"


@dataclass(frozen=True, slots=True)
class Issue:
    severity: Severity
    code: str
    message: str

    def __str__(self) -> str:
        return f"[{self.severity}] {self.code}: {self.message}"


class AudioCodec(StrEnum):
    AAC = "aac"
    AC3 = "ac3"
    EAC3 = "eac3"
    TRUEHD = "truehd"
    DTS = "dts"
    DTS_HD_MA = "dts_hd_ma"
    DTS_HD_HRA = "dts_hd_hra"
    LPCM = "lpcm"
    FLAC = "flac"
    OPUS = "opus"
    OTHER = "other"

    @property
    def lossless(self) -> bool:
        return self in (AudioCodec.TRUEHD, AudioCodec.DTS_HD_MA, AudioCodec.LPCM, AudioCodec.FLAC)


class SubFormat(StrEnum):
    SRT = "srt"
    PGS = "pgs"
    ASS = "ass"
    VOBSUB = "vobsub"
    TX3G = "tx3g"  # MP4 timed text
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class Layout:
    """Channel layout as main (full-range) channels plus LFE channels."""

    main: int
    lfe: int = 0

    @property
    def channels(self) -> int:
        return self.main + self.lfe

    def __str__(self) -> str:
        return f"{self.main}.{self.lfe}"

    @classmethod
    def parse(cls, value: str) -> Layout:
        main, _, lfe = value.partition(".")
        return cls(int(main), int(lfe or 0))


@dataclass(slots=True)
class AudioTrack:
    id: int  # mkvmerge track id (container-wide, 0-based)
    index: int  # audio-relative index (ffmpeg a:N / DeeZy track index)
    codec: AudioCodec
    layout: Layout
    language: str  # IETF tag, e.g. "en", "ja"
    title: str = ""
    default: bool = False
    forced: bool = False
    hearing_impaired: bool = False
    commentary: bool = False
    original: bool = False  # in the content's original language
    visual_impaired: bool = False  # audio description: narration for the blind and partially sighted
    atmos: bool = False  # TrueHD Atmos or E-AC-3 JOC
    dtsx: bool = False
    bitrate_kbps: int | None = None
    delay_ms: int = 0  # relative to video
    format_name: str = ""  # raw MediaInfo format, for display
    external_path: Path | None = None  # an added audio file (id and index are then that file's)
    sample_rate: int | None = None  # Hz
    bit_depth: int | None = None  # lossless formats only (a lossy decoder's depth means nothing)
    size_bytes: int | None = None  # the stream's size, when the file says
    duration_ms: int | None = None
    copy: int = 0  # 1, 2, ...: another output track made from this same track (Overrides.copies)

    @property
    def is_external(self) -> bool:
        return self.external_path is not None

    @property
    def base_language(self) -> str:
        return self.language.split("-")[0]


@dataclass(slots=True)
class SubTrack:
    id: int  # mkvmerge track id; -1 for external files
    index: int  # subtitle-relative index
    format: SubFormat
    language: str  # IETF tag after normalization, e.g. "es-419", "zh-Hant", "en"
    title: str = ""
    default: bool = False
    forced: bool = False  # container forced flag
    hearing_impaired: bool = False  # container HI flag
    commentary: bool = False
    original: bool = False
    visual_impaired: bool = False
    element_count: int | None = None
    number: int | None = None  # MKV track number (mkvmerge id + 1, gMKVExtract "trackN")
    external_path: Path | None = None
    extracted_from: int | None = None  # source track number an external file was extracted from
    # Classification hints from the external filename ({stem}.en.forced.srt etc.)
    tags: frozenset[str] = frozenset()

    @property
    def base_language(self) -> str:
        lang = self.language.split("-")[0]
        return "zh" if lang == "yue" else lang

    @property
    def is_external(self) -> bool:
        return self.external_path is not None


@dataclass(slots=True)
class VideoInfo:
    width: int
    height: int
    start_ms: int = 0  # first video timestamp in the container
    default_duration_ns: int | None = None  # frame duration; timestamps a raw .h264/.hevc encode at mux


@dataclass(slots=True)
class SourceInfo:
    path: Path | None
    name: str  # file or release name, used for filename checks
    video: VideoInfo | None
    audio: list[AudioTrack] = field(default_factory=list)
    subs: list[SubTrack] = field(default_factory=list)
    has_chapters: bool = False


# --- Job inputs ---------------------------------------------------------------


class EncodeState(StrEnum):
    DONE = "done"
    IN_PROGRESS = "in_progress"
    UNKNOWN = "unknown"  # no StaxRip log; assumed done if the file isn't locked


@dataclass(slots=True)
class JobInputs:
    """Everything one output is built from: one source, its encode, external subtitles, chapters."""

    source: Path
    encode: Path | None = None
    subtitles: list[Path] = field(default_factory=list)
    chapters: Path | None = None
    encode_state: EncodeState = EncodeState.UNKNOWN
    audio: list[Path] = field(default_factory=list)  # added audio files; their tracks join the source's


# --- Plan -----------------------------------------------------------------------


class AudioAction(StrEnum):
    COPY = "copy"
    DDP = "ddp"  # DeeZy E-AC-3
    ATMOS = "atmos"  # DeeZy E-AC-3 JOC from TrueHD Atmos
    AAC = "aac"  # ffmpeg -> qaac TVBR
    # ffmpeg's own encoders (core.execute.audio.ENCODES has each one's layouts and bitrates)
    FLAC = "flac"
    OPUS = "opus"  # libopus
    OPUSENC = "opusenc"  # ffmpeg -> opusenc (opus-tools)
    AAC_FFMPEG = "aac_ffmpeg"
    AC3 = "ac3"
    EAC3 = "eac3"


@dataclass(slots=True)
class PlannedAudio:
    source: AudioTrack
    action: AudioAction
    out_codec: AudioCodec
    out_layout: Layout
    out_atmos: bool
    bitrate_kbps: int | None  # None for copies and AAC TVBR (an AAC bitrate means qaac CVBR)
    upmix_50: bool
    language: str
    title: str
    default: bool
    forced: bool = False
    hearing_impaired: bool = False
    commentary: bool = False
    original: bool = False
    visual_impaired: bool = False
    options: dict[str, str] = field(default_factory=dict)  # the encode's settings, defaults filled in


@dataclass(slots=True)
class PlannedSub:
    source: SubTrack
    slot: str  # the profile's category for this track (shown, and used for its ordering); "" for none
    language: str
    title: str
    default: bool = False
    forced: bool = False
    hearing_impaired: bool = False
    commentary: bool = False
    original: bool = False
    visual_impaired: bool = False


class TrackKind(StrEnum):
    AUDIO = "audio"
    SUB = "sub"


@dataclass(frozen=True, slots=True)
class TrackProperty:
    """A per-track on/off property a profile reads from the file and lets the user override."""

    key: str  # TrackOverride.flags key, e.g. "forced"
    label: str  # column/checkbox text, e.g. "Forced"
    kind: TrackKind
    help: str = ""


@dataclass(slots=True)
class TrackOverride:
    """Manual corrections for one track (None / a missing flag = keep the detected value)."""

    exclude: bool | None = None
    language: str | None = None
    title: str | None = None
    flags: dict[str, bool] = field(default_factory=dict)  # TrackProperty.key -> value
    # Audio, for profiles with a track editor: copy or encode it (None = the profile's choice),
    # the bitrate (None = the encoder's default / AAC's quality mode) and the output layout (None = the default).
    action: AudioAction | None = None
    bitrate_kbps: int | None = None
    layout: Layout | None = None
    options: dict[str, str] = field(default_factory=dict)  # the encode's own settings (execute.audio.EncodeOption keys)

    @property
    def empty(self) -> bool:
        return (self.exclude is None and self.language is None and self.title is None and not self.flags
                and self.action is None and self.bitrate_kbps is None and self.layout is None and not self.options)


@dataclass(slots=True)
class Overrides:
    original_language: str | None = None
    # Source audio track ids to use, in output order (replaces automatic selection).
    audio_track_ids: list[int] | None = None
    # Keyed by track_key(track): "id:<mkvmerge id>" or "ext:<file name>".
    tracks: dict[str, TrackOverride] = field(default_factory=dict)
    # Output order as track keys, for profiles that let the user reorder. Audio and
    # subtitles each keep their own order; unlisted tracks follow in source order.
    order: list[str] | None = None
    # More output tracks made from an audio track, as "<track key>+<n>" (e.g. "id:1+1"): the same
    # source track again, with its own encode, title and flags (StaxRip's extra audio profiles).
    copies: list[str] = field(default_factory=list)


class OtherAudio(StrEnum):
    """What a template does with the audio tracks past its slots."""

    KEEP = "keep"  # as the profile decides
    EXCLUDE = "exclude"  # left out


@dataclass(slots=True)
class AudioSlot:
    """A template's settings for one source audio track (by position), and more outputs made from it."""

    track: TrackOverride = field(default_factory=TrackOverride)
    extra: list[TrackOverride] = field(default_factory=list)  # like Overrides.copies, in order


@dataclass(slots=True)
class TemplateAudio:
    """A template's audio: slot n is for the source's nth audio track. Slots past the source's
    tracks are ignored; added audio files aren't counted (they keep their own settings)."""

    slots: list[AudioSlot] = field(default_factory=list)
    others: OtherAudio = OtherAudio.KEEP


def track_key(track: AudioTrack | SubTrack) -> str:
    """"id:<mkvmerge id>" for a source track, "ext:<file name>" for an added file (an added audio
    file's second track on is "ext:<file name>#<n>"); a copy of an audio track adds "+<n>"."""
    external = track.external_path
    copy = f"+{track.copy}" if isinstance(track, AudioTrack) and track.copy else ""
    if external is None:
        return f"id:{track.id}{copy}"
    more = f"#{track.index}" if isinstance(track, AudioTrack) and track.index else ""
    return f"ext:{external.name}{more}{copy}"


def copy_base(key: str) -> tuple[str, int]:
    """("id:1", 2) for the copy key "id:1+2"; (key, 0) for anything else."""
    base, _, n = key.rpartition("+")
    return (base, int(n)) if base and n.isdigit() and int(n) > 0 else (key, 0)


def with_copies(tracks: list[AudioTrack], copies: list[str]) -> list[AudioTrack]:
    """The tracks, then each copy (Overrides.copies) of one of them. A copy starts as its track
    without the default flag; copies of tracks that aren't there are skipped."""
    by_key = {track_key(t): t for t in tracks}
    out = list(tracks)
    for key in copies:
        base, n = copy_base(key)
        if n and base in by_key:
            out.append(replace(by_key[base], copy=n, default=False))
    return out


@dataclass(slots=True)
class Plan:
    source: SourceInfo
    encode_path: Path | None
    resolution: str  # the profile's size class (e.g. "1080p") or a plain size label ("1920x1080")
    original_language: str
    chapters_path: Path | None = None  # external chapters (StaxRip qpf); None = take the encode's/source's
    audio: list[PlannedAudio] = field(default_factory=list)
    subs: list[PlannedSub] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    overrides: Overrides = field(default_factory=Overrides)  # what produced this plan; kept for replanning
    profile: str = ""  # id of the profile whose rules made this plan (and whose checks validate it)
    inputs: JobInputs | None = None  # the files it was planned from; Load re-probes these and replans

    @property
    def dual_audio(self) -> bool:
        return len(self.audio) > 1

    @property
    def blocked(self) -> bool:
        return any(i.severity is Severity.BLOCK for i in self.issues)

    @property
    def status(self) -> Severity | None:
        if self.blocked:
            return Severity.BLOCK
        if any(i.severity is Severity.WARN for i in self.issues):
            return Severity.WARN
        return None
