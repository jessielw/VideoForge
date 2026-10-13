"""The built-in manual profile: no group rules, the output is what the user sets up.

Every source track (and every added subtitle file) goes into an MKV in source
order, copied unchanged with its language, title and flags. The user excludes,
reorders and edits tracks through the job's overrides, and can have an audio track
encoded instead of copied (any of core.execute.audio.ENCODES: DDP, DDP Atmos, AAC,
FLAC, Opus, AC-3, E-AC-3). Only missing inputs and
impossible encodes block a job, and the finished file is checked against the plan
it was muxed from.
"""

from __future__ import annotations

from collections.abc import Sequence

from videoforge.core import lang
from videoforge.core.execute.audio import ENCODES, AudioEncode
from videoforge.core.jobs import ProbedInputs
from videoforge.core.models import (
    AudioAction,
    AudioCodec,
    AudioTrack,
    Issue,
    Layout,
    Overrides,
    Plan,
    PlannedAudio,
    PlannedSub,
    Severity,
    SourceInfo,
    SubTrack,
    TrackKind,
    TrackOverride,
    TrackProperty,
    track_key,
)
from videoforge.core.profile import Profile
from videoforge.core.video.settings import Encoder, EncoderSettings, RateControl, VideoSettings

# Track flags the user can set; each key is a field of AudioTrack/SubTrack and of PlannedAudio/PlannedSub.
_FLAGS = (
    ("default", "Default", "Played when no track is chosen"),
    ("forced", "Forced", "Shown even when subtitles are off (foreign parts only)"),
    ("hearing_impaired", "SDH", "For the deaf and hard of hearing"),
    ("commentary", "Commentary", "Commentary track"),
    ("original", "Original", "In the content's original language"),
)
FLAG_KEYS = tuple(key for key, _, _ in _FLAGS)


def ordered[T: (AudioTrack, SubTrack)](tracks: Sequence[T], order: list[str] | None) -> list[T]:
    """Tracks listed in order (by track key) first, in that order; the rest after them in source order."""
    if not order:
        return list(tracks)
    rank = {key: i for i, key in enumerate(order)}
    return sorted(tracks, key=lambda t: rank.get(track_key(t), len(rank)))  # stable: source order breaks ties


def _settings(track: AudioTrack | SubTrack, ov: TrackOverride | None) -> tuple[str, str, dict[str, bool]]:
    """Language, title and flags after the user's override."""
    flags = {k: getattr(track, k) for k in FLAG_KEYS}
    if ov is None:
        return track.language, track.title, flags
    flags.update({k: v for k, v in ov.flags.items() if k in flags})
    language = lang.normalize(ov.language) if ov.language else track.language
    return language, track.title if ov.title is None else ov.title, flags


def _default_layout(enc: AudioEncode, source: Layout) -> Layout:
    """The source's layout when the encoder takes it (up to its default_max); else the biggest one it
    takes that is no bigger. DDP makes 5.1 from 5.0 (DeeZy adds the LFE)."""
    if enc.action is AudioAction.DDP and source == Layout(5, 0):
        return Layout(5, 1)
    cap = enc.default_max.channels if enc.default_max else source.channels
    fits = [lay for lay in enc.layouts if lay.channels <= min(source.channels, cap)]
    if source in fits:
        return source
    return max(fits, key=lambda lay: (lay.channels, lay.lfe)) if fits else enc.layouts[0]


def audio_output(t: AudioTrack, ov: TrackOverride | None, issues: list[Issue]) -> dict:
    """PlannedAudio's action/format fields for a track: copied, or encoded as the override asks.
    Adds a BLOCK for an encode that can't be done (Atmos from a non-Atmos source, an upmix)."""
    action = (ov.action if ov else None) or AudioAction.COPY
    if action is AudioAction.COPY:
        return {"action": action, "out_codec": t.codec, "out_layout": t.layout, "out_atmos": t.atmos,
                "bitrate_kbps": None, "upmix_50": False}
    enc = ENCODES[action]
    if action is AudioAction.ATMOS:
        if not (t.atmos and t.codec is AudioCodec.TRUEHD):
            issues.append(Issue(Severity.BLOCK, "audio.atmos_source",
                                f"Audio #{t.id}: DDP Atmos needs a TrueHD Atmos source"))
        layout = Layout(5, 1)
        return {"action": action, "out_codec": enc.codec, "out_layout": layout, "out_atmos": True,
                "bitrate_kbps": (ov.bitrate_kbps if ov else None) or enc.default_bitrate(layout), "upmix_50": False}
    layout = (ov.layout if ov else None) or _default_layout(enc, t.layout)
    upmix_50 = action is AudioAction.DDP and t.layout == Layout(5, 0) and layout == Layout(5, 1)
    if layout not in enc.layouts:
        issues.append(Issue(Severity.BLOCK, "audio.layout", f"Audio #{t.id}: {enc.label} can't be {layout}"))
    elif layout.channels > t.layout.channels and not upmix_50:
        issues.append(Issue(Severity.BLOCK, "audio.upmix", f"Audio #{t.id}: {t.layout} can't be upmixed to {layout}"))
    bitrate = None
    if enc.bitrates is not None:  # lossless encodes take none
        bitrate = (ov.bitrate_kbps if ov else None) or enc.default_bitrate(layout)
        problem = enc.bitrate_problem(bitrate, layout) if bitrate else ""
        if problem:
            issues.append(Issue(Severity.BLOCK, "audio.bitrate", f"Audio #{t.id}: {problem}"))
    options, problems = enc.resolve_options(ov.options if ov else {})
    issues += [Issue(Severity.BLOCK, "audio.option", f"Audio #{t.id}: {p}") for p in problems]
    return {"action": action, "out_codec": enc.codec, "out_layout": layout, "out_atmos": False,
            "bitrate_kbps": bitrate, "upmix_50": upmix_50, "options": options}


def _excluded(track: AudioTrack | SubTrack, overrides: Overrides) -> bool:
    ov = overrides.tracks.get(track_key(track))
    return bool(ov and ov.exclude)


class ManualProfile(Profile):
    id = "manual"
    name = "Manual"
    container = "mkv"
    external_subtitles = True
    external_audio = True
    track_editor = True
    track_properties =tuple(TrackProperty(key, label, kind, help) for kind in TrackKind for key, label, help in _FLAGS)

    def plan(self, probed: ProbedInputs, original_language: str | None, overrides: Overrides) -> Plan:
        source, encode = probed.source, probed.encode
        issues: list[Issue] = []
        if encode is None:
            issues.append(Issue(Severity.BLOCK, "input.no_video", "No video for this source: add an encode or encode it here"))
        if source.video and source.video.start_ms:
            issues.append(
                Issue(
                    Severity.WARN,
                    "sync.video_start",
                    f"Source video starts at {source.video.start_ms} ms; source tracks are shifted to match the encode",
                )
            )
        video = (encode.video if encode else None) or source.video

        if overrides.audio_track_ids is not None:
            by_id = {t.id: t for t in source.audio}
            audio_tracks = [by_id[i] for i in overrides.audio_track_ids if i in by_id] + probed.external_audio
        else:
            audio_tracks = ordered(source.audio + probed.external_audio, overrides.order)
        audio_tracks = [t for t in audio_tracks if not _excluded(t, overrides)]
        if source.audio and not audio_tracks:
            issues.append(Issue(Severity.WARN, "audio.none", "No audio tracks selected"))
        sub_tracks = [t for t in ordered(source.subs + probed.external_subs, overrides.order) if not _excluded(t, overrides)]

        audio: list[PlannedAudio] = []
        for t in audio_tracks:
            ov = overrides.tracks.get(track_key(t))
            language, title, flags = _settings(t, ov)
            if t.external_path is not None and language == "und":
                issues.append(Issue(Severity.WARN, "audio.language",
                                    f"{t.external_path.name} has no language: set it in the track editor"))
            audio.append(PlannedAudio(source=t, **audio_output(t, ov, issues), language=language, title=title, **flags))
        subs: list[PlannedSub] = []
        for t in sub_tracks:
            language, title, flags = _settings(t, overrides.tracks.get(track_key(t)))
            if t.external_path is not None and language == "und":
                issues.append(Issue(Severity.WARN, "subs.language",
                                    f"{t.external_path.name} has no language: set it in the track editor"))
            subs.append(PlannedSub(source=t, slot="", language=language, title=title, **flags))

        orig = overrides.original_language or original_language or (audio[0].language if audio else "und")
        return Plan(
            source=source,
            encode_path=encode.path if encode else None,
            resolution=f"{video.width}x{video.height}" if video else "",
            original_language=orig,
            chapters_path=probed.inputs.chapters,
            audio=audio,
            subs=subs,
            issues=issues,
            overrides=overrides,
            profile=self.id,
        )

    def video_defaults(self) -> tuple[VideoSettings, EncoderSettings]:
        return VideoSettings(), EncoderSettings(encoder=Encoder.X264, rate_control=RateControl.CRF, crf=18.0, preset="slow")

    def validate_output(self, plan: Plan, output: SourceInfo) -> list[Issue]:
        return output_matches_plan(plan, output)

    def detected_flags(self, track: AudioTrack | SubTrack) -> dict[str, bool]:
        return {k: getattr(track, k) for k in FLAG_KEYS}


def _describe(language: str, title: str, flags: dict[str, bool]) -> str:
    on = [k for k in FLAG_KEYS if flags.get(k)]
    return f"{language} '{title}'" + (f" [{', '.join(on)}]" if on else "")


def output_matches_plan(plan: Plan, output: SourceInfo) -> list[Issue]:
    """BLOCK where the muxed file's tracks (count, order, language, title, flags, format) differ from the plan."""
    issues: list[Issue] = []

    def compare(code: str, label: str, wanted: list, found: list, same_format) -> None:
        if len(found) != len(wanted):
            issues.append(
                Issue(Severity.BLOCK, f"plan.{code}_count", f"Expected {len(wanted)} {label} track(s), found {len(found)}")
            )
        for i, (want, got) in enumerate(zip(wanted, found), 1):
            w = (lang.normalize(want.language), want.title, {k: getattr(want, k) for k in FLAG_KEYS})
            g = (lang.normalize(got.language), got.title, {k: getattr(got, k) for k in FLAG_KEYS})
            if w != g:
                issues.append(
                    Issue(Severity.BLOCK, f"plan.{code}", f"{label} {i}: expected {_describe(*w)}, found {_describe(*g)}")
                )
            if not same_format(want, got):
                issues.append(Issue(Severity.BLOCK, f"plan.{code}_format", f"{label} {i} is not in the planned format"))

    compare(
        "audio", "Audio", plan.audio, output.audio,
        lambda want, got: (got.codec, got.layout) == (want.out_codec, want.out_layout),
    )
    compare("subs", "Subtitle", plan.subs, output.subs, lambda want, got: got.format is want.source.format)
    return issues
