"""Audio sharing preserves custom titles and adds presets without overwriting the library."""

import pytest
from test_server import make_client

from videoforge.core.audio_io import read_audio_bundle
from videoforge.core.template_io import MAX_BYTES


def bundle(*entries):
    return {"format": "videoforge.audio", "version": 1, "audio": list(entries)}


def entry(label="Surround", group=None, **settings):
    return {
        "label": label,
        "group": group or [],
        "data": {"action": "ddp", "layout": "5.1", "bitrate_kbps": 640, "options": {}, "title": "Bob"} | settings,
    }


def test_audio_round_trip_conflicts_and_restart(tmp_path):
    doc = bundle(entry(group=["Home cinema"], options={"dialnorm": "-27"}), entry(title=None))
    with make_client(tmp_path) as client:
        exported = client.post("/api/presets/audio/export", json=doc)
        assert exported.status_code == 200, exported.text
        assert exported.json() == doc
        preview = client.post("/api/presets/audio/preview?keep_both=true", json=doc).json()
        assert preview == {"bundle": doc, "names": ["Surround", "Surround"], "actions": ["new", "new"]}
        assert client.get("/api/presets").json()["audio"] == []
        first = client.post("/api/presets/audio/import?keep_both=true", json=doc).json()
        second = client.post("/api/presets/audio/import?keep_both=true", json=doc).json()
        assert second["names"] == ["Surround (2)", "Surround (2)"]
        assert len(second["presets"]["audio"]) == 4
        for original in first["presets"]["audio"]:
            assert original in second["presets"]["audio"]
    with make_client(tmp_path) as client:
        saved = client.get("/api/presets").json()["audio"]
        assert len(saved) == 4
        assert [p["data"]["title"] for p in saved].count("Bob") == 2
        portable = [{k: p[k] for k in ("label", "group", "data")} for p in saved]
        assert client.post("/api/presets/audio/export", json=bundle(*portable)).json() == bundle(*portable)


@pytest.mark.parametrize(
    "settings",
    [
        {"action": "unknown"},
        {"title": 42},
        {"options": {"unknown": "x"}},
        {"layout": "invalid"},
        {"bitrate_kbps": -1},
        {"unknown": True},
    ],
)
def test_invalid_audio_file_is_atomic(tmp_path, settings):
    doc = bundle(entry(), entry("Invalid", **settings))
    with make_client(tmp_path) as client:
        for action in ("export", "preview", "import"):
            assert client.post(f"/api/presets/audio/{action}", json=doc).status_code == 422
        assert client.get("/api/presets").json()["audio"] == []


def test_audio_legacy_defaults_and_file_limits(tmp_path):
    legacy = entry()
    del legacy["data"]["title"]
    assert read_audio_bundle(bundle(legacy))["audio"][0]["data"]["title"] is None
    with make_client(tmp_path) as client:
        for raw in (b"{bad", b"[" * 2000):
            assert client.post("/api/presets/audio/import", content=raw).status_code == 422
        assert client.post("/api/presets/audio/import", content=b" " * (MAX_BYTES + 1)).status_code == 413
        for doc in (bundle(), bundle(entry(group=["a/b"])), bundle(entry()) | {"version": 2}):
            assert client.post("/api/presets/audio/import", json=doc).status_code == 422
