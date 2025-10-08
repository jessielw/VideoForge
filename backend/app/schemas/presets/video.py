from pydantic import BaseModel


class VideoEncoderPresetCreate(BaseModel):
    """Request model for creating a preset."""

    name: str
    description: str | None = None
    encoder: str
    rate_control_mode: str
    crf: int | None = None
    target_bitrate: int | None = None
    preset: str | None = None
    tune: str | None = None
    custom_args: str | None = None


class VideoEncoderPresetResponse(BaseModel):
    """Response model for a preset."""

    id: str
    name: str
    description: str | None
    encoder: str
    rate_control_mode: str
    crf: int | None
    target_bitrate: int | None
    preset: str | None
    tune: str | None
    custom_args: str | None
    is_builtin: bool
    created_at: str
    updated_at: str
