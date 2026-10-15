"""Auto-crop: find the black borders, the way StaxRip does (from the user's video-forge app).

Per sampled frame, 21 evenly spaced columns are scanned from the top and the
bottom, and 21 rows from each side, for pixels darker than a lightness threshold
(HSL L = (max + min) / 2). A side's crop is the smallest run over all samples and
frames, so one bright frame is enough to keep picture, and a fade to black can't
over-crop. Values round down to the chroma mod.
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


def _run(dark: np.ndarray) -> np.ndarray:
    """Per column of a boolean (rows, cols) array: how many leading rows are dark."""
    bright = ~dark
    first = bright.argmax(axis=0)
    return np.where(bright.any(axis=0), first, dark.shape[0])


def frame_borders(rgb: np.ndarray, threshold: float = THRESHOLD) -> Crop:
    """The black border of one (H, W, 3) frame, each side limited to a quarter of the frame."""
    h, w = rgb.shape[:2]
    xs = [int(w * i / _POSITIONS) for i in range(_POSITIONS)]
    ys = [int(h * i / _POSITIONS) for i in range(_POSITIONS)]
    qh, qw = max(1, h // 4), max(1, w // 4)

    def dark(px: np.ndarray) -> np.ndarray:  # only the sampled lines: the whole frame costs ~70 ms at 1080p
        return (px.max(axis=-1).astype(np.uint16) + px.min(axis=-1)) / 510.0 < threshold

    cols, rows = dark(rgb[:, xs]), dark(rgb[ys, :]).T  # rows.T: one column per sampled row
    return Crop(
        left=int(_run(rows[:qw]).min()),
        top=int(_run(cols[:qh]).min()),
        right=int(_run(rows[::-1][:qw]).min()),
        bottom=int(_run(cols[::-1][:qh]).min()),
    )


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


def detect(clip: vs.VideoNode, samples: int = 20, threshold: float = THRESHOLD, mod: int = 2) -> Crop:
    from videoforge.core.video.vs import frame_rgb

    return combine((frame_borders(frame_rgb(clip, n), threshold) for n in sample_frames(clip.num_frames, samples)),
                   mod)
