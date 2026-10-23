"""Finished files a job's next run could reuse, by section (the video, each audio encode), StaxRip-like.

A section is offered when its file is there and finished: by the job's own step record, by its folder's
finished-steps.json (a rerun, a re-added job), or by another job's folder on the source with today's settings
(pipeline/share.py: a run would link it). `current` says it was made with today's settings; one that isn't is
offered too, and the user decides (run_steps' keep and redo). The index, script, chapters and mux aren't asked
about.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from videoforge.core.config import AppConfig
from videoforge.core.job import JobSpec, StepRecord
from videoforge.core.models import Plan
from videoforge.core.pipeline.build import build_steps, output_path
from videoforge.core.pipeline.share import Sharing
from videoforge.core.pipeline.steps import Step
from videoforge.core.workdir import finished_files

if TYPE_CHECKING:
    from videoforge.core.profile import Profile


@dataclass(frozen=True, slots=True)
class ReuseOffer:
    id: str  # "video", "audio.2"
    label: str
    steps: tuple[str, ...]  # the step ids it covers (both passes of a 2-pass video)
    file: Path
    size: int
    seconds: float  # how long it took to make (0 when unknown)
    finished: float | None  # when (epoch seconds); None when only the job's record says so
    current: bool  # made with today's settings (a run would reuse it anyway)
    origin: str = ""  # another job's folder it's in (a run links it from there); "" for the job's own


def _sections(steps: list[Step]) -> list[tuple[str, str, list[Step]]]:
    video = [s for s in steps if s.id == "video" or s.id.startswith("video.")]
    found = []
    if video:
        found.append(("video", video[-1].label.replace("Video pass 2/2", "Video"), video))
    for s in steps:
        if s.id.startswith("audio."):
            found.append((s.id, s.label.replace("Encode audio", "Audio"), [s]))
    return found


def reuse_offers(
    spec: JobSpec, plan: Plan, profile: Profile, app: AppConfig, records: dict[str, StepRecord]
) -> list[ReuseOffer]:
    """The sections whose finished files a run of the job could reuse, in step order."""
    if spec.output_dir is None or plan.blocked or plan.source.path is None:
        return []
    built = build_steps(spec, plan, profile, app, output_path(spec, plan, profile, spec.output_dir))
    home = spec.job_dir
    finished = finished_files(home)
    share = Sharing(spec.work_dir, home, tuple(built.steps))
    offers = []
    for sid, label, steps in _sections(built.steps):
        last = steps[-1]
        if not last.outputs:
            continue
        file, origin = last.outputs[0], ""
        record = records.get(last.id)
        own = record is not None and record.outputs_match(list(last.outputs))
        noted = finished.get(file.name) if file.parent == home else None
        # Another job's, made as this one would make it (a run links it, and a 2-pass video's pass 1 with it).
        if not own and noted is None:
            found = share.find(last)
            if found is not None and found.folder != home:
                file, origin, noted = found.folder / file.name, found.folder.name, found.notes[file.name]
        if not own and noted is None:
            continue
        try:
            size = file.stat().st_size
        except OSError:
            continue
        fingerprint = last.fingerprint()
        current = (
            bool(origin)
            or (own and record is not None and record.fingerprint == fingerprint)
            or (noted is not None and noted.fingerprint == fingerprint)
        )
        seconds = sum(r.seconds for s in steps if (r := records.get(s.id)) is not None) if own else 0.0
        offers.append(
            ReuseOffer(
                sid,
                label,
                tuple(s.id for s in steps),
                file,
                size,
                seconds or (noted.seconds if noted else 0.0),
                noted.at if noted else None,
                bool(current),
                origin,
            )
        )
    return offers
