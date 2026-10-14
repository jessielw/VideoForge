"""The window (`serve --window`): paths from pywebview's drop event, the icon, the route a second launch calls."""

from __future__ import annotations

from test_server import make_client

from videoforge.desktop import app_icon, dropped_paths


def test_dropped_paths_reads_pywebview_full_paths():
    event = {"type": "drop", "dataTransfer": {"files": [
        {"name": "a.mkv", "pywebviewFullPath": "D:\\media\\a.mkv"},
        {"name": "Season 1", "pywebviewFullPath": "D:\\media\\Season 1"},
        {"name": "unmatched.srt"},
    ]}}
    assert dropped_paths(event) == ["D:\\media\\a.mkv", "D:\\media\\Season 1"]
    assert dropped_paths({"type": "drop", "dataTransfer": {}}) == []
    assert dropped_paths({"type": "drop"}) == []


def test_app_icon_is_the_favicon_shape():
    img = app_icon(64)
    assert img.size == (64, 64) and img.mode == "RGBA"
    assert img.getpixel((0, 0))[3] == 0  # transparent corner
    assert img.getpixel((8, 32))[:3] == (0xB3, 0x97, 0x70)  # gold frame
    assert img.getpixel((32, 32))[:3] == (0x1C, 0x19, 0x17)  # play triangle


def test_window_show_route(tmp_path):
    with make_client(tmp_path) as client:
        assert client.post("/api/window/show").status_code == 404  # browser only
        shown = []
        client.app.state.show_window = lambda: shown.append(True)
        assert client.post("/api/window/show").json() == {"ok": True} and shown == [True]
