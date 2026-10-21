"""Plain data models shared by probing, planning, execution and validation."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from fractions import Fraction
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
    number: int | None = None  # the container's track number: the MKV track number, the MP4 track ID, the TS PID
    core: bool = False  # a Blu-ray TrueHD's AC-3 core: mkvmerge splits it out of the TrueHD's PID

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
    size_bytes: int | None = None  # the stream's size, when the file says
    number: int | None = None  # the container's track number (MKV: mkvmerge id + 1, gMKVExtract "trackN")
    external_path: Path | None = None
    extracted_from: int | None = None  # source track number an external file was extracted from
    delay_ms: int = 0  # its start's offset to the video's, outside Matroska (ffprobe's): an MP4's, for the mux
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
class VideoColor:
    """The source video's colour description, in x264 / x265's names ("" / 0 / None: the source doesn't say).
    Read by probe (core/video/color.py); the encode is tagged with it."""

    primaries: str = ""  # --colorprim: bt709, bt2020, smpte432, ...
    transfer: str = ""  # --transfer: bt709, smpte2084 (PQ), arib-std-b67 (HLG), ...
    matrix: str = ""  # --colormatrix: bt709, bt2020nc, smpte170m, ...
    range: str = ""  # limited or full
    chroma_loc: int | None = None  # --chromaloc 0-5
    master_display: str = ""  # HDR10 mastering display, x265's G(x,y)B(x,y)R(x,y)WP(x,y)L(max,min)
    max_cll: int = 0  # HDR10 content light levels, cd/m2
    max_fall: int = 0


@dataclass(slots=True)
class VideoHdr:
    """The source video's dynamic HDR metadata, beyond HDR10 (MediaInfo; core/video/hdr.py). 0 / "": none."""

    dv_profile: int = 0  # Dolby Vision profile: 5, 7, 8
    dv_compat: int | None = None  # its base layer's compatibility id: 7.6 -> 6, 8.1 -> 1, 8.4 -> 4
    dv_level: int = 0
    dv_layers: str = ""  # "BL+EL+RPU", "BL+RPU"
    dv_el: str = ""  # a profile 7 enhancement layer: "FEL" or "MEL" (from the RPU); "" = none, or not read
    hdr10plus: bool = False  # SMPTE ST 2094-40 dynamic metadata (SEI in the stream)

    @property
    def dv_name(self) -> str:
        """ "7.6 FEL", "8.1", "5"; "" without Dolby Vision."""
        if not self.dv_profile:
            return ""
        name = f"{self.dv_profile}" + (f".{self.dv_compat}" if self.dv_compat is not None else "")
        return f"{name} {self.dv_el}" if self.dv_el else name


@dataclass(slots=True)
class VideoInfo:
    width: int
    height: int
    start_ms: int = 0  # first video timestamp in the container
    default_duration_ns: int | None = None  # frame duration; timestamps a raw .h264/.hevc encode at mux
    frames: int = 0  # frame count (MediaInfo); 0 = not known
    language: str = "und"  # the source's video language, written on the encode at mux
    # The pixel aspect ratio (a pixel's width / height): not 1:1 on an anamorphic source (DVD, some HDTV).
    sar_num: int = 1
    sar_den: int = 1
    color: VideoColor = field(default_factory=VideoColor)
    hdr: VideoHdr = field(default_factory=VideoHdr)
    id: int = 0  # mkvmerge's track id (mkvextract's too)
    # A variable frame rate (MediaInfo's FrameRate_Mode): default_duration_ns is then only the first frame's,
    # and the encode is timed by the source's own timestamps (core/video/vfr.py).
    vfr: bool = False
    duration_ms: int = 0  # the video's length (MediaInfo); 0 = not known
    # MediaInfo's ScanType (Progressive, Interlaced, MBAFF, PAFF) and ScanOrder (TFF, BFF, 2:3 Pulldown, ...),
    # as StaxRip shows them; "" = not read (a job probed before they were).
    scan_type: str = ""
    scan_order: str = ""

    @property
    def interlaced(self) -> bool:
        """Stored as fields: the picture combs unless the script deinterlaces or field-matches it."""
        return self.scan_type in ("Interlaced", "MBAFF", "PAFF")

    @property
    def sar(self) -> Fraction:
        return Fraction(self.sar_num, self.sar_den) if self.sar_num > 0 and self.sar_den > 0 else Fraction(1)


@dataclass(slots=True)
class SourceInfo:
    path: Path | None
    name: str  # file or release name, used for filename checks
    video: VideoInfo | None
    audio: list[AudioTrack] = field(default_factory=list)
    subs: list[SubTrack] = field(default_factory=list)
    has_chapters: bool = False
    attachments_bytes: int = 0  # the attachments' size (an ASS subtitle's fonts)
    container: str = ""  # mkvmerge's container type ("Matroska", "MP4/QuickTime", ...); "" in older probes (MKV)


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
    # Subtitles: burned into the video instead of muxed (core.video.burn; one per job).
    burn: bool | None = None

    @property
    def empty(self) -> bool:
        return (
            self.exclude is None
            and self.burn is None
            and self.language is None
            and self.title is None
            and not self.flags
            and self.action is None
            and self.bitrate_kbps is None
            and self.layout is None
            and not self.options
        )


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


class OtherTracks(StrEnum):
    """What a template does with the tracks it doesn't set: audio past its slots, subtitles no rule matches."""

    KEEP = "keep"  # as the profile decides
    EXCLUDE = "exclude"  # left out


@dataclass(slots=True)
class AudioSlot:
    """A template's settings for one source audio track (by position), and more outputs made from it."""

    track: TrackOverride = field(default_factory=TrackOverride)
    extra: list[TrackOverride] = field(default_factory=list)  # like Overrides.copies, in order


@dataclass(slots=True)
class AudioRule:
    """One rule of a template's audio (by rules): the source tracks it matches (an empty list or None
    = any) and what they get, as a slot gives. A track counts as commentary / audio description by its
    flag or its title (template.audio_traits). first_only: only the first matching track (source order)
    takes the rule; the others go on to the next rules."""

    languages: list[str] = field(default_factory=list)  # "en" matches en-US too; "es-419" only itself
    original: bool | None = None  # in the job's original language (or not)
    codecs: list[AudioCodec] = field(default_factory=list)
    min_channels: int | None = None  # compared with the track's channel count (5.1 = 6)
    max_channels: int | None = None
    commentary: bool | None = None
    visual_impaired: bool | None = None
    first_only: bool = False
    track: TrackOverride = field(default_factory=TrackOverride)  # exclude = leave out
    extra: list[TrackOverride] = field(default_factory=list)  # more outputs from each matched track


class AudioMatch(StrEnum):
    POSITION = "position"  # slot n is for the source's nth audio track
    RULES = "rules"  # each track takes the first rule it matches


@dataclass(slots=True)
class TemplateAudio:
    """A template's audio, for the source's audio tracks (added audio files keep their own settings).
    By position: slot n is for the source's nth audio track; slots past the source's tracks are
    ignored. By rules: each track takes the first rule it matches. `others`: the tracks past the slots,
    or no rule matches (the Templates page sets it to leave out for rules)."""

    mode: AudioMatch = AudioMatch.POSITION
    slots: list[AudioSlot] = field(default_factory=list)
    rules: list[AudioRule] = field(default_factory=list)
    others: OtherTracks = OtherTracks.KEEP


@dataclass(slots=True)
class SubRule:
    """One rule of a template's subtitles: the tracks it matches (an empty list or None = any) and what
    they get. A track counts as forced / SDH / commentary by its flag or its title (template.sub_traits)."""

    languages: list[str] = field(default_factory=list)  # "en" matches en-US too; "es-419" only itself
    formats: list[SubFormat] = field(default_factory=list)
    forced: bool | None = None
    hearing_impaired: bool | None = None
    commentary: bool | None = None
    track: TrackOverride = field(default_factory=TrackOverride)  # exclude = leave out; title and flags


@dataclass(slots=True)
class TemplateSubs:
    """A template's subtitles: each track (source tracks and added files) takes the first rule it
    matches; the output lists them in rule order, then the kept ones no rule matched."""

    rules: list[SubRule] = field(default_factory=list)
    others: OtherTracks = OtherTracks.EXCLUDE


@dataclass(slots=True)
class TemplateChoice:
    """What a template set for one kind of track once the job's tracks were known: each track it
    decided (an empty override: as the profile has it), the copies it made and its output order for
    them (None: source order). The track editor tells these from hand edits and can go back to them."""

    tracks: dict[str, TrackOverride] = field(default_factory=dict)
    copies: list[str] = field(default_factory=list)
    order: list[str] | None = None


def track_key(track: AudioTrack | SubTrack) -> str:
    """ "id:<mkvmerge id>" for a source track, "ext:<file name>" for an added file (an added audio
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
    burn: SubTrack | None = None  # the subtitle track burned into the video (core.video.burn), not muxed
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
