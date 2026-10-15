"""Measure audio sync of a muxed release against its source, by cross-correlation.

usage:
    uv run --no-project --with numpy python -I scripts/av_offset.py SOURCE OUTPUT SHIFT_S \
        OUT_STREAM=SRC_STREAM [...] [--at START,START,...]

Output time t is compared against source time t + SHIFT_S, where SHIFT_S is the
source video's start offset in seconds (0 for most remuxes; 0.838 for the Atmos
sample). Prints the offset in ms per stream pair and window; 0.00 is perfect.

Caveats:
- Each stream is decoded from the start and sliced, because ffmpeg -ss is not
  sample-accurate on TrueHD in MKV (it reads 89-94 ms off).
- The decoded PCM ignores a track's container start delay. For a copied track
  with MediaInfo "delay relative to video" D, the true offset is reading + D.
- An ffmpeg-made AC-3 reads about -5.3 ms (its 256-sample priming).
"""

import subprocess
import sys

import numpy as np

RATE = 8000
WINDOW_S = 20

_cache: dict[tuple[str, str], np.ndarray] = {}


def pcm(path: str, stream: str, start: float, dur: float) -> np.ndarray:
    key = (path, stream)
    if key not in _cache:
        out = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", path, "-map", stream, "-ac", "1", "-ar", str(RATE), "-f", "f32le", "-"],
            capture_output=True,
            check=True,
        ).stdout
        _cache[key] = np.frombuffer(out, dtype=np.float32)
    i = round(start * RATE)
    return _cache[key][i : i + round(dur * RATE)]


def offset_ms(a: np.ndarray, b: np.ndarray) -> float:
    """Positive: a is later than b."""
    n = min(len(a), len(b))
    a, b = a[:n] - a[:n].mean(), b[:n] - b[:n].mean()
    size = 1 << (2 * n - 1).bit_length()
    corr = np.fft.irfft(np.fft.rfft(a, size) * np.conj(np.fft.rfft(b, size)), size)
    lag = int(np.argmax(corr))
    if lag > size // 2:
        lag -= size
    return lag * 1000 / RATE


def main(args: list[str]) -> None:
    starts = [60.0, 600.0, 1300.0]
    if "--at" in args:
        i = args.index("--at")
        starts = [float(x) for x in args[i + 1].split(",")]
        args = args[:i] + args[i + 2 :]
    if len(args) < 4:
        sys.exit(__doc__)
    src, out, shift = args[0], args[1], float(args[2])
    for pair in args[3:]:
        out_stream, src_stream = pair.split("=")
        for start in starts:
            ms = offset_ms(pcm(out, out_stream, start, WINDOW_S), pcm(src, src_stream, start + shift, WINDOW_S))
            print(f"out {out_stream} vs src {src_stream} @ {start:g}s: {ms:+.2f} ms")


if __name__ == "__main__":
    main(sys.argv[1:])
