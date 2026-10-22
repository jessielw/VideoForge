"""Audio preset persistence, validation, and copies used by templates and jobs."""

import pytest
from test_server import add, make_client, make_files, wait_for


def test_audio_preset_folders_and_metadata(tmp_path):
    body = {
        "label": "5.1 640 kbps",
        "group": ["Surround", "Compatibility"],
        "data": {
            "action": "ac3",
            "layout": "5.1",
            "bitrate_kbps": 640,
            "options": {"dialnorm": "-27", "extra": "-cutoff 18000"},
            "language": "en",
            "title": "Bob",
            "flags": {"default": True},
            "exclude": True,
            "delay_ms": 250,
        },
    }
    with make_client(tmp_path) as client:
        response = client.post("/api/presets/audio", json=body)
        assert response.status_code == 200, response.text
        (preset,) = response.json()["audio"]
        assert set(preset["data"]) == {"action", "layout", "bitrate_kbps", "options", "title"}
        assert preset["data"]["title"] == "Bob"
        assert preset["data"]["options"] == body["data"]["options"]
        assert client.post("/api/presets/audio", json=body).status_code == 409
        assert client.post("/api/presets/audio", json=body | {"group": ["Other"]}).status_code == 200
        assert (
            client.post("/api/presets/audio", json=body | {"data": body["data"] | {"action": "eac3"}}).status_code
            == 200
        )

        moved = body | {"name": preset["name"], "label": " Surround 640 ", "group": [" Home cinema "]}
        response = client.post("/api/presets/audio", json=moved)
        assert response.status_code == 200
        preset = next(p for p in response.json()["audio"] if p["name"] == preset["name"])
        assert preset["label"] == "Surround 640" and preset["group"] == ["Home cinema"]
        assert client.post("/api/presets/audio", json=body | {"name": "missing"}).status_code == 404

    with make_client(tmp_path) as client:
        saved = client.get("/api/presets").json()["audio"]
        assert next(p for p in saved if p["name"] == preset["name"]) == preset
        # The generic settings route retains organization and only stores audio settings.
        saved = client.put(f"/api/presets/audio/{preset['name']}", json=preset["data"] | {"bitrate_kbps": 448}).json()[
            "audio"
        ]
        updated = next(p for p in saved if p["name"] == preset["name"])
        assert updated["group"] == preset["group"] and updated["data"]["bitrate_kbps"] == 448
        assert len(client.delete(f"/api/presets/audio/{preset['name']}").json()["audio"]) == 2


@pytest.mark.parametrize(
    "data",
    [
        {"action": "copy", "title": 42},
        {"action": "unknown"},
        {"action": "ac3", "layout": "7.1"},
        {"action": "ac3", "layout": "invalid"},
        {"action": "ac3", "bitrate_kbps": 641},
        {"action": "eac3", "bitrate_kbps": 7000},
        {"action": "opus", "layout": "1.0", "bitrate_kbps": 384},
        {"action": "ac3", "bitrate_kbps": 0},
        {"action": "ac3", "bitrate_kbps": -1},
        {"action": "ac3", "bitrate_kbps": 640.5},
        {"action": "ac3", "bitrate_kbps": True},
        {"action": "flac", "bitrate_kbps": 640},
        {"action": "copy", "layout": "5.1"},
        {"action": "copy", "options": {"extra": "-x"}},
        {"action": "ac3", "options": {"dialnorm": "-32"}},
        {"action": "ac3", "options": {"dialnorm": -27}},
        {"action": "ac3", "options": {"unknown": "value"}},
        {"action": "aac", "options": {"quality": "128"}},
        {"action": "ddp", "options": {"ddp_mode": "auto"}},
        {"action": "ddp", "layout": "5.1", "options": {"ddp_mode": " bluray "}},
    ],
)
def test_invalid_audio_presets_are_rejected(tmp_path, data):
    with make_client(tmp_path) as client:
        body = {"label": "Invalid", "data": data}
        assert client.post("/api/presets/audio", json=body).status_code == 422
        assert client.put("/api/presets/audio/Invalid", json=data).status_code == 422
        assert client.get("/api/presets").json()["audio"] == []


@pytest.mark.parametrize("mode", ["position", "rules"])
def test_audio_presets_in_templates_keep_snapshots_and_fit_sources(tmp_path, mode):
    make_files(tmp_path)
    with make_client(tmp_path) as client:
        body = {"label": "Surround", "data": {"action": "ddp", "layout": "5.1", "bitrate_kbps": 640}}
        (preset,) = client.post("/api/presets/audio", json=body).json()["audio"]
        track = preset["data"] | {"title": "Group audio", "flags": {"commentary": True}}
        # The same picker supplies primary outputs, extra outputs, and either template matching mode.
        audio = {"mode": mode, "slots" if mode == "position" else "rules": [{"track": track, "extra": [track]}]}
        if mode == "rules":
            audio["rules"][0]["languages"] = ["ja", "en"]
        (template,) = client.put("/api/presets/template/Group audio", json={"audio": audio}).json()["template"]
        (job_id,) = add(client, tmp_path, template=template["data"])
        job = wait_for(client, job_id, "ready", "warn")
        japanese = [a for a in job["plan"]["audio"] if a["language"] == "ja"]
        assert len(japanese) == 2
        assert {(a["out_layout"], a["bitrate_kbps"]) for a in japanese} == {("2.0", 256)}
        assert {a["title"] for a in japanese} == {"Group audio"}
        before = job["spec"]

        client.post("/api/presets/audio", json=body | {"name": preset["name"], "data": {"action": "copy"}})
        client.delete(f"/api/presets/audio/{preset['name']}")
        assert client.get("/api/presets").json()["template"][0] == template
        assert client.get(f"/api/jobs/{job_id}").json()["spec"] == before


def test_audio_encoder_limits_are_exposed_for_source_compatibility(tmp_path):
    with make_client(tmp_path) as client:
        encodes = {e["id"]: e for e in client.get("/api/config/encoders").json()}
        assert encodes["opus"]["per_channel_max"] == 256
        assert encodes["opus"]["bitrate_range"] == [6, 2048]
        assert encodes["ac3"]["bitrate_choices"][-1] == 640
        mode = next(o for o in encodes["ddp"]["options"] if o["key"] == "ddp_mode")
        assert mode["default"] == "standard"
        assert mode["choices"] == [{"value": "standard", "label": "Standard"}, {"value": "bluray", "label": "Blu-ray"}]


def test_ddp_bluray_preset_persists_and_checks_layout(tmp_path):
    data = {"action": "ddp", "layout": "7.1", "bitrate_kbps": 1536, "options": {"ddp_mode": "bluray"}}
    with make_client(tmp_path) as client:
        response = client.post("/api/presets/audio", json={"label": "Blu-ray", "data": data})
        assert response.status_code == 200, response.text
        (saved,) = response.json()["audio"]
        assert saved["data"]["options"] == {"ddp_mode": "bluray"}
        for layout in ("1.0", "2.0", "5.1"):
            response = client.post("/api/presets/audio", json={"label": "Invalid", "data": data | {"layout": layout}})
            assert response.status_code == 422
    with make_client(tmp_path) as client:
        assert client.get("/api/presets").json()["audio"] == [saved]
