"""Fix mode: header edits in place (mkvpropedit), structural changes by remux (mkvmerge).

The integration tests run the real MKVToolNix from tools/ on a tiny MKV that
ffmpeg generates; they skip when either is missing.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from videoforge.core.config import PROJECT_ROOT, Tools
from videoforge.core.fix import (
    FixError,
    FixMethod,
    FixState,
    HeaderTrack,
    apply_fix,
    method,
    propedit_command,
    read_state,
    remux_command,
    subtitle_track,
)


def state(path=Path("R.mkv")) -> FixState:
    return FixState(
        path,
        "",
        [
            HeaderTrack(0, 1, "video", "AVC", language="und", default=True),
            HeaderTrack(1, 2, "audio", "AAC", "AAC 2.0", "ja", default=True),
            HeaderTrack(2, 3, "audio", "E-AC-3", "E-AC-3 5.1", "en"),
            HeaderTrack(3, 4, "subtitles", "SubRip/SRT", "English", "en"),
        ],
    )


def test_header_changes_are_in_place():
    current = state()
    wanted = current.copy()
    assert method(current, wanted) is FixMethod.NONE
    wanted.tracks[1].name = "Japanese"
    wanted.tracks[3].forced = True
    wanted.tracks[3].language = "en-US"
    wanted.title = "Movie"
    assert method(current, wanted) is FixMethod.IN_PLACE
    assert propedit_command("mkvpropedit", current, wanted) == [
        "mkvpropedit", "R.mkv",
        "--edit", "info", "--set", "title=Movie",
        "--edit", "track:@2", "--set", "name=Japanese",
        "--edit", "track:@4", "--set", "language=en-US", "--set", "flag-forced=1",
    ]  # fmt: skip
    wanted.tracks[1].name = ""
    assert "--delete" in propedit_command("mkvpropedit", current, wanted)


def test_drop_reorder_or_add_is_a_remux():
    current = state()
    dropped = current.copy()
    dropped.tracks[2].keep = False
    assert method(current, dropped) is FixMethod.REMUX
    moved = current.copy()
    moved.tracks[1], moved.tracks[2] = moved.tracks[2], moved.tracks[1]
    assert method(current, moved) is FixMethod.REMUX

    wanted = current.copy()
    wanted.tracks[3].keep = False
    srt = subtitle_track(Path("new.en.srt"), "en")
    srt.name, srt.default = "English", True
    wanted.tracks.insert(3, srt)
    assert method(current, wanted) is FixMethod.REMUX
    argv = remux_command("mkvmerge", wanted, Path("R.fixing.mkv"))
    assert argv[:3] == ["mkvmerge", "-o", "R.fixing.mkv"]
    assert argv[argv.index("--audio-tracks") + 1] == "1,2"
    assert "--no-subtitles" in argv  # the old SRT is dropped
    assert argv.index("R.mkv") < argv.index("new.en.srt")
    i = argv.index("new.en.srt")
    assert argv[i - 16 : i - 12] == ["--language", "0:en", "--track-name", "0:English"]  # its own options precede it
    assert argv[-2:] == ["--track-order", "0:0,0:1,0:2,1:0"]


def test_video_is_required():
    wanted = state()
    wanted.tracks[0].keep = False
    with pytest.raises(FixError):
        remux_command("mkvmerge", wanted, Path("x.mkv"))


def test_only_mkv(tmp_path):
    with pytest.raises(FixError):
        read_state(tmp_path / "a.mp4", "mkvmerge")


# --- real tools ---------------------------------------------------------------------

MKVTOOLNIX = PROJECT_ROOT / "tools" / "MKVToolNix"
FFMPEG = shutil.which("ffmpeg")
needs_tools = pytest.mark.skipif(
    not (MKVTOOLNIX / "mkvmerge.exe").exists() or FFMPEG is None, reason="needs tools/MKVToolNix and ffmpeg"
)
TOOLS = Tools(
    mkvmerge=str(MKVTOOLNIX / "mkvmerge.exe"), deezy="", dee="", truehdd="", qaac="", ffmpeg=FFMPEG or "",
    mkvpropedit=str(MKVTOOLNIX / "mkvpropedit.exe"),
)  # fmt: skip


@pytest.fixture
def release(tmp_path) -> Path:
    """A 1 s MKV: video, ja + en audio, an English SRT."""
    raw = tmp_path / "raw.mkv"
    subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=duration=1:size=64x64:rate=24",
         "-f", "lavfi", "-i", "sine=duration=1", "-map", "0", "-map", "1", "-map", "1",
         "-c:v", "libx264", "-c:a", "aac", "-y", str(raw)],
        check=True,
    )  # fmt: skip
    srt = tmp_path / "old.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:00,900\nHello\n", encoding="utf-8")
    out = tmp_path / "Movie-GROUP.mkv"
    subprocess.run(
        [TOOLS.mkvmerge, "-q", "-o", str(out), "--language", "1:ja", "--track-name", "1:AAC 2.0",
         "--language", "2:en", str(raw), "--language", "0:en", str(srt)],
        check=True,
    )  # fmt: skip
    return out


@needs_tools
def test_in_place_edit_on_a_real_file(release):
    current = read_state(release, TOOLS.mkvmerge)
    assert [t.kind for t in current.tracks] == ["video", "audio", "audio", "subtitles"]
    wanted = current.copy()
    wanted.tracks[1].name = "Japanese AAC 2.0"
    wanted.tracks[2].default = False
    wanted.tracks[3].forced = True
    wanted.tracks[3].hearing_impaired = True
    wanted.tracks[1].original = True
    wanted.tracks[2].commentary = True
    wanted.tracks[2].visual_impaired = True  # audio description
    lines = []
    result = apply_fix(current, wanted, TOOLS, log=lines.append)
    assert result.method is FixMethod.IN_PLACE
    after = read_state(release, TOOLS.mkvmerge)
    assert after.tracks == wanted.tracks
    assert method(after, wanted) is FixMethod.NONE


@needs_tools
def test_remux_drops_adds_and_reorders(release, tmp_path):
    current = read_state(release, TOOLS.mkvmerge)
    new_srt = tmp_path / "new.srt"
    new_srt.write_text("1\n00:00:00,000 --> 00:00:00,900\nHi\n", encoding="utf-8")
    wanted = current.copy()
    wanted.tracks[3].keep = False  # old SRT out
    added = subtitle_track(new_srt, "en")
    added.name = "English (SDH)"
    added.hearing_impaired = True
    wanted.tracks.append(added)
    wanted.tracks[1], wanted.tracks[2] = wanted.tracks[2], wanted.tracks[1]  # en audio first
    result = apply_fix(current, wanted, TOOLS)
    assert result.method is FixMethod.REMUX
    assert not list(tmp_path.glob("*.fixing.mkv"))
    after = read_state(release, TOOLS.mkvmerge)
    assert [(t.kind, t.language) for t in after.tracks] == [
        ("video", "und"), ("audio", "en"), ("audio", "ja"), ("subtitles", "en"),
    ]  # fmt: skip
    assert after.tracks[3].name == "English (SDH)" and after.tracks[3].hearing_impaired
