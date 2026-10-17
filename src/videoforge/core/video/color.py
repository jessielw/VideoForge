"""The source's colour description (MediaInfo) -> x264 / x265 flags.

vspipe's y4m carries no colour information, so without these an encode is untagged and a player guesses
(an HDR10 source plays washed out). The flags go before the job's options, so an option set there wins.
x264 gets the VUI flags only (no HDR10 SEI); Dolby Vision isn't carried.
"""

from __future__ import annotations

from fractions import Fraction
import re
from typing import Any

from videoforge.core.models import VideoColor
from videoforge.core.video.settings import Encoder, EncoderSettings

# MediaInfo's names -> x264 / x265's (ITU-T H.273)
PRIMARIES = {
    "BT.709": "bt709",
    "BT.470 System M": "bt470m",
    "BT.601 PAL": "bt470bg",
    "BT.601 NTSC": "smpte170m",
    "SMPTE 240M": "smpte240m",
    "Generic film": "film",
    "BT.2020": "bt2020",
    "XYZ": "smpte428",
    "DCI P3": "smpte431",
    "Display P3": "smpte432",
}
TRANSFER = {
    "BT.709": "bt709",
    "BT.470 System M": "bt470m",
    "BT.470 System B/G": "bt470bg",
    "BT.601": "smpte170m",
    "SMPTE 240M": "smpte240m",
    "Linear": "linear",
    "Logarithmic (100:1)": "log100",
    "Logarithmic (316.22777:1)": "log316",
    "xvYCC": "iec61966-2-4",
    "BT.1361": "bt1361e",
    "sRGB/sYCC": "iec61966-2-1",
    "BT.2020 (10-bit)": "bt2020-10",
    "BT.2020 (12-bit)": "bt2020-12",
    "PQ": "smpte2084",
    "SMPTE 428M": "smpte428",
    "HLG": "arib-std-b67",
}
MATRIX = {
    "Identity": "gbr",
    "BT.709": "bt709",
    "FCC 73.682": "fcc",
    "BT.470 System B/G": "bt470bg",
    "BT.601": "smpte170m",
    "SMPTE 240M": "smpte240m",
    "YCgCo": "ycgco",
    "BT.2020 non-constant": "bt2020nc",
    "BT.2020 constant": "bt2020c",
    "Y'D'zD'x": "smpte2085",
    "Chromaticity-derived non-constant": "chroma-derived-nc",
    "Chromaticity-derived constant": "chroma-derived-c",
    "ICtCp": "ictcp",
}
RANGE = {"Limited": "limited", "Full": "full"}
X264_RANGE = {"limited": "tv", "full": "pc"}

_D65 = ("0.3127", "0.3290")
# A mastering display MediaInfo names: (red, green, blue, white point) as (x, y)
DISPLAYS = {
    "Display P3": (("0.680", "0.320"), ("0.265", "0.690"), ("0.150", "0.060"), _D65),
    "DCI P3": (("0.680", "0.320"), ("0.265", "0.690"), ("0.150", "0.060"), ("0.314", "0.351")),
    "BT.2020": (("0.708", "0.292"), ("0.170", "0.797"), ("0.131", "0.046"), _D65),
    "BT.709": (("0.640", "0.330"), ("0.300", "0.600"), ("0.150", "0.060"), _D65),
}
_XY = re.compile(r"x=([\d.]+)\s+y=([\d.]+)")
_LUMINANCE = re.compile(r"min:\s*([\d.]+)\s*cd/m2,\s*max:\s*([\d.]+)\s*cd/m2")
_NUMBER = re.compile(r"[\d.]+")
_TYPE = re.compile(r"Type (\d)")


def _text(track: Any, name: str) -> str:
    value = getattr(track, name, None)
    return str(value).split(" / ")[0].strip() if value else ""  # "Container / Stream" pairs: the first


def _units(value: str, per: int) -> int:
    return round(Fraction(value) * per)


def master_display(primaries: str, luminance: str) -> str:
    """x265's --master-display from MediaInfo's mastering display primaries (a name, or "R: x=... y=..., G:
    ..., B: ..., White point: ...") and luminance ("min: 0.0050 cd/m2, max: 1000 cd/m2"); "" when either
    can't be read. Chromaticities are in 0.00002 units, luminance in 0.0001 cd/m2."""
    lum = _LUMINANCE.search(luminance)
    points = DISPLAYS.get(primaries)
    if points is None:
        found = _XY.findall(primaries)
        if len(found) != 4:
            return ""
        points = tuple(found)
    if lum is None:
        return ""
    (r, g, b, wp) = [(_units(x, 50000), _units(y, 50000)) for x, y in points]
    low, high = _units(lum.group(1), 10000), _units(lum.group(2), 10000)
    return f"G({g[0]},{g[1]})B({b[0]},{b[1]})R({r[0]},{r[1]})WP({wp[0]},{wp[1]})L({high},{low})"


def _nits(track: Any, name: str) -> int:
    m = _NUMBER.search(_text(track, name))
    return round(float(m.group())) if m else 0


def from_mediainfo(track: Any) -> VideoColor:
    """A MediaInfo video track's colour description (names it doesn't know are left out)."""
    if track is None:
        return VideoColor()
    loc = _TYPE.search(_text(track, "chroma_subsampling_position"))
    return VideoColor(
        primaries=PRIMARIES.get(_text(track, "color_primaries"), ""),
        transfer=TRANSFER.get(_text(track, "transfer_characteristics"), ""),
        matrix=MATRIX.get(_text(track, "matrix_coefficients"), ""),
        range=RANGE.get(_text(track, "color_range"), ""),
        chroma_loc=int(loc.group(1)) if loc else None,
        master_display=master_display(
            _text(track, "mastering_display_color_primaries"), _text(track, "mastering_display_luminance")
        ),
        max_cll=_nits(track, "maximum_content_light_level"),
        max_fall=_nits(track, "maximum_frameaverage_light_level"),
    )


def color_args(color: VideoColor | None, settings: EncoderSettings) -> list[str]:
    """The encoder flags for the source's colour (none when settings.source_color is off); x265 also gets
    the HDR10 SEI (--master-display, --max-cll, --hdr10). Metadata only: tuning such as --hdr10-opt is the
    job's options' business (as in StaxRip's "Import VUI metadata")."""
    if color is None or not settings.source_color:
        return []
    x265 = settings.encoder is Encoder.X265
    args = []
    for flag, value in (
        ("--colorprim", color.primaries),
        ("--transfer", color.transfer),
        ("--colormatrix", color.matrix),
    ):
        if value:
            args += [flag, value]
    if color.range:
        args += ["--range", color.range if x265 else X264_RANGE[color.range]]
    if color.chroma_loc is not None:
        args += ["--chromaloc", str(color.chroma_loc)]
    if not x265:
        return args
    if color.master_display:
        args += ["--master-display", color.master_display]
    if color.max_cll or color.max_fall:
        args += ["--max-cll", f"{color.max_cll},{color.max_fall}"]
    if color.master_display or color.max_cll or color.max_fall:
        args += ["--hdr10"]
    return args
