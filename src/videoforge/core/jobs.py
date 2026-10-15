"""Engine flow for one job: discover inputs, probe them once, plan with a profile.

Probing is the slow part (network shares), so ProbedInputs is kept by callers and
any override replans from it without touching the files again.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING

from videoforge.core.config import AppConfig
from videoforge.core.models import (
    AudioTrack,
    EncodeState,
    Issue,
    JobInputs,
    Overrides,
    Plan,
    Severity,
    SourceInfo,
    SubTrack,
)
from videoforge.core.pairing import (
    MatchResult,
    discover,
    external_sub_track,
    name_delay_ms,
    name_language,
    name_without_delay,
)
from videoforge.core.probe import mkvmerge_identify, probe

if TYPE_CHECKING:
    from videoforge.core.profile import Profile


def has_audio_via_mkvmerge(app: AppConfig) -> Callable[[Path], bool]:
    def has_audio(path: Path) -> bool:
        return any(t["type"] == "audio" for t in mkvmerge_identify(path, app.tools.mkvmerge).get("tracks", []))

    return has_audio


def discover_jobs(
    paths: Iterable[Path], app: AppConfig, has_audio: Callable[[Path], bool] | None = None
) -> MatchResult:
    """Files/folders (one mixed drop) to matched job inputs."""
    return discover(paths, app.matching, has_audio or has_audio_via_mkvmerge(app))


@dataclass(slots=True)
class ProbedInputs:
    inputs: JobInputs
    source: SourceInfo
    encode: SourceInfo | None
    external_subs: list[SubTrack] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)  # from reading the inputs (e.g. unparseable sub names)
    external_audio: list[AudioTrack] = field(default_factory=list)  # the tracks of added audio files


def external_tracks(source: SourceInfo, paths: list[Path]) -> tuple[list[SubTrack], list[Issue]]:
    """Parse external subtitle files into tracks.

    A file whose name has no language is kept as "und" with a WARN; plan_job drops it
    unless the profile has a track editor (where the user sets the language).
    A file extracted from the source ("_trackN_") inherits that track's title and
    forced/SDH flags, so "English (ASS Foreign)" converted to SRT is still forced.
    """
    tracks: list[SubTrack] = []
    issues: list[Issue] = []
    stem = source.path.stem if source.path else source.name.rsplit(".", 1)[0]
    by_number = {s.number: s for s in source.subs if s.number is not None}
    for i, path in enumerate(paths):
        track = external_sub_track(path, stem, i, keep_unknown=True)
        if track is None:
            continue
        if track.language == "und":
            issues.append(
                Issue(
                    Severity.WARN,
                    "subs.external_name",
                    f"Ignored {path.name}: no language in the file name (e.g. .en.srt)",
                )
            )
        origin = by_number.get(track.extracted_from) if track.extracted_from else None
        if origin is not None:
            track = replace(
                track,
                title=origin.title,
                forced=track.forced or origin.forced,
                hearing_impaired=track.hearing_impaired or origin.hearing_impaired,
            )
        tracks.append(track)
    return tracks, issues


def external_audio_tracks(paths: list[Path], mkvmerge: str) -> tuple[list[AudioTrack], list[Issue]]:
    """Probe added audio files: each audio track is kept with its file. A language the container
    lacks comes from the file name; an eac3to "DELAY Xms" in the name is the delay to apply."""
    tracks: list[AudioTrack] = []
    issues: list[Issue] = []
    for path in paths:
        info = probe(path, mkvmerge)
        if not info.audio:
            issues.append(Issue(Severity.WARN, "audio.external_none", f"Ignored {path.name}: it has no audio track"))
        delay = name_delay_ms(path.stem)
        for t in info.audio:
            language = t.language if t.language != "und" else (name_language(name_without_delay(path.stem)) or "und")
            tracks.append(
                replace(t, external_path=path, language=language, delay_ms=t.delay_ms if delay is None else delay)
            )
    return tracks, issues


def probe_inputs(inputs: JobInputs, app: AppConfig) -> ProbedInputs:
    mkvmerge = app.tools.mkvmerge
    source = probe(inputs.source, mkvmerge)
    encode = probe(inputs.encode, mkvmerge) if inputs.encode else None
    ext, ext_issues = external_tracks(source, inputs.subtitles)
    ext_audio, audio_issues = external_audio_tracks(inputs.audio, mkvmerge)
    return ProbedInputs(inputs, source, encode, ext, ext_issues + audio_issues, ext_audio)


def plan_job(
    profile: Profile,
    probed: ProbedInputs,
    original_language: str | None = None,
    overrides: Overrides | None = None,
) -> Plan:
    """The profile's plan, plus what the engine knows about the inputs."""
    inputs = probed.inputs
    if not profile.external_audio and probed.external_audio:
        probed = replace(probed, external_audio=[])
    if not profile.external_subtitles and probed.external_subs:
        probed = replace(probed, external_subs=[])
    elif profile.track_editor:  # the user sets a missing language there (the profile warns while it's unset)
        probed = replace(probed, issues=[i for i in probed.issues if i.code != "subs.external_name"])
    else:
        probed = replace(probed, external_subs=[t for t in probed.external_subs if t.language != "und"])
    plan = profile.plan(probed, original_language, overrides or Overrides())
    plan.profile = profile.id
    plan.inputs = inputs
    plan.issues[:0] = probed.issues
    if inputs.encode is not None and inputs.encode_state is EncodeState.IN_PROGRESS:
        plan.issues.insert(0, Issue(Severity.BLOCK, "pair.encoding", f"{inputs.encode.name} is still encoding"))
    return plan
