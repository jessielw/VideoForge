"""What a job does to the video: the VapourSynth processing and the encoder settings.

Both are plain data, stored with the job and edited in the UI. script.py turns
VideoSettings into a script; encoders.py turns EncoderSettings into command lines.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class SourceFilter(StrEnum):
    FFMS2 = "ffms2"  # core.ffms2.Source: quick index (the default)
    BESTSOURCE = "bestsource"  # core.bs.VideoSource: exact seeking, slow first index (decodes the whole video)
    LSMASH = "lsmash"  # core.lsmas.LWLibavSource


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


class FilterCategory(StrEnum):
    """Where a filter goes in the chain: a new one is placed after the others of its category and those
    before it (StaxRip's categories, with field matching before the crop so the crop can't break it)."""

    FIELD = "field"  # IVTC, deinterlacing
    CROP = "crop"
    RESTORATION = "restoration"  # dirty lines, deblocking, dehaloing
    NOISE = "noise"  # denoising
    LINE = "line"  # anti-aliasing, sharpening
    RESIZE = "resize"
    DEBAND = "deband"
    GRAIN = "grain"
    CUSTOM = "custom"  # the user's own lines

    @property
    def rank(self) -> int:
        return list(FilterCategory).index(self)


@dataclass(slots=True)
class FilterStep:
    category: FilterCategory
    name: str
    # Lines that read and reassign `clip`. The crop and resize steps have none: theirs come from
    # VideoSettings.crop and .resize (the steps only say where in the chain they go).
    script: str = ""
    enabled: bool = True


def default_chain() -> list[FilterStep]:
    return [FilterStep(FilterCategory.CROP, "Crop"), FilterStep(FilterCategory.RESIZE, "Resize")]


@dataclass(slots=True)
class VideoSettings:
    source_filter: SourceFilter = SourceFilter.FFMS2
    crop: Crop = field(default_factory=Crop)
    resize: Resize | None = None
    # The processing, in order: always one crop step and one resize step, and any filters around them.
    filters: list[FilterStep] = field(default_factory=default_chain)
    # A whole processing body instead of the filters (also reads `src`, assigns `clip`).
    custom: str | None = None

    def __post_init__(self) -> None:
        # Exactly one crop and one resize step: a missing one goes in at its category's place.
        steps: list[FilterStep] = []
        seen: set[FilterCategory] = set()
        for s in self.filters:
            if s.category in (FilterCategory.CROP, FilterCategory.RESIZE):
                if s.category in seen:
                    continue
                seen.add(s.category)
                s.enabled = True
            steps.append(s)
        for missing in (c for c in default_chain() if c.category not in seen):
            at = next((i for i, s in enumerate(steps) if s.category.rank > missing.category.rank), len(steps))
            steps.insert(at, missing)
        self.filters = steps

    @staticmethod
    def upgrade_json(data: dict[str, Any]) -> dict[str, Any]:
        """Settings saved before the chain: `filters` was extra lines after the crop and resize."""
        lines = data.get("filters")
        if not isinstance(lines, str):
            return data
        chain = [{"category": "crop", "name": "Crop"}, {"category": "resize", "name": "Resize"}]
        if lines.strip():
            chain.append({"category": "custom", "name": "Custom", "script": lines})
        return {**data, "filters": chain}

    def output_size(self, width: int, height: int) -> tuple[int, int]:
        """The size the crop and resize make of a width x height source, in their chain order."""
        for s in self.filters:
            if s.category is FilterCategory.CROP:
                c = self.crop
                width, height = width - c.left - c.right, height - c.top - c.bottom
            elif s.category is FilterCategory.RESIZE and self.resize is not None:
                width, height = self.resize.width, self.resize.height
        return width, height


class Encoder(StrEnum):
    X264 = "x264"
    X265 = "x265"


class RateControl(StrEnum):
    CRF = "crf"  # one pass, constant quality
    ABR = "abr"  # one pass, average bitrate
    TWO_PASS = "2pass"  # noqa: S105 (two passes, average bitrate)


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
