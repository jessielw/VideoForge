"""Fix mode: correct a finished MKV the cheapest way.

Header-only changes (segment title, track names, languages, default / forced /
hearing-impaired flags) are written in place by mkvpropedit, in seconds.
Dropping, reordering or adding tracks (e.g. a replacement SRT) is a remux:
mkvmerge with the existing file as its input, so nothing is re-encoded. The remux
is written next to the file and swapped in only once it is complete. Works on any
MKV, including releases this tool didn't make.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from videoforge.core.config import Tools
from videoforge.core.execute import process
from videoforge.core.execute.process import CancelToken, LogFn
from videoforge.core.jobs import ProbedInputs
from videoforge.core.models import AudioAction, JobInputs, Overrides, SourceInfo
from videoforge.core.probe import mkvmerge_identify

if TYPE_CHECKING:
    from videoforge.core.profile import Profile

Runner = Callable[[Sequence[Sequence[str]], LogFn, CancelToken | None], None]

KINDS = ("video", "audio", "subtitles")


class FixError(ValueError):
    pass


@dataclass(slots=True)
class HeaderTrack:
    """One track's header as fix mode edits it."""

    id: int  # mkvmerge track id; -1 for an added file
    number: int  # MKV track number (mkvpropedit track:@N); 0 for an added file
    kind: str  # "video" | "audio" | "subtitles"
    codec: str
    name: str = ""
    language: str = "und"  # IETF
    default: bool = False
    forced: bool = False
    hearing_impaired: bool = False
    keep: bool = True
    path: Path | None = None  # an added file (a replacement SRT); muxed as its own input

    @property
    def added(self) -> bool:
        return self.path is not None

    @property
    def label(self) -> str:
        return self.path.name if self.path else f"#{self.id} {self.codec}"


@dataclass(slots=True)
class FixState:
    path: Path
    title: str = ""
    tracks: list[HeaderTrack] = field(default_factory=list)  # in output order

    def copy(self) -> FixState:
        return FixState(self.path, self.title, [replace(t) for t in self.tracks])


class FixMethod(StrEnum):
    NONE = "none"  # nothing to change
    IN_PLACE = "in_place"  # mkvpropedit
    REMUX = "remux"  # mkvmerge from the file itself


def read_state(path: Path, mkvmerge: str) -> FixState:
    if path.suffix.lower() != ".mkv":
        raise FixError(f"{path.name}: fix mode handles MKV files only")
    ident = mkvmerge_identify(path, mkvmerge)
    title = ident.get("container", {}).get("properties", {}).get("title") or ""
    tracks = []
    for t in ident.get("tracks", []):
        if t.get("type") not in KINDS:
            continue
        p = t.get("properties", {})
        tracks.append(
            HeaderTrack(
                id=t["id"],
                number=p.get("number") or t["id"] + 1,
                kind=t["type"],
                codec=t.get("codec", ""),
                name=p.get("track_name") or "",
                language=p.get("language_ietf") or p.get("language") or "und",
                default=bool(p.get("default_track")),
                forced=bool(p.get("forced_track")),
                hearing_impaired=bool(p.get("flag_hearing_impaired")),
            )
        )
    return FixState(path, title, tracks)


def method(current: FixState, wanted: FixState) -> FixMethod:
    kept = [t for t in wanted.tracks if t.keep]
    if any(t.added for t in kept) or [t.id for t in kept] != [t.id for t in current.tracks]:
        return FixMethod.REMUX
    return FixMethod.IN_PLACE if propedit_command("mkvpropedit", current, wanted) else FixMethod.NONE


def _flag(on: bool) -> str:
    return "1" if on else "0"


def propedit_command(tool: str, current: FixState, wanted: FixState) -> list[str] | None:
    """mkvpropedit argv for the header changes, or None when there are none.
    Only valid when method() isn't REMUX (same tracks, same order)."""
    edits: list[str] = []
    if wanted.title != current.title:
        edits += ["--edit", "info"] + (["--set", f"title={wanted.title}"] if wanted.title else ["--delete", "title"])
    by_id = {t.id: t for t in current.tracks}
    for w in wanted.tracks:
        c = by_id[w.id]
        sets: list[str] = []
        if w.name != c.name:
            sets += ["--set", f"name={w.name}"] if w.name else ["--delete", "name"]
        if w.language != c.language:
            sets += ["--set", f"language={w.language}"]  # mkvpropedit keeps the legacy element in step
        for prop, a, b in (
            ("flag-default", w.default, c.default),
            ("flag-forced", w.forced, c.forced),
            ("flag-hearing-impaired", w.hearing_impaired, c.hearing_impaired),
        ):
            if a != b:
                sets += ["--set", f"{prop}={_flag(a)}"]
        if sets:
            edits += ["--edit", f"track:@{c.number}", *sets]
    return [tool, str(current.path), *edits] if edits else None


def _track_options(tid: int, t: HeaderTrack) -> list[str]:
    return [
        "--language", f"{tid}:{t.language}",
        "--track-name", f"{tid}:{t.name}",
        "--default-track-flag", f"{tid}:{_flag(t.default)}",
        "--forced-display-flag", f"{tid}:{_flag(t.forced)}",
        "--hearing-impaired-flag", f"{tid}:{_flag(t.hearing_impaired)}",
    ]  # fmt: skip


def remux_command(tool: str, wanted: FixState, output: Path) -> list[str]:
    """mkvmerge argv: the file itself (kept tracks, new headers, chapters and tags as they
    are), then each added file, in the wanted track order."""
    kept = [t for t in wanted.tracks if t.keep]
    if not any(t.kind == "video" for t in kept):
        raise FixError("A release needs its video track")
    own = [t for t in kept if not t.added]
    added = [t for t in kept if t.added]
    argv = [tool, "-o", str(output)]
    argv += ["--title", wanted.title] if wanted.title else []
    for kind, option, none in (
        ("video", "--video-tracks", "--no-video"),
        ("audio", "--audio-tracks", "--no-audio"),
        ("subtitles", "--subtitle-tracks", "--no-subtitles"),
    ):
        ids = [str(t.id) for t in own if t.kind == kind]
        argv += [option, ",".join(ids)] if ids else [none]
    for t in own:
        argv += _track_options(t.id, t)
    argv.append(str(wanted.path))
    file_of: dict[int, int] = {}
    for n, t in enumerate(added, 1):
        file_of[id(t)] = n
        argv += _track_options(0, t)
        argv.append(str(t.path))
    order = [f"{file_of[id(t)]}:0" if t.added else f"0:{t.id}" for t in kept]
    argv += ["--track-order", ",".join(order)]
    return argv


@dataclass(slots=True)
class FixResult:
    method: FixMethod
    path: Path


def apply_fix(
    current: FixState,
    wanted: FixState,
    tools: Tools,
    *,
    log: LogFn | None = None,
    cancel: CancelToken | None = None,
    runner: Runner = process.run,
) -> FixResult:
    """Write wanted over the file. Raises ToolError/Cancelled; the file is untouched
    unless the edit (in place) or the whole remux succeeded."""
    log = log or (lambda _line: None)
    how = method(current, wanted)
    if how is FixMethod.NONE:
        return FixResult(how, current.path)
    if how is FixMethod.IN_PLACE:
        argv = propedit_command(tools.mkvpropedit, current, wanted)
        assert argv is not None
        log("== Edit headers in place (mkvpropedit)")
        runner([argv], log, cancel)
        return FixResult(how, current.path)

    partial = current.path.with_name(current.path.stem + ".fixing.mkv")
    try:
        log("== Remux from the file itself (mkvmerge)")
        runner([remux_command(tools.mkvmerge, wanted, partial)], log, cancel)
        if not partial.is_file():
            raise FixError(f"{partial.name} was not written")
        os.replace(partial, current.path)
    finally:
        partial.unlink(missing_ok=True)
    return FixResult(how, current.path)


def subtitle_track(path: Path, language: str = "und") -> HeaderTrack:
    """An external subtitle file to add in a remux."""
    return HeaderTrack(id=-1, number=0, kind="subtitles", codec=path.suffix.lstrip(".").upper(),
                       name="", language=language, path=path)


def suggest(
    profile: Profile, info: SourceInfo, current: FixState, original_language: str | None = None
) -> tuple[FixState, list[str]]:
    """What the profile would make of this release: plan it as if it were its own source
    and encode, then take the planned names, languages, flags and order. Tracks the plan
    drops are marked not kept. An audio track the plan would re-encode can't be fixed
    from the file alone; it is left as it is and noted."""
    probed = ProbedInputs(JobInputs(current.path, current.path), info, info)
    plan = profile.plan(probed, original_language, Overrides(original_language=original_language))
    notes = [f"{i.severity.value}: {i.message}" for i in plan.issues if i.severity.value != "info"]
    by_id = {t.id: replace(t) for t in current.tracks}
    order: list[HeaderTrack] = [t for t in by_id.values() if t.kind == "video"]
    for a in plan.audio:
        t = by_id.get(a.source.id)
        if t is None:
            continue
        if a.action is not AudioAction.COPY:
            notes.append(f"{t.label}: the profile would encode it ({a.action.value}); fix mode keeps it as it is")
        t.name, t.language, t.default, t.forced = a.title, a.language, a.default, False
        order.append(t)
    for sp in plan.subs:
        t = by_id.get(sp.source.id)
        if t is None:
            continue
        t.name, t.language, t.default = sp.title, sp.language, sp.default
        t.forced, t.hearing_impaired = sp.forced, sp.hearing_impaired
        order.append(t)
    placed = {id(t) for t in order}
    for t in by_id.values():
        if id(t) not in placed:
            t.keep = False
            order.append(t)
    return FixState(current.path, current.title, order), notes


def inspect_release(path: Path, mkvmerge: str) -> tuple[FixState, SourceInfo]:
    """The file's headers for editing, and its probe for the profile's checks."""
    from videoforge.core.probe import probe

    return read_state(path, mkvmerge), probe(path, mkvmerge)
