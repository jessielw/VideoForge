"""Starter encoder presets: built-in settings for the encoders a profile's defaults don't cover, offered next to
the profile's own (x264 CRF 18 slow) in every preset picker. The user saves a copy to change one.

The colour and HDR10 flags come from the source either way (EncoderSettings.source_color, color.py): "SDR" and
"HDR10" say what the preset is tuned for, not what it tags. Quality and speed follow StaxRip's defaults where it
has them (x265 CRF 20, 10-bit; SVT-AV1 at the Encoder tab's preset 4), a step slower for archive-quality output.
"""

from __future__ import annotations

from dataclasses import dataclass

from videoforge.core.video.settings import Encoder, EncoderSettings, RateControl


@dataclass(frozen=True)
class Starter:
    name: str  # stable id, e.g. "x265-sdr"
    label: str
    settings: EncoderSettings


def _x265(
    crf: float, *, options: dict[str, str] | None = None, hdr10plus: bool = True, dolby_vision: bool = True
) -> EncoderSettings:
    return EncoderSettings(
        Encoder.X265,
        RateControl.CRF,
        crf=crf,
        preset="slow",
        depth=10,
        options=options or {},
        hdr10plus=hdr10plus,
        dolby_vision=dolby_vision,
    )


def starters() -> list[Starter]:
    """Fresh copies (a job takes the settings and may change them)."""
    return [
        Starter(
            "x265-sdr",
            "x265 SDR, CRF 20",
            _x265(20.0, hdr10plus=False, dolby_vision=False),
        ),
        Starter(
            "x265-hdr10",
            "x265 HDR10 / HDR10+, CRF 18",
            _x265(18.0, dolby_vision=False),
        ),
        # Dolby Vision needs VBV (x265 refuses it without): --level-idc 5.1 fills it with the level's High tier
        # max bitrate (encoders.level_vbv), enough for 4K at 60 fps.
        Starter(
            "x265-dv",
            "x265 Dolby Vision, CRF 18, level 5.1",
            _x265(18.0, options={"level-idc": "5.1"}),
        ),
        Starter(
            "svtav1-10bit",
            "SVT-AV1 10-bit, CRF 30",
            EncoderSettings(Encoder.SVTAV1, RateControl.CRF, crf=30.0, preset="4", depth=10),
        ),
    ]
