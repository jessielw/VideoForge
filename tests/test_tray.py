"""The tray (`serve --tray`): the icon, and the page's Shut down."""

from __future__ import annotations

from test_server import make_client

from videoforge.tray import app_icon


def test_app_icon_is_the_favicon_shape():
    img = app_icon(64)
    assert img.size == (64, 64) and img.mode == "RGBA"
    assert img.getpixel((0, 0))[3] == 0  # transparent corner
    assert img.getpixel((8, 32))[:3] == (0xB3, 0x97, 0x70)  # gold frame
    assert img.getpixel((32, 32))[:3] == (0x1C, 0x19, 0x17)  # play triangle


def test_shutdown_route(tmp_path):
    with make_client(tmp_path) as client:
        assert client.post("/api/shutdown").status_code == 404  # nothing set up to stop
        stopped = []
        client.app.state.shutdown = lambda: stopped.append(True)
        assert client.post("/api/shutdown").json() == {"ok": True} and stopped == [True]
