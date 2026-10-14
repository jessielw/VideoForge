"""The window (`serve --window`): paths read from pywebview's drop event."""

from __future__ import annotations

from videoforge.desktop import dropped_paths


def test_dropped_paths_reads_pywebview_full_paths():
    event = {"type": "drop", "dataTransfer": {"files": [
        {"name": "a.mkv", "pywebviewFullPath": "D:\\media\\a.mkv"},
        {"name": "Season 1", "pywebviewFullPath": "D:\\media\\Season 1"},
        {"name": "unmatched.srt"},
    ]}}
    assert dropped_paths(event) == ["D:\\media\\a.mkv", "D:\\media\\Season 1"]
    assert dropped_paths({"type": "drop", "dataTransfer": {}}) == []
    assert dropped_paths({"type": "drop"}) == []
