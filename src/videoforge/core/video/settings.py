"""What a job does to the video: the VapourSynth processing and the encoder settings.

Both are plain data, stored with the job and edited in the UI. script.py turns
VideoSettings into a script; encoders.py turns EncoderSettings into command lines.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from fractions import Fraction
import math
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
    height: int  # with keep_ar, the last fitted height: each replan fits it to the job's source and crop
    kernel: str = "Spline36"  # a core.resize function: Spline36, Bicubic, Lanczos, Point, ...
    # StaxRip's resize: the height follows the width, so the square-pixel output keeps the display aspect
    # ratio of the picture going in (the cropped source, an anamorphic one's pixel aspect included).
    keep_ar: bool = False
    mod: int = 2  # both sides are a multiple of this


SQUARE_ENOUGH = Fraction(1, 100)  # a pixel this close to square is written as square


def round_mod(value: Fraction | float, mod: int) -> int:
    """The nearest multiple of mod (halves up; at least mod). frontend/src/lib/resize.ts does the same."""
    return max(mod, math.floor(Fraction(value) / mod + Fraction(1, 2)) * mod)


def fit_height(width: int, src_width: int, src_height: int, sar: Fraction = Fraction(1), mod: int = 2) -> int:
    """The height of a width-wide, square-pixel picture with the display aspect ratio of src_width x
    src_height pixels shaped sar (width / height of one pixel)."""
    return round_mod(Fraction(width * src_height) / (src_width * sar), mod)


def fit_width(height: int, src_width: int, src_height: int, sar: Fraction = Fraction(1), mod: int = 2) -> int:
    return round_mod(Fraction(height) * src_width * sar / src_height, mod)


def ar_error(width: int, height: int, src_width: int, src_height: int, sar: Fraction = Fraction(1)) -> float:
    """How far width x height's aspect ratio is from the source's display aspect ratio, in percent."""
    return float((Fraction(width, height) / (Fraction(src_width, src_height) * sar) - 1) * 100)


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

    def resize_input(self, width: int, height: int) -> tuple[int, int]:
        """The size going into the resize step: the source's, less the crop when it comes first."""
        for s in self.filters:
            if s.category is FilterCategory.RESIZE:
                break
            if s.category is FilterCategory.CROP:
                c = self.crop
                width, height = width - c.left - c.right, height - c.top - c.bottom
        return width, height

    def fit_resize(self, width: int, height: int, sar: Fraction = Fraction(1)) -> bool:
        """A keep_ar resize fitted to a width x height source (sar-shaped pixels) and the crop: the width
        on its mod, the height following it. True when that changed the size."""
        r = self.resize
        if r is None or not r.keep_ar or self.custom is not None:
            return False
        in_w, in_h = self.resize_input(width, height)
        if in_w <= 0 or in_h <= 0:
            return False
        w = round_mod(r.width, r.mod)
        h = fit_height(w, in_w, in_h, sar, r.mod)
        if (w, h) == (r.width, r.height):
            return False
        r.width, r.height = w, h
        return True

    def output_sar(self, width: int, height: int, sar: Fraction = Fraction(1)) -> Fraction | None:
        """The encode's pixel aspect ratio for a width x height source of sar-shaped pixels, so it plays at
        the shape it had (vspipe's y4m carries none: the encoder is told). Without a resize, the source's
        (a crop doesn't change a pixel's shape); after a keep-AR resize, square; after a fixed size, the
        pixel shape that undoes its stretch (square when that's within SQUARE_ENOUGH, as a fixed size
        rounded from the aspect is). None for a custom body: its size isn't known here."""
        if self.custom is not None:
            return None
        r = self.resize
        if r is None:
            return sar
        if r.keep_ar:
            return Fraction(1)
        in_w, in_h = self.resize_input(width, height)
        if min(in_w, in_h, r.width, r.height) <= 0:
            return Fraction(1)
        shape = (sar * in_w * r.height / (in_h * r.width)).limit_denominator(10000)
        return Fraction(1) if abs(shape - 1) <= SQUARE_ENOUGH else shape


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
