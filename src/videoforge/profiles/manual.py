"""The built-in manual profile: no group rules, the output is what the user sets up.

Every source track (and every added subtitle file) goes into an MKV in source
order, copied unchanged with its language, title and flags. The user excludes,
reorders and edits tracks through the job's overrides, and can have an audio track
encoded (DDP, DDP Atmos or AAC) instead of copied. Only missing inputs and
impossible encodes block a job, and the finished file is checked against the plan
it was muxed from.
"""

from __future__ import annotations

from collections.abc import Sequence

from videoforge.core import lang
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


# Output layouts each encoder takes, and the bitrate a DDP encode gets when none is set.
ENCODE_LAYOUTS = {
    AudioAction.DDP: tuple(Layout.parse(x) for x in ("1.0", "2.0", "5.1", "7.1")),
    AudioAction.AAC: tuple(Layout.parse(x) for x in ("1.0", "2.0", "5.1")),
}
DDP_BITRATE = {1: 192, 2: 256, 6: 640, 8: 1024}  # by channels
ATMOS_BITRATE = 768


def _default_layout(action: AudioAction, source: Layout) -> Layout:
    """DDP keeps the channels (5.0 -> 5.1, more than 6 -> 7.1); AAC keeps mono/stereo, else stereo."""
    if source.channels <= 2:
        return Layout(2, 0) if source.channels == 2 else Layout(1, 0)
    if action is AudioAction.AAC:
        return Layout(2, 0)
    return Layout(7, 1) if source.channels > 6 else Layout(5, 1)


def audio_output(t: AudioTrack, ov: TrackOverride | None, issues: list[Issue]) -> dict:
    """PlannedAudio's action/format fields for a track: copied, or encoded as the override asks.
    Adds a BLOCK for an encode that can't be done (Atmos from a non-Atmos source, an upmix)."""
    action = (ov.action if ov else None) or AudioAction.COPY
    if action is AudioAction.COPY:
        return {"action": action, "out_codec": t.codec, "out_layout": t.layout, "out_atmos": t.atmos,
                "bitrate_kbps": None, "upmix_50": False}
    bitrate = ov.bitrate_kbps if ov else None
    if action is AudioAction.ATMOS:
        if not (t.atmos and t.codec is AudioCodec.TRUEHD):
            issues.append(Issue(Severity.BLOCK, "audio.atmos_source",
                                f"Audio #{t.id}: DDP Atmos needs a TrueHD Atmos source"))
        return {"action": action, "out_codec": AudioCodec.EAC3, "out_layout": Layout(5, 1), "out_atmos": True,
                "bitrate_kbps": bitrate or ATMOS_BITRATE, "upmix_50": False}
    layout = (ov.layout if ov else None) or _default_layout(action, t.layout)
    upmix_50 = action is AudioAction.DDP and t.layout == Layout(5, 0) and layout == Layout(5, 1)
    if layout not in ENCODE_LAYOUTS[action]:
        issues.append(Issue(Severity.BLOCK, "audio.layout", f"Audio #{t.id}: {action.value} can't be {layout}"))
    elif layout.channels > t.layout.channels and not upmix_50:
        issues.append(Issue(Severity.BLOCK, "audio.upmix", f"Audio #{t.id}: {t.layout} can't be upmixed to {layout}"))
    if action is AudioAction.DDP:
        bitrate = bitrate or DDP_BITRATE.get(layout.channels, 640)
    return {"action": action, "out_codec": AudioCodec.EAC3 if action is AudioAction.DDP else AudioCodec.AAC,
            "out_layout": layout, "out_atmos": False, "bitrate_kbps": bitrate, "upmix_50": upmix_50}


def _excluded(track: AudioTrack | SubTrack, overrides: Overrides) -> bool:
    ov = overrides.tracks.get(track_key(track))
    return bool(ov and ov.exclude)


class ManualProfile(Profile):
    id = "manual"
    name = "Manual"
    container = "mkv"
    external_subtitles = True
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
            audio_tracks = [by_id[i] for i in overrides.audio_track_ids if i in by_id]
        else:
            audio_tracks = ordered(source.audio, overrides.order)
        audio_tracks = [t for t in audio_tracks if not _excluded(t, overrides)]
        if source.audio and not audio_tracks:
            issues.append(Issue(Severity.WARN, "audio.none", "No audio tracks selected"))
        sub_tracks = [t for t in ordered(source.subs + probed.external_subs, overrides.order) if not _excluded(t, overrides)]

        audio: list[PlannedAudio] = []
        for t in audio_tracks:
            ov = overrides.tracks.get(track_key(t))
            language, title, flags = _settings(t, ov)
            audio.append(PlannedAudio(source=t, **audio_output(t, ov, issues), language=language, title=title, **flags))
        subs: list[PlannedSub] = []
        for t in sub_tracks:
            language, title, flags = _settings(t, overrides.tracks.get(track_key(t)))
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
