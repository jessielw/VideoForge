"""Encoder sharing preserves every setting and folder without overwriting local presets."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from test_server import make_client

from videoforge.core.encoder_io import FORMAT, read_encoder_bundle
from videoforge.core.plan_io import to_json
from videoforge.core.template_io import MAX_BYTES, MAX_NAME
from videoforge.core.video.settings import EncoderSettings
from videoforge.server.store import Store


def entry(label="Grain", group=None, **settings):
    return {"label": label, "group": group or [], "data": to_json(EncoderSettings()) | settings}


def bundle(*entries):
    return {"format": FORMAT, "version": 1, "encoders": list(entries)}


def test_round_trip_preview_and_restart(tmp_path):
    doc = bundle(
        entry(
            "日本語 grain",
            ["1080p", "SDR"],
            crf=19.5,
            tune="grain",
            options={"aq-mode": "3"},
            extra="--no-dct-decimate",
        ),
        entry(
            "HDR", ["2160p"], encoder="x265", depth=10, hdr10plus=True, dolby_vision=True, options={"level-idc": "5.1"}
        ),
        entry("Target", encoder="svtav1", preset="4", rate_control="2pass", target_mb=25000),
    )
    with make_client(tmp_path) as client:
        for action in ("export", "preview"):
            response = client.post(f"/api/presets/encoders/{action}", json=doc)
            assert response.status_code == 200, response.text
            assert (response.json() if action == "export" else response.json()["bundle"]) == read_encoder_bundle(doc)
        assert client.get("/api/presets").json()["encoder"] == []
        result = client.post("/api/presets/encoders/import", json=doc)
        assert result.status_code == 200, result.text
        assert result.json()["names"] == [e["label"] for e in doc["encoders"]]
        saved = result.json()["presets"]["encoder"]
        assert len({e["name"] for e in saved}) == 3
    with make_client(tmp_path) as client:
        saved = client.get("/api/presets").json()["encoder"]
        portable = [{k: e[k] for k in ("label", "group", "data")} for e in saved]
        assert sorted(portable, key=lambda e: e["label"]) == sorted(doc["encoders"], key=lambda e: e["label"])
        assert client.post("/api/presets/encoders/export", json=bundle(*portable)).json() == bundle(*portable)


def test_conflicts_are_scoped_and_preview_does_not_reserve_names(tmp_path):
    label = "A" * MAX_NAME
    with make_client(tmp_path) as client:
        client.put(f"/api/presets/encoder/{label}", json={"crf": 22})  # legacy flat preset
        client.put("/api/presets/template/Local", json={"qpf": False})
        client.put("/api/presets/template-default/manual", json={"name": "Local"})
        before = client.get("/api/presets").json()
        doc = bundle(entry(label), entry(label), entry(label, ["SDR"]), entry(label, encoder="x265"))
        preview = client.post("/api/presets/encoders/preview?keep_both=true", json=doc).json()
        assert preview["names"] == [label[:76] + " (2)", label[:76] + " (3)", label, label]
        # Another browser saves a name after preview; import must reallocate it.
        client.put(f"/api/presets/encoder/{label[:76]} (2)", json={"crf": 23})
        result = client.post("/api/presets/encoders/import?keep_both=true", json=doc).json()
        assert result["names"] == [label[:76] + " (3)", label[:76] + " (4)", label, label]
        assert result["presets"]["template"] == before["template"]
        assert result["presets"]["template_defaults"] == before["template_defaults"]
        assert next(e for e in result["presets"]["encoder"] if e["name"] == label) == before["encoder"][0]


@pytest.mark.parametrize(
    "data",
    [
        None,
        [],
        "settings",
        {"encoder": "bad"},
        {"crf": "18"},
        {"crf": True},
        {"depth": 8.5},
        {"options": {"ref": 4}},
        {"extra": None},
        {"unknown": True},
    ],
)
def test_invalid_settings_reject_whole_file(tmp_path, data):
    doc = bundle(entry("Valid"), entry("Invalid") | {"data": data})
    with make_client(tmp_path) as client:
        for action in ("export", "preview", "import"):
            response = client.post(f"/api/presets/encoders/{action}", json=doc)
            assert response.status_code == 422, response.text
        assert client.get("/api/presets").json()["encoder"] == []


@pytest.mark.parametrize(
    "doc",
    [
        None,
        {},
        [],
        bundle(),
        bundle(entry()) | {"version": 2},
        bundle(entry()) | {"version": True},
        bundle(entry()) | {"format": "videoforge.templates"},
        bundle(entry()) | {"extra": True},
        bundle(entry() | {"name": "local-id"}),
        bundle(entry(" ")),
        bundle(entry("A" * 81)),
        bundle(entry() | {"group": "SDR"}),
        bundle(entry(group=["a/b"])),
        bundle(entry(group=[" "])),
        bundle(entry(group=[4])),
        bundle(entry(group=["a"] * 9)),
        bundle(*[entry() for _ in range(501)]),
    ],
)
def test_invalid_envelopes(doc):
    with pytest.raises(ValueError):
        read_encoder_bundle(doc)


def test_malformed_oversized_and_nonfinite_files(tmp_path):
    with make_client(tmp_path) as client:
        for raw in (
            b"{bad",
            b"\xff",
            b"[" * 2000,
            b'{"format":"videoforge.encoders","version":1,"encoders":[{"label":"bad","group":[],"data":{"crf":NaN}}]}',
        ):
            assert client.post("/api/presets/encoders/import", content=raw).status_code == 422
        assert client.post("/api/presets/encoders/import", content=b" " * (MAX_BYTES + 1)).status_code == 413
        assert client.get("/api/presets").json()["encoder"] == []


def test_concurrent_imports_are_additive_and_failed_imports_are_atomic():
    store = Store(":memory:")
    try:

        def add(_):
            return store.import_encoder_presets([entry()], max_name=MAX_NAME)[0][0]

        with ThreadPoolExecutor(max_workers=4) as pool:
            labels = list(pool.map(add, range(8)))
        assert len(set(labels)) == len(store.presets("encoder")) == 8
        before = store.presets("encoder")
        with pytest.raises(TypeError):
            store.import_encoder_presets([entry("New"), entry("Bad", options=object())], max_name=MAX_NAME)
        assert store.presets("encoder") == before
    finally:
        store.close()
