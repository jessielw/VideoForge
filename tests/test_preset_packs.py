"""Group preset packs exclude application configuration and import additively across libraries."""

from concurrent.futures import ThreadPoolExecutor
import copy
from dataclasses import replace
import json
import sqlite3

import pytest
from test_configuration_transfer import export, seed
from test_server import make_client

from videoforge.server.preset_pack import FORMAT, MAX_BYTES, read_preset_pack
from videoforge.server.store import Store


def portable(configuration):
    libraries = copy.deepcopy(configuration["presets"])
    for kind in ("encoder", "audio"):
        libraries[kind] = [{key: entry[key] for key in ("label", "group", "data")} for entry in libraries[kind]]
    return {"format": FORMAT, "version": 1, "presets": libraries}


def test_share_selected_libraries_without_private_configuration_and_import_on_another_installation(tmp_path):
    with make_client(tmp_path / "sender") as sender:
        seed(sender, tmp_path)
        sender.app.state.base_config = replace(
            sender.app.state.base_config, plugins={"example": {"token": "PLUGIN_SECRET"}}
        )
        sender.put(
            "/api/config",
            json={
                "notifications": [
                    {
                        "name": "Private",
                        "url": "json://localhost/NOTIFICATION_SECRET",
                        "enabled": False,
                        "events": ["job_done"],
                    }
                ],
                "actions": [
                    {
                        "name": "Private webhook",
                        "kind": "webhook",
                        "target": "https://example.test/ACTION_SECRET",
                        "enabled": False,
                        "events": ["job_done"],
                    }
                ],
            },
        )
        configuration = export(sender)
        raw = json.dumps(configuration)
        assert all(secret in raw for secret in ("PLUGIN_SECRET", "NOTIFICATION_SECRET", "ACTION_SECRET"))
        doc = portable(configuration)
        doc["presets"]["audio"][0]["data"]["title"] = "Bob"
        # Export only the reusable settings, not this group's complete library.
        doc["presets"]["video"] = []
        response = sender.post("/api/preset-packs/export", json=doc)
        assert response.status_code == 200, response.text
        shared = response.json()
        assert shared["presets"]["audio"][0]["data"]["title"] == "Bob"
        assert set(shared) == {"format", "version", "presets"}
        raw = json.dumps(shared)
        assert all(
            secret not in raw for secret in ("PLUGIN_SECRET", "NOTIFICATION_SECRET", "ACTION_SECRET", "custom-x264")
        )
        assert all("name" not in entry for kind in ("encoder", "audio") for entry in shared["presets"][kind])
    with make_client(tmp_path / "recipient") as recipient:
        seed(recipient, tmp_path)
        before = export(recipient)
        preview = recipient.post("/api/preset-packs/preview?keep_both=true", json=shared)
        assert preview.status_code == 200, preview.text
        assert preview.json()["names"] == {
            "template": ["Feature (2)"],
            "encoder": ["Film (2)"],
            "audio": ["Film (2)"],
            "video": [],
        }
        assert export(recipient) == before
        imported = recipient.post("/api/preset-packs/import?keep_both=true", json=shared)
        assert imported.status_code == 200, imported.text
        after = export(recipient)
        for key in ("application", "settings", "folders", "template_defaults"):
            assert after[key] == before[key]
        for kind in ("encoder", "audio"):
            entries = after["presets"][kind]
            assert len(entries) == 2
            added = next(entry for entry in entries if entry["label"] == "Film (2)")
            assert added["group"] == ["1080p", "SDR"]
            assert added["data"] == shared["presets"][kind][0]["data"]
            assert added["name"] != before["presets"][kind][0]["name"]
        assert after["presets"]["video"] == before["presets"]["video"]


def test_conflicts_reallocated_after_preview_and_scoped_to_encoder_and_folder(tmp_path):
    with make_client(tmp_path) as client:
        seed(client, tmp_path)
        doc = portable(export(client))
        encoder = doc["presets"]["encoder"][0]
        doc["presets"]["encoder"] += [
            copy.deepcopy(encoder) | {"group": ["Other"]},
            copy.deepcopy(encoder) | {"data": encoder["data"] | {"encoder": "x264"}},
        ]
        doc["presets"]["template"][0]["name"] = "Manual defaults"
        preview = client.post("/api/preset-packs/preview?keep_both=true", json=doc).json()
        assert preview["names"]["encoder"] == ["Film (2)", "Film", "Film"]
        assert preview["names"]["template"] == ["Manual defaults (2)"]
        client.post(
            "/api/presets/encoder", json={"label": "Film (2)", "group": encoder["group"], "data": encoder["data"]}
        )
        result = client.post("/api/preset-packs/import?keep_both=true", json=doc)
        assert result.status_code == 200, result.text
        assert result.json()["names"]["encoder"] == ["Film (3)", "Film", "Film"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda doc: doc.update(settings={"notifications": []}),
        lambda doc: doc.update(application={"plugins": {"token": "private"}}),
        lambda doc: doc.update(template_defaults={"manual": "Feature"}),
        lambda doc: doc["presets"]["encoder"][0].update(name="local-storage-id"),
        lambda doc: doc["presets"]["audio"][0].update(group=["a/b"]),
        lambda doc: doc["presets"]["audio"][0].update(data={"action": "copy", "bitrate_kbps": 128}),
        lambda doc: doc["presets"]["template"][0].update(data={"qpf": "false"}),
        lambda doc: doc.update(version=True),
        lambda doc: doc.update(version=2),
    ],
)
def test_invalid_or_private_fields_reject_whole_pack_without_writes(tmp_path, mutate):
    with make_client(tmp_path) as client:
        seed(client, tmp_path)
        before = export(client)
        doc = portable(before)
        mutate(doc)
        for action in ("export", "preview", "import"):
            response = client.post(f"/api/preset-packs/{action}", json=doc)
            assert response.status_code == 422, response.text
        assert export(client) == before


def test_pack_does_not_claim_to_scrub_user_authored_scripts_or_arguments(tmp_path):
    with make_client(tmp_path) as client:
        seed(client, tmp_path)
        doc = portable(export(client))
        doc["presets"]["template"][0]["data"]["video"]["custom"] = "api_key = 'USER_SCRIPT_TOKEN'\nclip = src"
        doc["presets"]["encoder"][0]["data"]["extra"] = "--stats private-path"
        normalized = read_preset_pack(doc)
        assert "USER_SCRIPT_TOKEN" in normalized["presets"]["template"][0]["data"]["video"]["custom"]
        assert normalized["presets"]["encoder"][0]["data"]["extra"] == "--stats private-path"


def test_empty_malformed_and_oversized_packs_are_rejected(tmp_path):
    with make_client(tmp_path) as client:
        doc = {
            "format": FORMAT,
            "version": 1,
            "presets": {kind: [] for kind in ("template", "encoder", "audio", "video")},
        }
        assert client.post("/api/preset-packs/import", json=doc).status_code == 422
        for raw in (b"{bad", b"\xff", b"[" * 2000):
            assert client.post("/api/preset-packs/import", content=raw).status_code == 422
        assert client.post("/api/preset-packs/import", content=b" " * (MAX_BYTES + 1)).status_code == 413


def test_multiple_libraries_are_atomic_and_concurrent_imports_keep_both_copies():
    store = Store(":memory:")
    libraries = {
        "template": [{"name": "Film", "data": {}}],
        "audio": [{"label": "Copy", "group": [], "data": {"action": "copy"}}],
    }
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: store.import_preset_pack(libraries, max_name=80), range(8)))
        assert len({names["template"][0] for names, _ in results}) == 8
        assert len(store.presets("template")) == len(store.presets("audio")) == 8
        before = store.configuration_snapshot((), ("template", "audio"))
        store._db.execute(
            "CREATE TRIGGER reject_pack BEFORE INSERT ON presets WHEN NEW.kind = 'audio' "
            "BEGIN SELECT RAISE(ABORT, 'forced failure'); END"
        )
        with pytest.raises(sqlite3.IntegrityError):
            store.import_preset_pack(libraries, max_name=80)
        assert store.configuration_snapshot((), ("template", "audio")) == before
    finally:
        store.close()


def test_importing_the_same_pack_again_replaces_in_place_and_adds_nothing(tmp_path):
    """A preset of the same name (an encoder or audio preset: in the same encoder or action and folder) is
    replaced, keeping its identity and a default template's place; one with the same settings is left alone."""
    with make_client(tmp_path) as client:
        seed(client, tmp_path)
        before = export(client)
        doc = portable(before)
        again = client.post("/api/preset-packs/import", json=doc).json()
        assert again["actions"] == {kind: ["unchanged"] * len(doc["presets"][kind]) for kind in doc["presets"]}
        assert export(client)["presets"] == before["presets"]

        doc["presets"]["template"][0]["data"]["qpf"] = True
        doc["presets"]["encoder"][0]["data"]["crf"] = 21
        doc["presets"]["template"].append(copy.deepcopy(doc["presets"]["template"][0]))  # the same name twice
        manual = copy.deepcopy(doc["presets"]["template"][0]) | {"name": "Manual defaults"}  # a built-in's name
        doc["presets"]["template"].append(manual)
        preview = client.post("/api/preset-packs/preview", json=doc).json()
        assert preview["names"]["template"] == ["Feature", "Feature (2)", "Manual defaults (2)"]
        assert preview["actions"]["template"] == ["replaced", "copy", "copy"]
        assert preview["actions"]["encoder"] == ["replaced"] and preview["actions"]["audio"] == ["unchanged"]
        assert export(client)["presets"] == before["presets"]  # a preview writes nothing

        client.post("/api/preset-packs/import", json=doc)
        after = export(client)
        feature = next(t for t in after["presets"]["template"] if t["name"] == "Feature")
        assert feature["data"]["qpf"] is True
        assert after["template_defaults"] == before["template_defaults"] == {"manual": "Feature"}
        (encoder,) = after["presets"]["encoder"]
        assert encoder["name"] == before["presets"]["encoder"][0]["name"] and encoder["data"]["crf"] == 21


def test_keep_both_imports_a_numbered_copy_of_each(tmp_path):
    with make_client(tmp_path) as client:
        seed(client, tmp_path)
        doc = portable(export(client))
        result = client.post("/api/preset-packs/import?keep_both=true", json=doc).json()
        assert result["names"]["template"] == ["Feature (2)"] and result["actions"]["encoder"] == ["copy"]
        assert len(client.get("/api/presets").json()["encoder"]) == 2


def test_one_library_import_replaces_too(tmp_path):
    with make_client(tmp_path) as client:
        seed(client, tmp_path)
        doc = client.post(
            "/api/presets/templates/export",
            json={
                "format": "videoforge.templates",
                "version": 1,
                "templates": [{"name": "Feature", "data": {"qpf": True}}],
            },
        ).json()
        result = client.post("/api/presets/templates/import", json=doc).json()
        assert result["names"] == ["Feature"] and result["actions"] == ["replaced"]
        assert [t["name"] for t in result["presets"]["template"]] == ["Feature"]


def test_several_presets_delete_at_once(tmp_path):
    with make_client(tmp_path) as client:
        seed(client, tmp_path)
        for name in ("Group / 1080p / Film", "Group / 1080p / Grain"):
            client.put(f"/api/presets/template/{name.replace('/', '%2F')}", json={})
        names = ["Group / 1080p / Film", "Group / 1080p / Grain", "Feature", "Gone already"]
        presets = client.post("/api/presets/delete", json={"kind": "template", "names": names}).json()
        assert (
            presets["template"] == [] and presets["template_defaults"] == {}
        )  # the default goes back to the profile's
        encoder = presets["encoder"][0]["name"]
        assert client.post("/api/presets/delete", json={"kind": "encoder", "names": [encoder]}).json()["encoder"] == []
        assert client.post("/api/presets/delete", json={"kind": "nope", "names": []}).status_code == 404
