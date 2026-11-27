"""The field scan: what a source's fields hold (progressive, telecined film, interlaced video or a mix), from one
pass over every frame, and the filter chain that fits. Written as JSON; run out of the server process (the server
never imports VapourSynth):

    python -m videoforge.core.video.fieldscan <source.vpy> <out.json>

The script leaves the source in `clip` as decoded (build_script's "source" stage), with pulldown applied when the
stream has flags (VideoInfo.pulldown): soft-telecined parts then come out as a player shows them, and a scan of
the stored frames would call them progressive.

Per frame, from VIVTC's VFM at each field order (the frames tagged with it, since the source filter's _FieldBased
beats VFM's own order argument):
- moving: its luma differs from the last frame's by more than _MOVING. The ratios below count moving frames only:
  a still frame looks clean whatever its fields hold.
- combed as decoded: VFM's mic for the frame as it is (its "c" match) over VFM's mi, where either order computed
  it; where neither did, both matched other fields (VFM only scores the matches it weighs, and micout=1, which
  scores all five, halves the scan's speed). On moving frames that agrees with micout's answer on all but one of
  13,280 frames of a DVD episode.
- left combed: VFM's _Combed after matching fields. Telecine leaves next to none at the right order; video stays
  combed at both. Still frames count here too: a fading credit over a still shot combs without moving the frame.
And over all of them: the 3:2 cadence (telecine combs the same 2 of every 5 frames, per section, since an edit
shifts it), which tells film (IVTC decimates it) from progressive video with its fields one off (nothing to
drop). For video, the order is Bwdif's: bobbed at the wrong order, the picture jitters up and down (a short second
pass over the windows with the most combing).

The verdict's chain sets the field order it found first (_FieldBased), so it holds even when the stream's flag is
wrong (stream_order says what that was).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from enum import StrEnum
import json
import os
from pathlib import Path
import sys
import time
from typing import TYPE_CHECKING, Any, TextIO

if TYPE_CHECKING:
    import vapoursynth as vs

VERSION = 1  # the report's layout

_MOVING = 0.004  # luma PlaneStatsDiff against the last frame
_MI = 80  # VFM's default mi: a match whose mic is above it is combed
_PROGRESSIVE = 0.03  # combed as decoded, of the moving frames: under it, nothing to do
_TELECINE = 0.04  # left combed after matching, of the moving frames: under it, field matching does it all
_INTERLACED = 0.25  # left combed after matching: over it, video
_CADENCE = 0.9  # the share of combed frames on 2 of every 5 positions: telecine's 3:2
_CADENCE_SECTION = 600  # frames: the cadence is counted per section, since an edit shifts it
_CADENCE_FRAMES = 50  # combed frames: fewer, and the cadence can't be told
_MIN_MOVING = 30  # moving frames: fewer, and nothing can be told
_CHUNK = 30  # frames per strip character
_CHUNK_MOVING = 5  # moving frames a chunk needs for a verdict
_STRETCH_GAP = 30  # frames left combed closer than this make one stretch
_MAX_STRETCHES = 500
_BOB_WINDOW = 60  # frames per Bwdif window
_BOB_WINDOWS = 10
_BOB_CLEAR = 0.05  # jitter ratios within 1 +- this don't say which order


class Verdict(StrEnum):
    PROGRESSIVE = "progressive"  # no combing (or stored as interlaced, PsF): nothing to do
    TELECINE = "telecine"  # film in 3:2 pulldown: IVTC (VFM + VDecimate)
    SHIFTED = "shifted"  # progressive with its fields matched one off (no 3:2): VFM, nothing dropped
    HYBRID = "hybrid"  # telecine with parts field matching can't fix: IVTC with a deinterlacer on those frames
    INTERLACED = "interlaced"  # video, each field its own moment: deinterlace
    UNKNOWN = "unknown"  # too little motion to tell

    @property
    def label(self) -> str:
        return _LABELS[self]


_LABELS = {
    Verdict.PROGRESSIVE: "Progressive",
    Verdict.TELECINE: "Telecined film",
    Verdict.SHIFTED: "Progressive, fields shifted",
    Verdict.HYBRID: "Telecined film with combed parts",
    Verdict.INTERLACED: "Interlaced video",
    Verdict.UNKNOWN: "Too little motion to tell",
}
_ORDERS = {"tff": 2, "bff": 1}  # _FieldBased
_STREAM = {0: "progressive", 1: "bff", 2: "tff"}


@dataclass(frozen=True, slots=True)
class FieldScan:
    verdict: Verdict
    order: str  # the content's: "tff", "bff"; "" when there is nothing to match
    stream_order: str  # the source's _FieldBased: "tff", "bff", "progressive"; "" when it sets none
    frames: int
    fps_num: int
    fps_den: int
    moving: int  # frames with motion
    combed: int  # moving frames combed as decoded
    left_tff: int  # moving frames VFM leaves combed at each order
    left_bff: int
    fallback: int  # frames (moving or not) VFM leaves combed at `order`: the hybrid chain's deinterlacer gets them
    cadence: float | None  # 3:2: the share of combed frames on 2 of every 5 positions (None: too few)
    jitter: float | None  # Bwdif's frame-to-frame difference at BFF over TFF (>1: TFF; None: not run)
    strip: str  # one character per _CHUNK frames, see STRIP_LEGEND
    stretches: list[tuple[int, int, int]] = field(default_factory=list)  # (first, last, frames) left combed
    seconds: float = 0.0
    chunk: int = _CHUNK
    version: int = VERSION

    @property
    def mismatch(self) -> bool:
        """The stream's field order isn't the content's (the chain's SetFieldBased overrides it)."""
        return bool(self.order) and self.stream_order in _ORDERS and self.stream_order != self.order

    @property
    def chain(self) -> str:
        return chain(self.verdict, self.order)


STRIP_LEGEND = {
    ".": "too little motion",
    "P": "progressive",
    "T": "telecine, field matching fixes it",
    "h": "partly combed after field matching",
    "I": "combed after field matching (video)",
}


_TAG_NOTE = "# the field order the scan found: 2 top first, 1 bottom first"


def chain(verdict: Verdict, order: str) -> str:
    """The script lines (on `clip`) for a verdict at a field order; "" when there's nothing to do."""
    if verdict in (Verdict.PROGRESSIVE, Verdict.UNKNOWN) or order not in _ORDERS:
        return ""
    tff = int(order == "tff")
    tag = f"clip = core.std.SetFieldBased(clip, {_ORDERS[order]})  {_TAG_NOTE}"
    if verdict is Verdict.INTERLACED:
        return f"{tag}\nclip = core.bwdif.Bwdif(clip, field={tff})"
    lines = [tag, f"clip = core.vivtc.VFM(clip, order={tff})"]
    if verdict is Verdict.HYBRID:
        # VFM's clip2 would give its fields to every frame: the deinterlaced frame replaces only the combed ones.
        lines = [
            "import havsfunc",
            tag,
            f"fallback = havsfunc.QTGMC(clip, TFF={tff == 1}, Preset='Fast', FPSDivisor=2)",
            lines[1],
            "clip = core.std.FrameEval(clip, lambda n, f, matched=clip: fallback if f.props['_Combed'] else matched, "
            "prop_src=clip)  # the frames field matching leaves combed",
        ]
    if verdict is not Verdict.SHIFTED:
        lines.append("clip = core.vivtc.VDecimate(clip)")
    return "\n".join(lines)


def _core() -> Any:
    """vs.core, whose plugins (std, vivtc, bwdif) aren't in the stubs."""
    import vapoursynth as vs

    return vs.core


def _eight_bit(clip: vs.VideoNode) -> vs.VideoNode:
    """VFM reads 8-bit frames: a deeper clip is scanned at 8 bits."""
    import vapoursynth as vs

    f = clip.format
    if f.sample_type == vs.INTEGER and f.bits_per_sample == 8:
        return clip
    return _core().resize.Point(clip, format=f.replace(sample_type=vs.INTEGER, bits_per_sample=8))


@dataclass(slots=True)
class _Frames:
    moving: list[bool] = field(default_factory=list)
    combed: list[bool] = field(default_factory=list)  # as decoded
    left: dict[str, list[bool]] = field(default_factory=lambda: {"tff": [], "bff": []})


class _Progress:
    def __init__(self, out: TextIO, total: int) -> None:
        self.out, self.total, self.last = out, max(total, 1), -1

    def at(self, done: int) -> None:
        pct = min(100, done * 100 // self.total)
        if pct != self.last:
            self.last = pct
            self.out.write(f"Progress: {pct}%\n")
            self.out.flush()


def _measure(clip: vs.VideoNode, progress: _Progress) -> _Frames:
    core = _core()
    motion = core.std.PlaneStats(clip, clip[0] + clip[:-1], plane=0)
    nodes = [motion] + [
        core.vivtc.VFM(core.std.SetFieldBased(clip, _ORDERS[order]), order=int(order == "tff")) for order in _ORDERS
    ]
    got = _Frames()
    for n, (m, tff, bff) in enumerate(zip(*(node.frames(close=True) for node in nodes), strict=True)):
        got.moving.append(float(m.props["PlaneStatsDiff"]) > _MOVING)  # pyright: ignore[reportArgumentType]
        # The c match's mic, -1 where that order's VFM didn't weigh it
        scored = [int(f.props["VFMMics"][1]) for f in (tff, bff)]  # pyright: ignore[reportIndexIssue, reportArgumentType]
        known = [mic for mic in scored if mic >= 0]
        got.combed.append(any(mic > _MI for mic in known) if known else True)
        got.left["tff"].append(bool(tff.props["_Combed"]))
        got.left["bff"].append(bool(bff.props["_Combed"]))
        progress.at(n + 1)
    return got


def _cadence(got: _Frames) -> float | None:
    """The share of combed moving frames on the 2 most combed of every 5 positions, per section."""
    top = total = 0
    for start in range(0, len(got.moving), _CADENCE_SECTION):
        end = start + _CADENCE_SECTION
        positions = Counter(i % 5 for i in range(start, min(end, len(got.moving))) if got.moving[i] and got.combed[i])
        top += sum(n for _, n in positions.most_common(2))
        total += sum(positions.values())
    return top / total if total >= _CADENCE_FRAMES else None


def _chunk(got: _Frames, order: str, start: int) -> str:
    end = min(start + _CHUNK, len(got.moving))
    moving = [i for i in range(start, end) if got.moving[i]]
    if len(moving) < _CHUNK_MOVING:
        return "."
    combed = sum(got.combed[i] for i in moving) / len(moving)
    left = sum(got.left[order][i] for i in moving) / len(moving)
    if combed < _PROGRESSIVE:
        return "P"
    if left < _TELECINE:
        return "T"
    return "I" if left > _INTERLACED else "h"


def _stretches(left: list[bool]) -> list[tuple[int, int, int]]:
    out: list[list[int]] = []
    for i, combed in enumerate(left):
        if not combed:
            continue
        if out and i - out[-1][1] <= _STRETCH_GAP:
            out[-1][1] = i
            out[-1][2] += 1
        else:
            out.append([i, i, 1])
    return [(a, b, n) for a, b, n in out[:_MAX_STRETCHES]]


def _jitter(clip: vs.VideoNode, got: _Frames) -> float | None:
    """Bwdif bobbed at BFF over TFF, its mean frame-to-frame difference over the windows with the most combing:
    the wrong order jitters more (over 1: top field first)."""
    core = _core()
    n = len(got.moving)
    windows = sorted(
        range(0, max(n - _BOB_WINDOW, 0) + 1, _BOB_WINDOW),
        key=lambda s: -sum(got.left["tff"][i] or got.left["bff"][i] for i in range(s, min(s + _BOB_WINDOW, n))),
    )[:_BOB_WINDOWS]
    sums = {}
    for order, fieldarg in (("tff", 3), ("bff", 2)):  # double rate
        total = 0.0
        for start in sorted(windows):
            part = core.std.SetFieldBased(clip[start : min(start + _BOB_WINDOW, n)], _ORDERS[order])
            bob = core.bwdif.Bwdif(part, field=fieldarg)
            diff = core.std.PlaneStats(bob[:-1], bob[1:], plane=0)
            total += sum(float(f.props["PlaneStatsDiff"]) for f in diff.frames(close=True))  # pyright: ignore[reportArgumentType]
        sums[order] = total
    return sums["bff"] / sums["tff"] if sums["tff"] > 0 else None


def classify(got: _Frames) -> tuple[Verdict, str, float | None, str]:
    """The verdict, the field-matching order (fewer frames left combed; TFF on a tie), the cadence, and the strip."""
    moving = [i for i, m in enumerate(got.moving) if m]
    order = "bff" if sum(got.left["bff"][i] for i in moving) < sum(got.left["tff"][i] for i in moving) else "tff"
    cadence = _cadence(got)
    strip = "".join(_chunk(got, order, s) for s in range(0, len(got.moving), _CHUNK))
    if len(moving) < _MIN_MOVING:
        return Verdict.UNKNOWN, "", cadence, strip
    combed = sum(got.combed[i] for i in moving) / len(moving)
    left = sum(got.left[order][i] for i in moving) / len(moving)
    if combed < _PROGRESSIVE:
        return Verdict.PROGRESSIVE, "", cadence, strip
    if left < _TELECINE:
        if cadence is not None and cadence < _CADENCE:
            return Verdict.SHIFTED, order, cadence, strip
        return Verdict.TELECINE, order, cadence, strip
    if left > _INTERLACED:
        return Verdict.INTERLACED, order, cadence, strip
    return Verdict.HYBRID, order, cadence, strip


def scan(clip: vs.VideoNode, out: TextIO = sys.stdout) -> FieldScan:
    """Every frame of clip, printing "Progress: N%" lines."""
    if clip.format is None or not clip.width or not clip.height:
        raise RuntimeError("The source changes size or format between frames")
    if clip.num_frames < 2:
        raise RuntimeError("The source has fewer than 2 frames")
    start = time.perf_counter()
    stream = clip.get_frame(0).props.get("_FieldBased")
    clip = _eight_bit(clip)
    got = _measure(clip, _Progress(out, clip.num_frames))
    verdict, order, cadence, strip = classify(got)
    jitter = None
    if verdict in (Verdict.INTERLACED, Verdict.HYBRID):
        jitter = _jitter(clip, got)
        if verdict is Verdict.INTERLACED and jitter is not None and abs(jitter - 1) > _BOB_CLEAR:
            order = "tff" if jitter > 1 else "bff"
    moving = [i for i, m in enumerate(got.moving) if m]
    left = got.left[order or "tff"]
    return FieldScan(
        verdict=verdict,
        order=order,
        stream_order=_STREAM.get(stream, "") if isinstance(stream, int) else "",
        frames=clip.num_frames,
        fps_num=clip.fps.numerator,
        fps_den=clip.fps.denominator,
        moving=len(moving),
        combed=sum(got.combed[i] for i in moving),
        left_tff=sum(got.left["tff"][i] for i in moving),
        left_bff=sum(got.left["bff"][i] for i in moving),
        fallback=sum(left) if order else 0,
        cadence=cadence,
        jitter=jitter,
        strip=strip,
        stretches=_stretches(left) if order else [],
        seconds=round(time.perf_counter() - start, 1),
    )


def to_json(result: FieldScan) -> str:
    return json.dumps(asdict(result), indent=2)


def read(path: Path) -> FieldScan | None:
    """The report a field scan wrote; None when it isn't there, can't be read, or has another layout."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") != VERSION:
            return None
        data["verdict"] = Verdict(data["verdict"])
        data["stretches"] = [tuple(s) for s in data["stretches"]]
        return FieldScan(**data)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def summary(result: FieldScan) -> str:
    order = {"tff": "top field first", "bff": "bottom field first"}.get(result.order, "")
    text = result.verdict.label + (f", {order}" if order else "")
    if result.fallback and result.verdict is Verdict.HYBRID:
        text += f" ({result.fallback} frames left combed)"
    if result.mismatch:
        text += f"; the stream says {result.stream_order.upper()}"
    return text


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("usage: python -m videoforge.core.video.fieldscan <source.vpy> <out.json>")
    from videoforge.core.video.vs import load_clip

    script, result = Path(sys.argv[1]), Path(sys.argv[2])
    try:
        report = scan(load_clip(script.read_text(encoding="utf-8")))
        partial = result.with_name(result.name + ".partial")
        partial.write_text(to_json(report), encoding="utf-8")
        os.replace(partial, result)
    except Exception as e:  # the message is the step's error
        print(e, file=sys.stderr)
        sys.exit(1)
    print(f"{summary(report)} ({report.seconds:.0f} s)")


if __name__ == "__main__":
    main()
