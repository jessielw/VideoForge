"""A test encode's quality: SSIMULACRA2 and XPSNR (vszip) of its frames against the frames that went into the
encoder, written as JSON. Run out of the server process (the server never imports VapourSynth):

    python -m videoforge.core.video.metrics <reference.vpy> <encode.mkv> <out.json>

The reference is the script the encoder got (the sample's); the encode is opened with FFMS2 as the preview opens
it (script.encoded_script, its index next to it), so frame n of one is frame n of the other. SSIMULACRA2 gets both
as RGBS (the reference's matrix for both; one it doesn't say is guessed from its size), vszip linearises them as
sRGB; its mean and 5th percentile (the worst frames) go out. XPSNR needs YUV at 8 or 10 bits and an even size: a
deeper clip is compared at 10 bits; another (RGB, odd size) gets none. Its luma's average is ffmpeg's (the frames'
weighted distortion averaged, then in dB); frames identical to their reference count no distortion, and a sample
that is all of them has none (None).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import sys
from typing import TYPE_CHECKING, Any, TextIO

if TYPE_CHECKING:
    import vapoursynth as vs

_PERCENTILE = 5  # the worst frames' SSIMULACRA2
_UNSPECIFIED = (2, 3)  # _Matrix: unspecified, reserved


@dataclass(frozen=True, slots=True)
class Scores:
    frames: int
    ssimulacra2: float  # the frames' mean; 100 is identical, ~90 visually lossless, ~70 high quality
    ssimulacra2_p5: float  # 5% of the frames score below it
    xpsnr: float | None  # luma, dB; None: not YUV with an even size, or no frame differs


def _matrix(clip: vs.VideoNode, said: int) -> int:
    """The YUV matrix to convert by: the clip's, else BT.709 for HD and BT.601 below it (as zimg's users guess)."""
    if said not in _UNSPECIFIED:
        return said
    return 1 if clip.width > 1024 or clip.height > 576 else 6


def _core() -> Any:
    """vs.core, whose plugins (resize, std, vszip) aren't in the stubs."""
    import vapoursynth as vs

    return vs.core


def _rgbs(clip: vs.VideoNode, matrix: int) -> vs.VideoNode:
    import vapoursynth as vs

    if clip.format.color_family == vs.YUV:
        return _core().resize.Bicubic(clip, format=vs.RGBS, matrix_in=matrix)
    return _core().resize.Bicubic(clip, format=vs.RGBS)


def _xpsnr_input(clip: vs.VideoNode) -> vs.VideoNode | None:
    """The clip as XPSNR takes it (YUV, 8 or 10 bits, even size), or None."""
    import vapoursynth as vs

    f = clip.format
    if f.color_family != vs.YUV or clip.width % 2 or clip.height % 2:
        return None
    if f.sample_type == vs.INTEGER and f.bits_per_sample in (8, 10):
        return clip
    return _core().resize.Point(clip, format=f.replace(sample_type=vs.INTEGER, bits_per_sample=10))


def xpsnr_average(frames: list[float]) -> float | None:
    """ffmpeg's (and vszip's) average of per-frame XPSNR values: their weighted distortion (sqrt of the WSSE,
    10^(-dB/20) of the frame's) averaged, then back to dB. Identical frames (inf) add none; all of them: None."""
    if not frames:
        return None
    mean = sum(0.0 if math.isinf(x) else 10 ** (-x / 20) for x in frames) / len(frames)
    return -20 * math.log10(mean) if mean > 0 else None


def percentile(values: list[float], pct: float) -> float:
    """The nearest-rank pct percentile."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(pct / 100 * len(ordered)) - 1)]


def measure(reference: vs.VideoNode, encoded: vs.VideoNode, out: TextIO = sys.stdout) -> Scores:
    """Both clips frame by frame, printing "Progress: N%" lines."""
    core = _core()
    if (reference.width, reference.height) != (encoded.width, encoded.height):
        raise RuntimeError(
            f"The encode is {encoded.width}x{encoded.height} and its script {reference.width}x{reference.height}"
        )
    if reference.num_frames != encoded.num_frames:
        raise RuntimeError(f"The encode has {encoded.num_frames} frames and its script {reference.num_frames}")
    if encoded.format.id != reference.format.id:  # an encoder that writes another depth than it reads
        encoded = core.resize.Point(encoded, format=reference.format.id)
    said = reference.get_frame(0).props.get("_Matrix", 2)
    matrix = _matrix(reference, said if isinstance(said, int) else 2)
    node = core.vszip.SSIMULACRA2(_rgbs(reference, matrix), _rgbs(encoded, matrix))
    ref_x, enc_x = _xpsnr_input(reference), _xpsnr_input(encoded)
    if ref_x is not None and enc_x is not None:
        xpsnr = core.vszip.XPSNR(ref_x, enc_x, verbose=False)
        node = core.std.CopyFrameProps(node, xpsnr, props=["XPSNR_Y"])
    total, last = node.num_frames, -1
    ssim: list[float] = []
    xp: list[float] = []
    for n, frame in enumerate(node.frames(close=True)):
        ssim.append(float(frame.props["SSIMULACRA2"]))  # pyright: ignore[reportArgumentType]
        if "XPSNR_Y" in frame.props:
            xp.append(float(frame.props["XPSNR_Y"]))  # pyright: ignore[reportArgumentType]
        pct = (n + 1) * 100 // total
        if pct != last:
            last = pct
            out.write(f"Progress: {pct}%\n")
            out.flush()
    if not ssim:
        raise RuntimeError("The encode has no frames")
    return Scores(
        frames=len(ssim),
        ssimulacra2=sum(ssim) / len(ssim),
        ssimulacra2_p5=percentile(ssim, _PERCENTILE),
        xpsnr=xpsnr_average(xp) if len(xp) == len(ssim) else None,
    )


def read(path: Path) -> Scores | None:
    """The scores a quality step wrote; None when they aren't there or can't be read."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Scores(data["frames"], data["ssimulacra2"], data["ssimulacra2_p5"], data["xpsnr"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def main() -> None:
    if len(sys.argv) != 4:
        sys.exit("usage: python -m videoforge.core.video.metrics <reference.vpy> <encode.mkv> <out.json>")
    from videoforge.core.video.script import encoded_script
    from videoforge.core.video.vs import load_clip

    script, mkv, result = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    try:
        scores = measure(load_clip(script.read_text(encoding="utf-8")), load_clip(encoded_script(mkv, mkv.parent)))
        partial = result.with_name(result.name + ".partial")
        partial.write_text(json.dumps(asdict(scores), indent=2), encoding="utf-8")
        os.replace(partial, result)
    except Exception as e:  # the message is the step's error
        print(e, file=sys.stderr)
        sys.exit(1)
    print(
        f"SSIMULACRA2 {scores.ssimulacra2:.2f} (5% of frames below {scores.ssimulacra2_p5:.2f})"
        + (f", XPSNR {scores.xpsnr:.2f} dB" if scores.xpsnr is not None else "")
    )


if __name__ == "__main__":
    main()
