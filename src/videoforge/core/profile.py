"""Profiles: one group's rules on top of the shared engine.

The engine finds, probes, encodes, muxes and runs jobs. A profile decides what
goes into the output: which tracks, copy or encode, titles, flags, the container,
whether external subtitles are taken, and how the finished file is checked.
Implementations live in videoforge.profiles (the core never imports them).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar

from videoforge.core.execute.audio import AudioSettings
from videoforge.core.jobs import ProbedInputs
from videoforge.core.models import AudioTrack, Issue, Overrides, Plan, SourceInfo, SubTrack, TrackProperty
from videoforge.core.video.settings import EncoderSettings, VideoSettings


class Profile(ABC):
    id: ClassVar[str]
    name: ClassVar[str]
    container: ClassVar[str] = "mkv"  # a key of core.execute.mux.MUXERS
    # Containers a job may pick instead (MuxSettings.container); () = only `container`.
    containers: ClassVar[tuple[str, ...]] = ()
    external_subtitles: ClassVar[bool] = True  # False: added subtitle files are ignored
    external_audio: ClassVar[bool] = False  # True: added audio files' tracks join the source's
    # Per-track on/off properties the user can override (TrackOverride.flags keys); the GUI builds its controls from these.
    track_properties: ClassVar[tuple[TrackProperty, ...]] = ()
    # True: the plan follows the user's track order (Overrides.order), titles and per-track audio
    # encodes (TrackOverride.action/bitrate_kbps/layout), so the UI offers the full track editor.
    # TrackOverride.exclude False keeps a track the profile's own choice leaves out.
    track_editor: ClassVar[bool] = False
    # True: the profile picks the output tracks by its own rules (e.g. a group's spec), so Settings'
    # default subtitle rules leave its new jobs alone; a template's rules, picked for the job, still apply.
    picks_tracks: ClassVar[bool] = False

    @abstractmethod
    def plan(self, probed: ProbedInputs, original_language: str | None, overrides: Overrides) -> Plan:
        """Decide the output tracks. Block (Severity.BLOCK issue) instead of guessing."""

    def video_defaults(self) -> tuple[VideoSettings, EncoderSettings]:
        """What a new job's video processing and encode start as (fresh copies)."""
        return VideoSettings(), EncoderSettings()

    def audio_settings(self) -> AudioSettings:
        """Encoder settings for the audio tracks the plan encodes."""
        return AudioSettings()

    def validate_output(self, plan: Plan, output: SourceInfo) -> list[Issue]:
        """Checks on the muxed file against its plan; a BLOCK marks the job INVALID."""
        return []

    def validate_release(self, info: SourceInfo) -> list[Issue]:
        """Checks on any finished release, including ones this tool didn't make (`videoforge validate`)."""
        return []

    def detected_flags(self, track: AudioTrack | SubTrack) -> dict[str, bool]:
        """track_properties values as the profile reads them before overrides (the GUI's starting values)."""
        return {}

    def output_stem(self, plan: Plan) -> str:
        if plan.source.path is not None:
            return plan.source.path.stem
        return Path(plan.source.name).stem
