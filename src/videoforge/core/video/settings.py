"""What a job does to the video: the VapourSynth processing and the encoder settings.

Both are plain data, stored with the job and edited in the UI. script.py turns
VideoSettings into a script; encoders.py turns EncoderSettings into command lines.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class SourceFilter(StrEnum):
    BESTSOURCE = "bestsource"  # core.bs.VideoSource: exact seeking, slow first index
    LSMASH = "lsmash"  # core.lsmas.LWLibavSource
    FFMS2 = "ffms2"  # core.ffms2.Source


@dataclass(slots=True)
class Crop:
    left: int = 0
    top: int = 0
    right: int = 0
    bottom: int = 0

    @property
    def is_zero(self) -> bool:
        return not (self.left or self.top or self.right or self.bottom)


@dataclass(slots=True)
class Resize:
    width: int
    height: int
    kernel: str = "Spline36"  # a core.resize function: Spline36, Bicubic, Lanczos, Point, ...


@dataclass(slots=True)
class VideoSettings:
    source_filter: SourceFilter = SourceFilter.BESTSOURCE
    crop: Crop = field(default_factory=Crop)
    resize: Resize | None = None
    # Extra script lines after crop/resize: they read and reassign `clip`.
    filters: str = ""
    # A whole processing body instead of crop/resize/filters (also reads `src`, assigns `clip`).
    custom: str | None = None


class Encoder(StrEnum):
    X264 = "x264"
    X265 = "x265"


class RateControl(StrEnum):
    CRF = "crf"  # one pass, constant quality
    ABR = "abr"  # one pass, average bitrate
    TWO_PASS = "2pass"  # two passes, average bitrate


@dataclass(slots=True)
class EncoderSettings:
    encoder: Encoder = Encoder.X264
    rate_control: RateControl = RateControl.CRF
    crf: float = 18.0
    bitrate_kbps: int = 10000
    preset: str = "slower"
    tune: str = ""
    depth: int = 8  # output bit depth; the script converts to it
    # --name value pairs, in order; an empty value is a bare flag (e.g. "no-fast-pskip": "").
    options: dict[str, str] = field(default_factory=dict)
    extra: str = ""  # raw arguments appended last

    @property
    def passes(self) -> int:
        return 2 if self.rate_control is RateControl.TWO_PASS else 1
