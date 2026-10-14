"""Templates: settings for a job's whole run (video, encoder, audio, container, chapters), the way
StaxRip's templates hold a project's settings. Applied when jobs are added, or to a batch.

The crop is per source, so a template says what to do with it instead (CropMode). Its audio is by
position (TemplateAudio): settings for the source's 1st, 2nd, ... audio track, which become the
job's track overrides once the source's tracks are known (apply_audio), each made to fit its track
(fit_audio), so one template suits a season's 5.1 and stereo episodes. Subtitles stay per job.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from enum import StrEnum

from videoforge.core.execute.audio import ENCODES
from videoforge.core.execute.mux import MuxSettings
from videoforge.core.job import JobSpec
from videoforge.core.models import (
    AudioAction,
    AudioCodec,
    AudioTrack,
    OtherAudio,
    Overrides,
    TemplateAudio,
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


def apply_audio(overrides: Overrides, audio: TemplateAudio, source_audio: list[AudioTrack]) -> Overrides:
    """The job's overrides with its source audio set from the template: the earlier choices for those
    tracks (settings, copies, order) are replaced; slot n goes to the nth track, extra slots are ignored.
    Each slot is fitted to its track (fit_audio). Added audio files and subtitles keep theirs."""
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
        elif audio.others is OtherAudio.EXCLUDE:
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
