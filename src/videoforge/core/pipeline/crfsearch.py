"""A CRF search (ab-av1's crf-search, on the test encode's blocks): the sample (pipeline/sample.py) encoded at
several CRFs, each scored against the frames the encoder got (core/video/metrics.py), for the highest CRF whose
score still reaches a target.

    <job>/sample/search/sample.vpy   the job's script on the blocks, shared by the tries
    <job>/sample/search/crf-<n>/     a try: its encode, MKV and scores (sample.py's names)
    <job>/sample/search/search.json  the target, the tries so far and the CRF found (SearchResult)

The first try is the job's CRF. Until one try passes and a higher one fails, the next goes JUMP further (up after
a pass, down after a failure) within the encoder's range; between a pass and the failure above it, the CRF where a
straight line through their scores meets the target, kept off both. It ends when they are one CRF apart, at either
end of the range, or after MAX_TRIES; the answer is the highest pass. Every try's steps have records of their own,
so the same search again, or one for another target, reuses the CRFs it already encoded.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field, fields, replace
from datetime import datetime
from enum import StrEnum
from fractions import Fraction
import json
import math
from pathlib import Path
import time

from videoforge.core.config import AppConfig
from videoforge.core.execute.mux import frame_rate
from videoforge.core.job import JobSpec, StepRecord
from videoforge.core.models import Plan
from videoforge.core.pipeline import sample
from videoforge.core.pipeline.steps import Step
from videoforge.core.video import info, metrics
from videoforge.core.video.encoders import SVTAV1_CRF, output_name
from videoforge.core.video.settings import Encoder, RateControl

SEARCH_DIR = "search"  # in the test encode's folder
RESULT = "search.json"
MAX_TRIES = 8
# Each encoder's CRF range: x264 / x265's, libvpx's (VP8 from 4), SvtAv1EncApp's
CRF_RANGE: dict[Encoder, tuple[int, int]] = {
    Encoder.X264: (0, 51),
    Encoder.X265: (0, 51),
    Encoder.VP8: (4, 63),
    Encoder.VP9: (0, 63),
    Encoder.SVTAV1: SVTAV1_CRF,
}
_REPLACE_WAITS = (0.02, 0.05, 0.1, 0.2, 0.5, None)  # seconds, then give up
JUMP: dict[Encoder, int] = {Encoder.X264: 4, Encoder.X265: 4}  # the others' (a longer range): 6


class Metric(StrEnum):
    SSIMULACRA2 = "ssimulacra2"  # the frames' mean
    SSIMULACRA2_P5 = "ssimulacra2_p5"  # the worst 5%
    XPSNR = "xpsnr"  # luma, dB

    @property
    def label(self) -> str:
        return {"ssimulacra2": "SSIMULACRA2", "ssimulacra2_p5": "SSIMULACRA2 (worst 5%)"}.get(self.value, "XPSNR")


@dataclass(frozen=True, slots=True)
class Target:
    metric: Metric
    value: float

    def __str__(self) -> str:
        return f"{self.metric.label} {self.value:g}" + (" dB" if self.metric is Metric.XPSNR else "")


@dataclass(frozen=True, slots=True)
class Try:
    crf: int
    bytes: int  # the encoded stream's
    seconds: float  # the encode took
    kbps: float | None
    estimate_mb: float | None  # the whole video's at kbps (sample.SampleResult.estimate_mb)
    ssimulacra2: float
    ssimulacra2_p5: float
    xpsnr: float | None

    def score(self, metric: Metric) -> float | None:
        value = getattr(self, metric.value)
        return float(value) if value is not None else None


def passes(t: Try, target: Target) -> bool:
    score = t.score(target.metric)
    return score is not None and score >= target.value


def crf_range(encoder: Encoder) -> tuple[int, int]:
    return CRF_RANGE[encoder]


def next_crf(tries: Sequence[Try], target: Target, start: float, encoder: Encoder) -> int | None:
    """The CRF to try next, or None once the search is over (see the module's doc)."""
    lo, hi = crf_range(encoder)
    if len(tries) >= MAX_TRIES:
        return None
    if not tries:
        return min(hi, max(lo, round(start)))
    best = max((t for t in tries if passes(t, target)), key=lambda t: t.crf, default=None)
    above = [t for t in tries if not passes(t, target) and (best is None or t.crf > best.crf)]
    fail = min(above, key=lambda t: t.crf, default=None)
    jump = JUMP.get(encoder, 6)
    if best is None:  # nothing passes yet: lower
        lowest = min(t.crf for t in tries)
        return max(lo, lowest - jump) if lowest > lo else None
    if fail is None:  # nothing above the best fails yet: higher
        return min(hi, best.crf + jump) if best.crf < hi else None
    if fail.crf - best.crf <= 1:
        return None
    good, bad = best.score(target.metric) or 0.0, fail.score(target.metric)  # a pass has a score
    if bad is None:  # a failure without a score can't be interpolated: halve
        return (best.crf + fail.crf) // 2
    at = best.crf + (good - target.value) / (good - bad) * (fail.crf - best.crf)
    return min(fail.crf - 1, max(best.crf + 1, math.floor(at)))


def answer(tries: Sequence[Try], target: Target) -> int | None:
    """The highest CRF that passed; None when none did."""
    return max((t.crf for t in tries if passes(t, target)), default=None)


def search_dir(spec: JobSpec) -> Path:
    return sample.sample_dir(spec) / SEARCH_DIR


def try_place(spec: JobSpec, crf: int) -> sample.Place:
    home = search_dir(spec)
    return sample.Place(home / f"crf-{crf}", home / sample.SCRIPT, "search.script", f"search.crf{crf}")


def try_spec(spec: JobSpec, crf: int) -> JobSpec:
    return replace(spec, encoder=replace(spec.encoder, crf=float(crf)))


def search_key(spec: JobSpec, plan: Plan) -> str:
    """What a search depends on besides its target and percent: sample_key with the CRF left out (applying the
    CRF it found keeps it current)."""
    return sample.sample_key(try_spec(spec, 0), plan)


def check(spec: JobSpec) -> None:
    """ValueError when the job can't be searched: it reuses an encode, or doesn't encode at a CRF."""
    if not spec.encodes_video:
        raise ValueError("The job reuses an encode: there's no CRF to search")
    if spec.encoder.rate_control is not RateControl.CRF:
        raise ValueError("A CRF search needs the encoder's rate control at CRF")


def try_steps(spec: JobSpec, plan: Plan, app: AppConfig, container: str, percent: int, crf: int) -> list[Step]:
    """A try's script (shared), encode, MKV and scores; the script info step (sample.prepare_steps) has run."""
    return sample.sample_steps(try_spec(spec, crf), plan, app, container, percent, True, try_place(spec, crf))


@dataclass(slots=True)
class SearchResult:
    percent: int
    metric: Metric
    target: float
    start: float  # the job's CRF when it began
    encoder: str  # Encoder.label
    frames: int  # the sample's
    total_frames: int  # the script's
    key: str  # search_key() when it began
    started: str  # ISO time
    tries: list[Try] = field(default_factory=list)
    done: bool = False  # False while it runs (or after a failure: the tries so far)
    crf: int | None = None  # answer(), once done
    exact: bool = False  # the CRF above it was tried and failed (not the range's end or MAX_TRIES)

    @property
    def goal(self) -> Target:
        return Target(self.metric, self.target)

    def to_json(self) -> dict:
        return asdict(self)


def _write(spec: JobSpec, result: SearchResult) -> None:
    home = search_dir(spec)
    home.mkdir(parents=True, exist_ok=True)
    partial = home / f"{RESULT}.partial"
    partial.write_text(json.dumps(result.to_json(), indent=2), encoding="utf-8")
    for wait in _REPLACE_WAITS:  # Windows refuses while a job view reads the last one
        try:
            partial.replace(home / RESULT)
            return
        except PermissionError:
            if wait is None:
                raise
            time.sleep(wait)


def _read_try(
    spec: JobSpec, crf: int, sel_frames: int, total: int, fps: Fraction | None, records: dict[str, StepRecord]
) -> Try:
    where = try_place(spec, crf)
    scores = metrics.read(where.home / sample.QUALITY)
    if scores is None:
        raise ValueError(f"CRF {crf}: its quality scores weren't written")
    out = where.home / output_name(try_spec(spec, crf).encoder)
    size = out.stat().st_size
    record = records.get(f"{where.prefix}.video")
    kbps = size * 8 / 1000 / (sel_frames / fps) if fps and sel_frames else None
    return Try(
        crf=crf,
        bytes=size,
        seconds=record.seconds if record else 0.0,
        kbps=kbps,
        estimate_mb=kbps * (total / fps) / 8 / 1000 if kbps is not None and fps else None,
        ssimulacra2=scores.ssimulacra2,
        ssimulacra2_p5=scores.ssimulacra2_p5,
        xpsnr=scores.xpsnr,
    )


def search(
    spec: JobSpec,
    plan: Plan,
    app: AppConfig,
    container: str,
    percent: int,
    target: Target,
    records: dict[str, StepRecord],
    run: Callable[[list[Step], int], None],
    log: Callable[[str], None],
) -> SearchResult:
    """The search, its tries run by run(steps, try number) (their records go to records); the script info step
    (sample.prepare_steps) has run. search.json is written after every try, and once done."""
    check(spec)
    found = info.read(spec.job_dir / info.SCRIPT_INFO)
    if found is None:
        raise ValueError("The script's frames aren't known: its info step hasn't run")
    v = plan.source.video
    source_fps = frame_rate(v.default_duration_ns) if v is not None and v.default_duration_ns else None
    sel = sample.selection(found, percent, source_fps)
    fps = found.fps or source_fps
    result = SearchResult(
        percent=percent,
        metric=target.metric,
        target=target.value,
        start=spec.encoder.crf,
        encoder=spec.encoder.encoder.label,
        frames=sel.frames(found.frames),
        total_frames=found.frames,
        key=search_key(spec, plan),
        started=datetime.now().isoformat(timespec="seconds"),
    )
    _write(spec, result)
    while (crf := next_crf(result.tries, target, spec.encoder.crf, spec.encoder.encoder)) is not None:
        try_place(spec, crf).home.mkdir(parents=True, exist_ok=True)  # the shared script step made only the first
        run(try_steps(spec, plan, app, container, percent, crf), len(result.tries))
        t = _read_try(spec, crf, result.frames, found.frames, fps, records)
        if t.score(target.metric) is None:
            raise ValueError(f"{target.metric.label} can't be measured on this script (it needs YUV, even size)")
        result.tries.append(t)
        rate = f"{t.kbps:.0f} kb/s" if t.kbps is not None else "no bitrate"
        verdict = "reaches" if passes(t, target) else "is below"
        log(f"CRF search: CRF {crf}, {rate}, {target.metric.label} {t.score(target.metric):.2f} {verdict} {target}")
        _write(spec, result)
    result.crf = answer(result.tries, target)
    result.exact = result.crf is not None and any(
        t.crf == result.crf + 1 and not passes(t, target) for t in result.tries
    )
    result.done = True
    _write(spec, result)
    return result


def read_result(spec: JobSpec) -> SearchResult | None:
    """The job's last search (or the one running), None without one or one that can't be read."""
    try:
        data = json.loads((search_dir(spec) / RESULT).read_text(encoding="utf-8"))
        known = {f.name for f in fields(Try)}
        tries = [Try(**{k: t[k] for k in known}) for t in data.get("tries", [])]
        names = {f.name for f in fields(SearchResult)} - {"tries", "metric"}
        rest = {k: data[k] for k in names if k in data}
        return SearchResult(metric=Metric(data["metric"]), tries=tries, **rest)
    except (OSError, ValueError, KeyError, TypeError):
        return None
