"""Templates: settings for a job's whole run (video, encoder, audio, container, chapters), the way
StaxRip's templates hold a project's settings. Applied when jobs are added, or to a batch.

The crop is per source, so a template says what to do with it instead (CropMode). Its audio is by
position (TemplateAudio): settings for the source's 1st, 2nd, ... audio track, which become the
job's track overrides once the source's tracks are known (apply_audio). Subtitles stay per job.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from enum import StrEnum

from videoforge.core.execute.mux import MuxSettings
from videoforge.core.job import JobSpec
from videoforge.core.models import AudioTrack, OtherAudio, Overrides, TemplateAudio, TrackOverride, copy_base, track_key
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
    Added audio files and subtitles keep theirs."""
    keys = [track_key(t) for t in source_audio]
    ours = set(keys)
    copies = [c for c in overrides.copies if copy_base(c)[0] not in ours]
    tracks = {k: v for k, v in overrides.tracks.items() if copy_base(k)[0] not in ours}
    for i, key in enumerate(keys):
        if i < len(audio.slots):
            slot = audio.slots[i]
            if not slot.track.empty:
                tracks[key] = _fresh(slot.track)
            for n, extra in enumerate(slot.extra, 1):
                copies.append(f"{key}+{n}")
                tracks[f"{key}+{n}"] = _fresh(extra)
        elif audio.others is OtherAudio.EXCLUDE:
            tracks[key] = TrackOverride(exclude=True)
    order = [k for k in overrides.order if copy_base(k)[0] not in ours] if overrides.order else None
    return replace(overrides, tracks=tracks, copies=copies, order=order or None, audio_track_ids=None)


def _fresh(ov: TrackOverride) -> TrackOverride:
    """A template's track settings for one job: a copy, without a language (that's per source)."""
    out = copy.deepcopy(ov)
    out.language = None
    return out
