"""Template sharing: lossless settings, strict files, and additive atomic imports."""

from concurrent.futures import ThreadPoolExecutor
import copy

import pytest
from test_server import make_client

from videoforge.core.plan_io import to_json
from videoforge.core.template import Template
from videoforge.core.template_io import FORMAT, MAX_BYTES, MAX_NAME, read_bundle
from videoforge.server.store import Store


def bundle(*entries):
    return {"format": FORMAT, "version": 1, "templates": list(entries)}


def entry(name="Group setup", **settings):
    return {"name": name, "data": to_json(Template()) | settings}


def test_export_import_round_trip_and_preview(tmp_path):
    data = to_json(Template())
    data["video"] |= {
        "crop": {"left": 2, "top": 4, "right": 6, "bottom": 8},
        "resize": {"width": 1280, "height": 720, "kernel": "Spline36", "keep_ar": True, "mod": 2},
        "custom": "raise RuntimeError('Import must never execute this')",
        "filters": [{"category": "custom", "name": "Shared filter", "script": "clip = src", "enabled": False}],
    }
    data["encoder"] |= {"encoder": "x265", "crf": 19.5, "options": {"aq-mode": "3"}, "extra": "--no-sao"}
    data["mux"] |= {"container": "mp4", "extra": "-inter 500"}
    data |= {
        "crop_mode": "fixed",
        "qpf": False,
        "audio": {
            "mode": "rules",
            "rules": [
                {
                    "languages": ["ja", "en"],
                    "first_only": True,
                    "track": {"action": "copy"},
                    "extra": [{"action": "opus", "layout": "2.0", "bitrate_kbps": 128}],
                }
            ],
            "others": "exclude",
        },
        "subs": {"rules": [{"languages": ["en"], "forced": True, "track": {"flags": {"default": True}}}]},
    }
    original = bundle(
        {"name": "日本語 setup", "data": data}, entry("Stereo", audio={"slots": [{"track": {"action": "copy"}}]})
    )
    with make_client(tmp_path) as client:
        exported = client.post("/api/presets/templates/export", json=original)
        assert exported.status_code == 200, exported.text
        doc = exported.json()
        assert set(doc) == {"format", "version", "templates"}
        assert doc == read_bundle(original)
        assert client.get("/api/presets").json()["template"] == []
        preview = client.post("/api/presets/templates/preview", json=doc)
        assert preview.status_code == 200
        assert preview.json() == {"bundle": doc, "names": ["日本語 setup", "Stereo"]}
        assert client.get("/api/presets").json()["template"] == []
        imported = client.post("/api/presets/templates/import", json=doc)
        assert imported.status_code == 200, imported.text
        saved = {e["name"]: e["data"] for e in imported.json()["presets"]["template"]}
        assert saved == {e["name"]: e["data"] for e in doc["templates"]}
        assert imported.json()["presets"]["template_defaults"] == {}
    with make_client(tmp_path) as client:
        saved = client.get("/api/presets").json()["template"]
        assert client.post("/api/presets/templates/export", json=bundle(*saved)).json()["templates"] == saved


def test_conflicts_keep_existing_templates_defaults_and_other_presets(tmp_path):
    name = "A" * MAX_NAME
    with make_client(tmp_path) as client:
        client.put(f"/api/presets/template/{name}", json={"qpf": False})
        client.put("/api/presets/template-default/manual", json={"name": name})
        client.put("/api/presets/encoder/Local", json={})
        before = client.get("/api/presets").json()
        doc = bundle(entry(name), entry(name))
        preview = client.post("/api/presets/templates/preview", json=doc).json()
        assert preview["names"] == [name[:76] + " (2)", name[:76] + " (3)"]
        # A save in another tab between preview and import must not be overwritten.
        client.put(f"/api/presets/template/{preview['names'][0]}", json={"qpf": False})
        result = client.post("/api/presets/templates/import", json=doc).json()
        assert result["names"] == [name[:76] + " (3)", name[:76] + " (4)"]
        assert result["presets"]["template_defaults"] == before["template_defaults"]
        assert result["presets"]["encoder"] == before["encoder"]
        assert next(e for e in result["presets"]["template"] if e["name"] == name) == before["template"][0]


@pytest.mark.parametrize(
    "data",
    [
        None,
        [],
        "settings",
        {"qpf": "false"},
        {"qpf": None},
        {"crop_mode": "invalid"},
        {"video": None},
        {"video": {"crop": {"left": True}}},
        {"video": {"filters": [None]}},
        {"video": {"resize": {"width": "1280", "height": 720}}},
        {"encoder": {"crf": "18"}},
        {"encoder": {"options": {"aq-mode": 3}}},
        {"encoder": {"unknown": True}},
        {"audio": {"rules": {}}},
        {"audio": {"slots": [{"track": {"layout": "invalid"}}]}},
        {"subs": {"rules": [{"languages": "en"}]}},
        {"output_dir": "C:/private"},
    ],
)
def test_invalid_settings_reject_whole_bundle(tmp_path, data):
    doc = bundle(entry("Valid"), {"name": "Invalid", "data": data})
    with make_client(tmp_path) as client:
        for action in ("preview", "import", "export"):
            response = client.post(f"/api/presets/templates/{action}", json=doc)
            assert response.status_code == 422, response.text
        assert client.get("/api/presets").json()["template"] == []


@pytest.mark.parametrize(
    "doc",
    [
        None,
        [],
        {},
        {"format": "other", "version": 1, "templates": [entry()]},
        bundle(),
        bundle(entry()) | {"version": 2},
        bundle(entry()) | {"version": True},
        bundle(entry()) | {"template_defaults": {"manual": "Group setup"}},
        bundle({"name": " ", "data": {}}),
        bundle({"name": "A" * 81, "data": {}}),
        bundle({"name": 4, "data": {}}),
        bundle({"name": "Missing data"}),
        bundle(*[entry() for _ in range(501)]),
    ],
)
def test_invalid_envelopes(doc):
    with pytest.raises(ValueError):
        read_bundle(doc)


def test_malformed_and_oversized_files(tmp_path):
    with make_client(tmp_path) as client:
        for raw in (b"{broken", b"\xff", b"[" * 2000):
            assert client.post("/api/presets/templates/import", content=raw).status_code == 422
        assert client.post("/api/presets/templates/import", content=b" " * (MAX_BYTES + 1)).status_code == 413
        assert client.get("/api/presets").json()["template"] == []


def test_imported_built_in_defaults_get_a_distinct_name(tmp_path):
    with make_client(tmp_path) as client:
        profile = client.get("/api/profiles").json()[0]
        name = f"{profile['name']} defaults"
        doc = bundle({"name": name, "data": profile["defaults"]["template"]})
        assert client.post("/api/presets/templates/preview", json=doc).json()["names"] == [f"{name} (2)"]
        assert client.post("/api/presets/templates/import", json=doc).json()["names"] == [f"{name} (2)"]


def test_old_fields_get_defaults_and_filter_upgrade_without_mutating_input():
    doc = bundle({"name": " Old ", "data": {"video": {"filters": "clip = src"}}})
    before = copy.deepcopy(doc)
    normalized = read_bundle(doc)["templates"][0]
    assert doc == before
    assert normalized["name"] == "Old"
    assert normalized["data"]["audio"] is None and normalized["data"]["subs"] is None
    assert normalized["data"]["video"]["filters"][-1]["script"] == "clip = src"


def test_concurrent_imports_keep_every_copy_and_failed_batch_rolls_back():
    store = Store(":memory:")
    try:

        def add(_):
            return store.import_presets("template", [entry()], max_name=MAX_NAME)[0]

        with ThreadPoolExecutor(max_workers=4) as pool:
            names = list(pool.map(add, range(8)))
        assert len(set(names)) == len(store.presets("template")) == 8
        before = store.presets("template")
        with pytest.raises(TypeError):
            store.import_presets("template", [entry("New"), {"name": "Bad", "data": object()}], max_name=MAX_NAME)
        assert store.presets("template") == before
    finally:
        store.close()
