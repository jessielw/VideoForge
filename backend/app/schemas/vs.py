from pydantic import BaseModel


class VsProbeModel(BaseModel):
    """
    Transport model for a VapourSynth probe result.

    Kept minimal and nullable to reflect variable probe availability.
    """

    frames: int | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    fps_num: int | None = None
    fps_den: int | None = None
    error: str | None = None


class VsResponse(BaseModel):
    """Wrapper response for VapourSynth probe endpoint."""

    ok: bool
    path: str | None = None
    vapoursynth: VsProbeModel | None = None


__all__ = ["VsProbeModel", "VsResponse"]
