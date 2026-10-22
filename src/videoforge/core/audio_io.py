"""Portable audio presets, including custom output titles."""

from typing import Any

from videoforge.core.audio_preset import AudioPresetSettings
from videoforge.core.encoder_io import read_grouped_bundle


def read_audio_bundle(doc: Any) -> dict[str, Any]:
    return read_grouped_bundle(
        doc, kind="audio", key="audio", format_name="videoforge.audio", settings=AudioPresetSettings
    )
