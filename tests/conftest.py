from __future__ import annotations

from pathlib import Path

import pytest

from videoforge.core.jobs import ProbedInputs
from videoforge.core.models import (
    AudioCodec,
    AudioTrack,
    JobInputs,
    Layout,
    Overrides,
    Plan,
    SourceInfo,
    SubFormat,
    SubTrack,
    VideoInfo,
)
from videoforge.profiles.manual import ManualProfile


@pytest.fixture(scope="session")
def profile():
    return ManualProfile()


def plan_for(
    src: SourceInfo,
    encode: SourceInfo | None = None,
    overrides: Overrides | None = None,
    *,
    external_subs: list[SubTrack] | None = None,
    chapters: Path | None = None,
) -> Plan:
    """The manual profile's plan for already-probed inputs."""
    inputs = JobInputs(source=src.path or Path(src.name), encode=encode.path if encode else None, chapters=chapters)
    probed = ProbedInputs(inputs, src, encode, list(external_subs or []))
    return ManualProfile().plan(probed, None, overrides or Overrides())


def audio(
    codec: AudioCodec,
    layout: str,
    language: str = "en",
    *,
    atmos: bool = False,
    title: str = "",
    index: int = 0,
    bitrate: int | None = None,
    default: bool = False,
    commentary: bool = False,
) -> AudioTrack:
    return AudioTrack(
        id=index + 1,
        index=index,
        codec=codec,
        layout=Layout.parse(layout),
        language=language,
        title=title,
        default=default,
        commentary=commentary,
        atmos=atmos,
        bitrate_kbps=bitrate,
    )


def sub(
    fmt: SubFormat,
    language: str = "en",
    title: str = "",
    *,
    index: int = 0,
    forced: bool = False,
    hi: bool = False,
    elements: int | None = None,
    external: str | None = None,
    tags: frozenset[str] = frozenset(),
) -> SubTrack:
    return SubTrack(
        id=-1 if external else 10 + index,
        index=index,
        format=fmt,
        language=language,
        title=title,
        forced=forced,
        hearing_impaired=hi,
        element_count=elements,
        external_path=Path(external) if external else None,
        tags=tags,
    )


def source(audio_tracks=(), subs=(), width: int = 1920, name: str = "Movie.mkv") -> SourceInfo:
    return SourceInfo(
        path=Path(name),
        name=name,
        video=VideoInfo(width=width, height=width * 9 // 16),
        audio=list(audio_tracks),
        subs=list(subs),
        has_chapters=True,
    )


def simulate_output(plan: Plan, name: str = "Movie.2020.1080p.BluRay.x264.mkv") -> SourceInfo:
    """What the muxed file would look like if the executor follows the plan exactly."""
    out_audio = [
        AudioTrack(
            id=i + 1,
            index=i,
            codec=a.out_codec,
            layout=a.out_layout,
            language=a.language,
            title=a.title,
            default=a.default,
            forced=a.forced,
            hearing_impaired=a.hearing_impaired,
            commentary=a.commentary,
            original=a.original,
            atmos=a.out_atmos,
            bitrate_kbps=a.bitrate_kbps,
        )
        for i, a in enumerate(plan.audio)
    ]
    out_subs = [
        SubTrack(
            id=len(out_audio) + i + 1,
            index=i,
            format=s.source.format,
            language=s.language,
            title=s.title,
            default=s.default,
            forced=s.forced,
            hearing_impaired=s.hearing_impaired,
            commentary=s.commentary,
            original=s.original,
        )
        for i, s in enumerate(plan.subs)
    ]
    video = plan.source.video
    return SourceInfo(path=None, name=name, video=video, audio=out_audio, subs=out_subs, has_chapters=True)
