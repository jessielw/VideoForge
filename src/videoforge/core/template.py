"""Templates: settings for a job's whole run (video, encoder, audio, container, chapters), the way
StaxRip's templates hold a project's settings. Applied when jobs are added, or to a batch.

The crop is per source, so a template says what to do with it instead (CropMode). Its audio is by
position (TemplateAudio.slots: settings for the source's 1st, 2nd, ... audio track) or by rules
(TemplateAudio.rules: each track takes the first rule matching its language, codec, channels and
traits), and becomes the job's track overrides once the source's tracks are known (apply_audio),
each made to fit its track (fit_audio), so one template suits a season's 5.1 and stereo episodes
and, with rules, a season whose track order shifts. Its subtitles are rules
(TemplateSubs): each track, added files too, takes the first rule matching its language, format and
traits (apply_subs), so "forced English first and default, then full English, nothing else" fits
every episode whatever its track list.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from enum import StrEnum
import re

from videoforge.core import lang
from videoforge.core.execute.audio import ENCODES
from videoforge.core.execute.mux import MuxSettings
from videoforge.core.job import JobSpec
from videoforge.core.models import (
    AudioAction,
    AudioCodec,
    AudioMatch,
    AudioRule,
    AudioTrack,
    OtherTracks,
    Overrides,
    SubRule,
    SubTrack,
    TemplateAudio,
    TemplateChoice,
    TemplateSubs,
    TrackOverride,
    copy_base,
    track_key,
)
from videoforge.core.profile import Profile
from videoforge.core.video.settings import EncoderSettings, VideoSettings


class CropMode(StrEnum):
    KEEP = "keep"  # each job's own crop
    FIXED = "fixed"  # the template's crop (video.crop) on every job
    AUTO = "auto"  # detect each job's crop once its source can be read


@dataclass(slots=True)
class Template:
    video: VideoSettings = field(default_factory=VideoSettings)
    encoder: EncoderSettings = field(default_factory=EncoderSettings)
    mux: MuxSettings = field(default_factory=MuxSettings)
    qpf: bool = True
    crop_mode: CropMode = CropMode.KEEP
    audio: TemplateAudio | None = None  # None: the template leaves each job's audio alone
    subs: TemplateSubs | None = None  # None: ... and its subtitles

    @classmethod
    def defaults(cls, profile: Profile) -> Template:
        """A profile's own settings for a new job, as a template."""
        video, encoder = profile.video_defaults()
        return cls(video, encoder)

    def apply(self, spec: JobSpec) -> None:
        """Set the job's settings from the template. A job reusing an encode has nothing to crop."""
        crop = self.video.crop if self.crop_mode is CropMode.FIXED else spec.video.crop
        spec.video = replace(copy.deepcopy(self.video), crop=copy.copy(crop))
        spec.encoder = copy.deepcopy(self.encoder)
        spec.mux = copy.copy(self.mux)
        spec.qpf = self.qpf
        spec.autocrop = self.crop_mode is CropMode.AUTO and spec.encodes_video
        if self.audio is not None:
            spec.audio_template = copy.deepcopy(self.audio)
        if self.subs is not None:
            spec.subs_template = copy.deepcopy(self.subs)


def apply_audio(
    overrides: Overrides, audio: TemplateAudio, source_audio: list[AudioTrack], original_language: str | None = None
) -> Overrides:
    """The job's overrides with its source audio set from the template, by position or by rules: the
    earlier choices for those tracks (settings, copies, order) are replaced. Each output is fitted to
    its track (fit_audio). Added audio files and subtitles keep theirs. original_language is the job's
    (rules can ask for it)."""
    if audio.mode is AudioMatch.RULES:
        return apply_audio_rules(overrides, audio, source_audio, original_language)
    return apply_audio_slots(overrides, audio, source_audio)


def apply_audio_slots(overrides: Overrides, audio: TemplateAudio, source_audio: list[AudioTrack]) -> Overrides:
    """By position: slot n goes to the nth track, extra slots are ignored; tracks past the slots are
    kept as they are or left out."""
    keys = [track_key(t) for t in source_audio]
    ours = set(keys)
    copies = [c for c in overrides.copies if copy_base(c)[0] not in ours]
    tracks = {k: v for k, v in overrides.tracks.items() if copy_base(k)[0] not in ours}
    for i, (key, track) in enumerate(zip(keys, source_audio, strict=True)):
        if i < len(audio.slots):
            slot = audio.slots[i]
            if not slot.track.empty:
                tracks[key] = fit_audio(slot.track, track)
            for n, extra in enumerate(slot.extra, 1):
                copies.append(f"{key}+{n}")
                tracks[f"{key}+{n}"] = fit_audio(extra, track)
        elif audio.others is OtherTracks.EXCLUDE:
            tracks[key] = TrackOverride(exclude=True)
    order = [k for k in overrides.order if copy_base(k)[0] not in ours] if overrides.order else None
    return replace(overrides, tracks=tracks, copies=copies, order=order or None, audio_track_ids=None)


def fit_audio(ov: TrackOverride, track: AudioTrack) -> TrackOverride:
    """A template's track settings for one source track: a copy without a language (that's per source),
    with what the track can't give made the best that fits: DDP Atmos from a track without Atmos is
    plain DDP, a layout with more channels than the track is the encode's default for it, and a
    bitrate goes with the layout it was set for (back to the default when the layout changes, or when
    the encode won't take it). The same settings set by hand in the track editor still block."""
    out = copy.deepcopy(ov)
    out.language = None
    if out.action is AudioAction.ATMOS and not (track.atmos and track.codec is AudioCodec.TRUEHD):
        out.action, out.layout, out.bitrate_kbps = AudioAction.DDP, None, None
    enc = ENCODES.get(out.action) if out.action else None
    if enc is None:  # copied
        return out
    if out.layout and (out.layout not in enc.layouts or enc.upmixes(track.layout, out.layout)):
        out.layout, out.bitrate_kbps = None, None
    if out.bitrate_kbps and enc.bitrate_problem(out.bitrate_kbps, out.layout or enc.default_layout(track.layout)):
        out.bitrate_kbps = None
    return out


_FORCED_RE = re.compile(r"(?i)\b(forced|foreign)\b")
_SDH_RE = re.compile(r"(?i)\b(sdh|cc)\b|hearing.impaired")
_COMMENTARY_RE = re.compile(r"(?i)\bcommentary\b")


def sub_traits(track: SubTrack) -> dict[str, bool]:
    """Forced / SDH / commentary as a template's rules see them: the track's flag, or its title saying so
    ("English (Forced)", "English SDH"). An added file's name tags already set its flags."""
    return {
        "forced": track.forced or bool(_FORCED_RE.search(track.title)),
        "hearing_impaired": track.hearing_impaired or bool(_SDH_RE.search(track.title)),
        "commentary": track.commentary or bool(_COMMENTARY_RE.search(track.title)),
    }


def language_matches(language: str, wanted: str) -> bool:
    """A rule's language ("en", "eng", "English") against a track's: a base language matches its
    regions too (en matches en-US), a region only itself (es-419)."""
    w = lang.from_mediainfo_name(wanted.strip())
    return language == w if "-" in w else lang.base_of(language) == lang.base_of(w)


def sub_matches(rule: SubRule, track: SubTrack) -> bool:
    wanted = [x for x in rule.languages if x.strip()]
    if wanted and not any(language_matches(track.language, w) for w in wanted):
        return False
    if rule.formats and track.format not in rule.formats:
        return False
    traits = sub_traits(track)
    return all(
        want is None or traits[key] == want
        for key, want in (
            ("forced", rule.forced),
            ("hearing_impaired", rule.hearing_impaired),
            ("commentary", rule.commentary),
        )
    )


def apply_subs(overrides: Overrides, subs: TemplateSubs, tracks: list[SubTrack]) -> Overrides:
    """The job's overrides with its subtitles (source tracks, then added files) set from the template's
    rules: the earlier choices for them (settings, order) are replaced. Each track takes its first
    matching rule's settings (no language: that's per source); one no rule matches is kept or left
    out (subs.others). Kept tracks are ordered by rule, then source order. One default at most: when
    a rule sets it, the first kept track to get it keeps it and every other subtitle has it off."""
    keys = [track_key(t) for t in tracks]
    ours = set(keys)
    out = {k: v for k, v in overrides.tracks.items() if k not in ours}
    ranked: list[tuple[int, int, str]] = []  # (rule, source position, key) of the kept tracks
    for pos, (key, track) in enumerate(zip(keys, tracks, strict=True)):
        rule = next((i for i, r in enumerate(subs.rules) if sub_matches(r, track)), None)
        if rule is None:
            if subs.others is OtherTracks.EXCLUDE:
                out[key] = TrackOverride(exclude=True)
            else:
                ranked.append((len(subs.rules), pos, key))
            continue
        ov = replace(copy.deepcopy(subs.rules[rule].track), language=None)
        if not ov.empty:
            out[key] = ov
        if not ov.exclude:
            ranked.append((rule, pos, key))
    kept = [key for _, _, key in sorted(ranked)]
    if any(key in out and out[key].flags.get("default") for key in kept):
        first = next(key for key in kept if key in out and out[key].flags.get("default"))
        for key in kept:
            if key != first:
                ov = out.setdefault(key, TrackOverride())
                ov.flags = {**ov.flags, "default": False}
    order = [k for k in overrides.order or [] if k not in ours] + kept
    return replace(overrides, tracks=out, order=order or None)


_AD_RE = re.compile(r"(?i)audio.description|\bdescri(ptive|bed)\b")
_AD_SHORT_RE = re.compile(r"\bAD\b")  # case-sensitive: "AD", not "ad" in a word or a name


def audio_traits(track: AudioTrack) -> dict[str, bool]:
    """Commentary / audio description as a template's rules see them: the track's flag, or its title
    saying so ("Director's Commentary", "English AD", "Descriptive Audio")."""
    described = bool(_AD_RE.search(track.title) or _AD_SHORT_RE.search(track.title))
    return {
        "commentary": track.commentary or bool(_COMMENTARY_RE.search(track.title)),
        "visual_impaired": track.visual_impaired or described,
    }


def audio_matches(rule: AudioRule, track: AudioTrack, original_language: str | None = None) -> bool:
    wanted = [x for x in rule.languages if x.strip()]
    if wanted and not any(language_matches(track.language, w) for w in wanted):
        return False
    if rule.original is not None:  # an unknown language is never the original
        known = original_language not in (None, "", "und") and track.language != "und"
        if (known and language_matches(track.language, original_language or "")) != rule.original:
            return False
    if rule.codecs and track.codec not in rule.codecs:
        return False
    channels = track.layout.channels
    if (rule.min_channels and channels < rule.min_channels) or (rule.max_channels and channels > rule.max_channels):
        return False
    traits = audio_traits(track)
    return all(
        want is None or traits[key] == want
        for key, want in (("commentary", rule.commentary), ("visual_impaired", rule.visual_impaired))
    )


def apply_audio_rules(
    overrides: Overrides, audio: TemplateAudio, source_audio: list[AudioTrack], original_language: str | None
) -> Overrides:
    """By rules: each track (source order) takes the first rule it matches, skipping a first_only rule
    an earlier track took, and gets its settings and more outputs (each fitted to it); one no rule
    matches is kept as it is or left out (audio.others). Kept tracks are ordered by rule, then source
    order, each followed by its more outputs; unmatched kept ones last. One default at most: when a
    rule sets it, the first kept output to get it keeps it and every other one has it off."""
    keys = [track_key(t) for t in source_audio]
    ours = set(keys)
    copies = [c for c in overrides.copies if copy_base(c)[0] not in ours]
    out = {k: v for k, v in overrides.tracks.items() if copy_base(k)[0] not in ours}
    taken: set[int] = set()  # the rules a track took
    ranked: list[tuple[int, int, list[str]]] = []  # (rule, source position, its output keys) of the kept tracks
    for pos, (key, track) in enumerate(zip(keys, source_audio, strict=True)):
        rule = next(
            (
                i
                for i, r in enumerate(audio.rules)
                if not (r.first_only and i in taken) and audio_matches(r, track, original_language)
            ),
            None,
        )
        if rule is None:
            if audio.others is OtherTracks.EXCLUDE:
                out[key] = TrackOverride(exclude=True)
            else:
                ranked.append((len(audio.rules), pos, [key]))
            continue
        taken.add(rule)
        r = audio.rules[rule]
        ov = fit_audio(r.track, track)
        if not ov.empty:
            out[key] = ov
        if ov.exclude:
            continue
        made = [key]
        for n, extra in enumerate(r.extra, 1):
            made.append(f"{key}+{n}")
            out[made[-1]] = fit_audio(extra, track)
        copies += made[1:]
        ranked.append((rule, pos, made))
    kept = [key for _, _, made in sorted(ranked) for key in made]
    first = next((key for key in kept if key in out and out[key].flags.get("default")), None)
    if first is not None:
        for key in kept:
            if key != first:
                ov = out.setdefault(key, TrackOverride())
                ov.flags = {**ov.flags, "default": False}
    order = [k for k in overrides.order or [] if copy_base(k)[0] not in ours] + kept
    return replace(overrides, tracks=out, copies=copies, order=order or None, audio_track_ids=None)


def template_choice(overrides: Overrides, keys: list[str]) -> TemplateChoice:
    """What a template just set (apply_audio / apply_subs) for the tracks it decided (keys; their
    copies count too), kept on the job so the track editor can tell it from later hand edits."""
    ours = set(keys)
    copies = [c for c in overrides.copies if copy_base(c)[0] in ours and c not in ours]
    decided = [*keys, *copies]
    tracks = {k: copy.deepcopy(overrides.tracks.get(k) or TrackOverride()) for k in decided}
    order = [k for k in overrides.order or [] if k in tracks]
    return TemplateChoice(tracks, copies, order or None)
