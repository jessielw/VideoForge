"""Reusable audio encoding settings, independent of a source track's metadata."""

from __future__ import annotations

from dataclasses import dataclass, field

from videoforge.core.execute.audio import ENCODES
from videoforge.core.models import AudioAction, Layout


@dataclass(slots=True)
class AudioPresetSettings:
    action: AudioAction = AudioAction.COPY
    layout: Layout | None = None
    bitrate_kbps: int | None = None
    options: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.action is AudioAction.COPY:
            if self.layout is not None or self.bitrate_kbps is not None or self.options:
                raise ValueError("Copy does not take channels, bitrate, or encoder options")
            return
        enc = ENCODES[self.action]
        if self.layout is not None and self.layout not in enc.layouts:
            raise ValueError(f"{enc.label} does not support {self.layout}")
        if self.bitrate_kbps is not None:
            if type(self.bitrate_kbps) is not int or self.bitrate_kbps <= 0:
                raise ValueError("Bitrate must be a positive whole number")
            if enc.bitrates is None:
                raise ValueError(f"{enc.label} is lossless and does not take a bitrate")
            layout = self.layout or max(enc.layouts, key=lambda lay: lay.channels)
            if problem := enc.bitrate_problem(self.bitrate_kbps, layout):
                raise ValueError(problem)
        if any(not isinstance(v, str) for v in self.options.values()):
            raise ValueError("Encoder option values must be text")
        unknown = self.options.keys() - {o.key for o in enc.options}
        if unknown:
            raise ValueError(f"Unknown {enc.label} options: {', '.join(sorted(unknown))}")
        _, problems = enc.resolve_options(self.options)
        if problems:
            raise ValueError("; ".join(problems))
        self.options = {k: v.strip() for k, v in self.options.items()}
