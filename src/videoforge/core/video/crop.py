"""Auto-crop: find the black borders, the way StaxRip does (from the user's video-forge app).

Per sampled frame, 21 evenly spaced columns are scanned from the top and the
bottom, and 21 rows from each side, for pixels darker than a lightness threshold
(HSL L = (max + min) / 2 of RGB). A side's crop is the smallest run over all samples
and frames, so one bright frame is enough to keep picture, and a fade to black can't
over-crop. Values round down to the chroma mod.

YUV frames are read as they are: only the sampled lines are turned into RGB (with the
frame's matrix and range, chroma from the nearest sample), so no full-frame conversion
(about 8x quicker at 1080p). Luma alone isn't enough: it reads dark navy or red picture
as black. Other formats go through a full RGB conversion.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

import numpy as np

from videoforge.core.video.settings import Crop

if TYPE_CHECKING:
    import vapoursynth as vs

THRESHOLD = 0.06
_POSITIONS = 21
# Kr, Kb per matrix (the _Matrix frame property): BT.709, FCC, BT.601 (470BG, 170M), SMPTE 240M, BT.2020
_KR_KB = {
    1: (0.2126, 0.0722),
    4: (0.30, 0.11),
    5: (0.299, 0.114),
    6: (0.299, 0.114),
    7: (0.212, 0.087),
    9: (0.2627, 0.0593),
    10: (0.2627, 0.0593),
}


def _run(dark: np.ndarray) -> np.ndarray:
    """Per column of a boolean (rows, cols) array: how many leading rows are dark."""
    bright = ~dark
    first = bright.argmax(axis=0)
    return np.where(bright.any(axis=0), first, dark.shape[0])


def _lines(h: int, w: int) -> tuple[list[int], list[int]]:
    """The sampled columns (xs) and rows (ys)."""
    return [int(w * i / _POSITIONS) for i in range(_POSITIONS)], [int(h * i / _POSITIONS) for i in range(_POSITIONS)]


def _borders(cols: np.ndarray, rows: np.ndarray, h: int, w: int) -> Crop:
    """From the darkness of the sampled columns (h, n) and rows (w, n), each side limited to a quarter."""
    qh, qw = max(1, h // 4), max(1, w // 4)
    return Crop(
        left=int(_run(rows[:qw]).min()),
        top=int(_run(cols[:qh]).min()),
        right=int(_run(rows[::-1][:qw]).min()),
        bottom=int(_run(cols[::-1][:qh]).min()),
    )


def frame_borders(rgb: np.ndarray, threshold: float = THRESHOLD) -> Crop:
    """The black border of one (H, W, 3) uint8 RGB frame."""
    h, w = rgb.shape[:2]
    xs, ys = _lines(h, w)

    def dark(px: np.ndarray) -> np.ndarray:
        return (px.max(axis=-1).astype(np.uint16) + px.min(axis=-1)) / 510.0 < threshold

    return _borders(dark(rgb[:, xs]), dark(rgb[ys, :]).T, h, w)  # rows.T: one column per sampled row


def yuv_borders(
    y: np.ndarray,
    u: np.ndarray,
    v: np.ndarray,
    *,
    bits: int = 8,
    matrix: int = 1,
    full_range: bool = False,
    threshold: float = THRESHOLD,
) -> Crop:
    """The black border of one YUV frame given as its planes (chroma may be subsampled), judged by the
    same RGB lightness as frame_borders on just the sampled lines."""
    h, w = y.shape
    xs, ys = _lines(h, w)
    sx, sy = w // u.shape[1], h // u.shape[0]
    kr, kb = _KR_KB.get(matrix, _KR_KB[1])
    peak = (1 << bits) - 1
    if full_range:
        y_off, y_scale, c_scale = 0.0, peak, peak
    else:
        y_off, y_scale, c_scale = 16 << (bits - 8), 219 << (bits - 8), 224 << (bits - 8)
    c_off = 1 << (bits - 1)

    def dark(yy: np.ndarray, uu: np.ndarray, vv: np.ndarray) -> np.ndarray:
        yy = (yy.astype(np.float32) - y_off) / y_scale
        cb = (uu.astype(np.float32) - c_off) / c_scale
        cr = (vv.astype(np.float32) - c_off) / c_scale
        r = yy + 2 * (1 - kr) * cr
        b = yy + 2 * (1 - kb) * cb
        g = (yy - kr * r - kb * b) / (1 - kr - kb)
        rgb = np.clip(np.stack([r, g, b], axis=-1), 0.0, 1.0)
        return (rgb.max(axis=-1) + rgb.min(axis=-1)) / 2 < threshold

    cx, ry = [x // sx for x in xs], [r // sy for r in ys]
    rows_of = np.arange(h) // sy  # the chroma row (column, below) each luma row (column) takes
    cols_of = np.arange(w) // sx
    cols = dark(y[:, xs], u[np.ix_(rows_of, cx)], v[np.ix_(rows_of, cx)])
    rows = dark(y[ys, :], u[np.ix_(ry, cols_of)], v[np.ix_(ry, cols_of)])
    return _borders(cols, rows.T, h, w)


def combine(crops: Iterable[Crop], mod: int = 2) -> Crop:
    """The smallest crop per side over all frames, rounded down to mod."""
    crops = list(crops)
    if not crops:
        return Crop()

    def side(name: str) -> int:
        v = min(getattr(c, name) for c in crops)
        return v - v % mod

    return Crop(side("left"), side("top"), side("right"), side("bottom"))


def sample_frames(total: int, count: int = 20) -> list[int]:
    """Frames spread over the clip, skipping the first and last 5% (logos, credits)."""
    if total <= 0:
        return []
    count = max(1, min(count, total))
    start, end = int(total * 0.05), max(int(total * 0.95), 1)
    if end - start < count:
        start, end = 0, total
    step = (end - start) / count
    return sorted({min(total - 1, int(start + step * (i + 0.5))) for i in range(count)})


def _frame_crop(clip: vs.VideoNode, n: int, threshold: float) -> Crop:
    import vapoursynth as vs

    from videoforge.core.video.vs import frame_rgb, matrix

    fmt = clip.format
    if fmt is None or fmt.color_family is not vs.YUV or fmt.sample_type is not vs.INTEGER:
        return frame_borders(frame_rgb(clip, n), threshold)
    f = clip.get_frame(max(0, min(n, clip.num_frames - 1)))
    # _Range (older VapourSynth: _ColorRange); compare with the enum, whose values changed in R6x
    rng = f.props["_Range"] if "_Range" in f.props else f.props.get("_ColorRange")
    full = rng is not None and int(rng) == int(vs.RANGE_FULL)  # unset: limited, like nearly all video
    return yuv_borders(
        np.asarray(f[0]),
        np.asarray(f[1]),
        np.asarray(f[2]),
        bits=fmt.bits_per_sample,
        matrix=matrix(f.props, clip.height),
        full_range=full,
        threshold=threshold,
    )


def detect(clip: vs.VideoNode, samples: int = 20, threshold: float = THRESHOLD, mod: int = 2) -> Crop:
    return combine((_frame_crop(clip, n, threshold) for n in sample_frames(clip.num_frames, samples)), mod)
