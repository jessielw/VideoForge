"""Installation-wide queue limits and the file reservations held from admission through cleanup."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from videoforge.core.job import JobSpec
from videoforge.core.video.settings import Encoder


class EncoderLimit(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    cap: int = Field(default=1, ge=1)
    run_alone: bool = False


def default_limits() -> dict[str, EncoderLimit]:
    limits = {name: EncoderLimit() for name in [*(e.value for e in Encoder), "remux"]}
    limits["x264"] = EncoderLimit(cap=2)
    limits["x265"] = EncoderLimit(run_alone=True)
    return limits


class Concurrency(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    enabled: bool = False
    total: int = Field(default=2, ge=1)
    limit_samples: bool = False
    encoders: dict[str, EncoderLimit] = Field(default_factory=default_limits)

    @field_validator("encoders")
    @classmethod
    def known_encoders(cls, configured: dict[str, EncoderLimit]) -> dict[str, EncoderLimit]:
        defaults = default_limits()
        if unknown := configured.keys() - defaults.keys():
            raise ValueError(f"Unknown encoder: {', '.join(sorted(unknown))}")
        return defaults | configured

    def waiting(self, kind: str, active: Sequence[str]) -> str:
        if not active:
            return ""
        if self.enabled:
            for other in active:
                if self.encoders[other].run_alone:
                    return f"{other} is set to run alone"
            if self.encoders[kind].run_alone:
                return f"{kind} is waiting to run alone"
            if active.count(kind) >= self.encoders[kind].cap:
                return f"{kind} has reached its job limit"
        if len(active) >= (self.total if self.enabled else 1):
            return "All job slots are in use"
        return ""


def encoder_type(spec: JobSpec) -> str:
    return spec.encoder.encoder.value if spec.encodes_video else "remux"


@dataclass(frozen=True)
class RunPaths:
    home: Path
    work: Path
    inputs: frozenset[Path]
    outputs: frozenset[Path]

    @classmethod
    def for_job(cls, spec: JobSpec, output: Path | None) -> RunPaths:
        writes = () if output is None else (output, output.with_name(output.name + ".partial"))
        return cls(
            spec.job_dir.resolve(),
            spec.work_dir.resolve(),
            frozenset(p.resolve() for p in spec.inputs.files()),
            frozenset(p.resolve() for p in writes),
        )

    def conflicts(self, other: RunPaths) -> bool:
        # Generated files (including tool-selected index names) live beneath work. Different
        # variants coordinate those at each step. External consumers must wait through cleanup.
        return (
            self.home == other.home
            or bool(self.outputs & (other.inputs | other.outputs) or other.outputs & self.inputs)
            or any(p.is_relative_to(other.work) for p in self.inputs | self.outputs)
            or any(p.is_relative_to(self.work) for p in other.inputs | other.outputs)
        )
