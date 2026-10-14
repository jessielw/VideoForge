"""Templates: settings for a job's whole run (video, encoder, container, chapters), the way
StaxRip's templates hold a project's settings. Applied when jobs are added, or to a batch.

Audio and subtitle choices aren't in a template: they depend on each source's tracks. The
crop is per source too, so a template says what to do with it instead (CropMode).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from enum import StrEnum

from videoforge.core.execute.mux import MuxSettings
from videoforge.core.job import JobSpec
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
