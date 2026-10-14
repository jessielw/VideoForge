"""Added audio files probed with the real tools: raw streams get their codec, and the file name
gives a missing language and an eac3to-style delay. Skips without tools/MKVToolNix and ffmpeg."""

from __future__ import annotations

import shutil
import subprocess

import pytest

from videoforge.core.config import PROJECT_ROOT
from videoforge.core.jobs import external_audio_tracks
from videoforge.core.models import AudioCodec, Layout

MKVMERGE = PROJECT_ROOT / "tools" / "MKVToolNix" / "mkvmerge.exe"
FFMPEG = shutil.which("ffmpeg")
pytestmark = pytest.mark.skipif(not MKVMERGE.exists() or FFMPEG is None, reason="needs tools/MKVToolNix and ffmpeg")


def test_raw_audio_files(tmp_path):
    ac3 = tmp_path / "Commentary.en DELAY 100ms.ac3"
    flac = tmp_path / "German.de.flac"
    subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "sine=d=1", "-ac", "2", "-c:a", "ac3", str(ac3)], check=True)
    subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "sine=d=1", "-filter_complex",
                    "[0]asplit=6[a][b][c][d][e][f];[a][b][c][d][e][f]join=inputs=6:channel_layout=5.1(side)",
                    "-c:a", "flac", str(flac)], check=True)  # fmt: skip
    tracks, issues = external_audio_tracks([ac3, flac], str(MKVMERGE))
    got = [(t.external_path.name, t.codec, t.layout, t.language, t.delay_ms) for t in tracks]
    assert got == [
        (ac3.name, AudioCodec.AC3, Layout(2, 0), "en", 100),
        (flac.name, AudioCodec.FLAC, Layout(5, 1), "de", 0),
    ]
    assert not issues
    # At a glance: rate, depth (lossless only), duration.
    assert [(t.sample_rate, t.bit_depth) for t in tracks] == [(44100, None), (44100, 16)]
    assert all(t.duration_ms and 900 <= t.duration_ms <= 1100 for t in tracks)
