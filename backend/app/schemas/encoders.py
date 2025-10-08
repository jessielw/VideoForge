from pydantic import BaseModel

from app.enums.audio import AudioEncoder


class VideoConfigModel(BaseModel):
    encoder: str
    mode: str
    crf: int | None = None
    bitrate: int | None = None
    preset: str | None = None
    tune: str | None = None
    customArgs: str | None = None


class AudioTrackConfig(BaseModel):
    """Configuration for a single audio track."""

    sourceTrack: int  # Which source track to use (0, 1, 2...)
    encoder: AudioEncoder
    bitrate: int | None = 192  # kbps (ignored for copy mode)
    language: str | None = None  # Language tag (e.g., "eng", "jpn")
    name: str | None = None  # Track name/title


class AudioConfigModel(BaseModel):
    """Audio processing configuration supporting multiple tracks."""

    tracks: list[AudioTrackConfig] = []  # List of audio tracks to process


class SubtitleTrackConfig(BaseModel):
    """Configuration for a single subtitle track."""

    sourceTrack: int  # Which source track to use (0, 1, 2...)
    mode: str  # "copy", "extract", "burn"
    language: str | None = None  # Language tag (e.g., "eng", "jpn")
    name: str | None = None  # Track name/title
    forced: bool | None = False  # Forced subtitle flag
    default: bool | None = False  # Default subtitle flag


class SubtitleConfigModel(BaseModel):
    """Subtitle processing configuration supporting multiple tracks."""

    tracks: list[SubtitleTrackConfig] = []  # List of subtitle tracks to process


class OutputConfigModel(BaseModel):
    outputPath: str
    container: str
    muxer: str | None = None
    fastStart: bool | None = False
    overwrite: bool | None = False


class JobConfigModel(BaseModel):
    sourcePath: str
    vsScript: str
    videoConfig: VideoConfigModel
    audioConfig: AudioConfigModel
    subtitleConfig: SubtitleConfigModel | None = None
    outputConfig: OutputConfigModel
    name: str | None = None


class SubmitJobRequest(BaseModel):
    config: JobConfigModel


class ReorderJobsRequest(BaseModel):
    jobIds: list[int]
