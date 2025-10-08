from typing import Any

from pydantic import BaseModel, Field


class MediaInfoResponse(BaseModel):
    """Response model for /api/mediainfo."""

    ok: bool
    path: str | None = None
    general: Any | None = None
    video_tracks: list[Any] = Field(default_factory=list)
    audio_tracks: list[Any] = Field(default_factory=list)
    text_tracks: list[Any] = Field(default_factory=list)
    mediainfo_data: Any | None = None
