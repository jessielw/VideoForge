"""Templates: what applying one does to a job's settings."""

from __future__ import annotations

from pathlib import Path

from videoforge.core.execute.mux import MuxSettings
from videoforge.core.job import JobSpec
from videoforge.core.models import JobInputs
from videoforge.core.template import CropMode, Template
from videoforge.core.video.settings import Crop, EncoderSettings, VideoSettings


def spec(encode: Path | None = None) -> JobSpec:
    return JobSpec(JobInputs(Path("Show.S01E01.mkv"), encode=encode), "manual",
                   video=VideoSettings(crop=Crop(0, 140, 0, 140)))


def test_keep_fixed_and_auto_crop():
    t = Template(VideoSettings(filters="clip = clip", crop=Crop(8, 0, 8, 0)), EncoderSettings(crf=16),
                 MuxSettings("mp4", "-x"), qpf=False)
    s = spec()
    t.apply(s)
    assert s.video.crop == Crop(0, 140, 0, 140) and s.video.filters == "clip = clip" and not s.autocrop
    assert s.encoder.crf == 16 and s.mux == MuxSettings("mp4", "-x") and not s.qpf
    assert s.video is not t.video and s.encoder is not t.encoder and s.mux is not t.mux  # copies

    t.crop_mode = CropMode.FIXED
    t.apply(s)
    assert s.video.crop == Crop(8, 0, 8, 0) and s.video.crop is not t.video.crop

    t.crop_mode = CropMode.AUTO
    t.apply(s)
    assert s.autocrop
    reuses = spec(encode=Path("Show.S01E01.264"))
    t.apply(reuses)
    assert not reuses.autocrop  # nothing to crop: the video isn't encoded here
