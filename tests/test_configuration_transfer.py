"""Full configuration backups restore libraries and preferences together, without touching jobs."""

import copy
import sqlite3

import pytest
from test_server import add, make_client, make_files, wait_for

from videoforge.core.config import AppConfig
from videoforge.core.plan_io import from_json
from videoforge.server.configuration import MAX_BYTES, read_configuration
from videoforge.server.store import Store


def export(client):
    response = client.get("/api/configuration/export")
    assert response.status_code == 200, response.text
    return response.json()


def seed(client, tmp_path):
    settings = {
        "tools": {"x264": "custom-x264", "qaac": "custom-qaac"},
        "roots": [str(tmp_path)],
        "profile": "manual",
        "parallel_audio": 4,
        "delete_work_dir": True,
        "index_waits_for_disk": False,
        "encoder_priority": "idle",
        "tool_priority": "below_normal",
        "notifications": [
            {"name": "Private", "url": "json://localhost/notify", "enabled": False, "events": ["job_done"]}
        ],
        "actions": [
            {
                "name": "Command",
                "kind": "command",
                "target": 'echo "{output}"',
                "enabled": False,
                "events": ["job_done"],
                "overwrite": False,
            }
        ],
        "disabled_plugins": ["missing-plugin"],
    }
    response = client.put("/api/config", json=settings)
    assert response.status_code == 200, response.text
    client.put("/api/settings", json={"output_dir": str(tmp_path / "output"), "last_dir": str(tmp_path)})
    client.put(
        "/api/presets/template/Feature",
        json={"qpf": False, "video": {"custom": "raise RuntimeError('never during import')"}},
    )
    client.put("/api/presets/template-default/manual", json={"name": "Feature"})
    response = client.put("/api/presets/subs-default", json={"rules": [{"languages": ["en"]}], "name_untitled": True})
    assert response.status_code == 200, response.text
    client.put("/api/presets/video/Processing", json={"custom": "clip = src"})
    for kind, data in (
        ("encoder", {"encoder": "x265", "crf": 19.5, "options": {"ref": "4"}}),
        ("audio", {"action": "aac_ffmpeg", "bitrate_kbps": 128}),
    ):
        response = client.post(f"/api/presets/{kind}", json={"label": "Film", "group": ["1080p", "SDR"], "data": data})
        assert response.status_code == 200, response.text


def test_export_preview_restore_and_restart_preserve_entire_configuration(tmp_path):
    with make_client(tmp_path) as client:
        seed(client, tmp_path)
        original = export(client)
        assert {kind: len(entries) for kind, entries in original["presets"].items()} == {
            "template": 1,
            "video": 1,
            "encoder": 1,
            "audio": 1,
        }
        original["application"]["matching"]["encode_suffixes"] = ["_custom", ""]
        original["application"]["plugins"] = {"library": {"token": "secret", "nested": {"enabled": True}}}
        original["application"]["allow_commands"] = True
        client.put("/api/presets/template/Local", json={})
        before = export(client)
        preview = client.post("/api/configuration/preview", json=original)
        assert preview.status_code == 200, preview.text
        assert preview.json()["counts"] == {"template": 1, "video": 1, "encoder": 1, "audio": 1}
        assert preview.json()["current_counts"]["template"] == 2
        assert export(client) == before
        response = client.post("/api/configuration/import", json=original)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["presets"]["template_defaults"] == {"manual": "Feature"}
        assert result["presets"]["subs_default"]["rules"][0]["languages"] == ["en"]
        assert result["presets"]["subs_default"]["name_untitled"] is True
        assert result["config"]["parallel_audio"] == 4
        assert result["config"]["allow_commands"] is True
        assert any("plugin settings" in text for text in result["config"]["restart"])
        assert client.app.state.actions.allow_commands is True
        assert client.app.state.queue.app.matching.encode_suffixes == ("_custom", "")
        assert export(client) == original
    with make_client(tmp_path) as client:
        assert export(client) == original
        assert client.app.state.config.plugins == original["application"]["plugins"]
        assert client.app.state.config.matching.encode_suffixes == ("_custom", "")
        assert client.get("/api/config").json()["restart"] == []
        assert client.get("/api/settings").json() == original["folders"]


def test_a_version_2_backup_has_no_default_subtitle_rules(tmp_path):
    with make_client(tmp_path) as client:
        seed(client, tmp_path)
        old = export(client)
        old["version"] = 2
        with pytest.raises(ValueError, match="missing or unknown fields"):
            read_configuration(old)  # version 2 had no subs_default
        del old["subs_default"]
        assert read_configuration(old)["subs_default"] is None
        assert client.post("/api/configuration/import", json=old).json()["presets"]["subs_default"] is None


def test_restore_empty_libraries_preserves_jobs_and_queue_bookkeeping(tmp_path):
    make_files(tmp_path)
    with make_client(tmp_path) as client:
        empty = export(client)
        seed(client, tmp_path)
        job = add(client, tmp_path)[0]
        wait_for(client, job, "ready", "warn", "blocked")
        before = client.get(f"/api/jobs/{job}").json()["spec"]
        client.app.state.store.set_setting("queue-order-test", [job])
        response = client.post("/api/configuration/import", json=empty)
        assert response.status_code == 200, response.text
        for kind in empty["presets"]:
            assert response.json()["presets"][kind] == []
        assert response.json()["presets"]["template_defaults"] == {}
        assert client.get(f"/api/jobs/{job}").json()["spec"] == before
        assert client.app.state.store.get_setting("queue-order-test") == [job]
        assert client.app.state.store.load_jobs()[0].spec.id == job


@pytest.mark.parametrize(
    "location,value",
    [
        (("version",), True),
        (("version",), 4),
        (("subs_default",), {"rules": [], "others": "everything"}),
        (("settings", "parallel_audio"), True),
        (("settings", "parallel_audio"), 99),
        (("settings", "actions"), [{"name": "bad"}]),
        (("settings", "notifications"), [{"name": "bad", "url": "invalid"}]),
        (("settings", "index_waits_for_disk"), "false"),
        (("settings", "disabled_plugins"), "plugin"),
        (("application", "matching", "encode_suffixes"), [4]),
        (("application", "plugins"), {"bad": []}),
        (("application", "parallel_audio"), 9),
        (("template_defaults",), {"manual": "Missing"}),
        (("folders", "output_dir"), 4),
        (("presets", "template"), [{"name": "bad", "data": {"qpf": "false"}}]),
        (("presets", "encoder"), [{"name": "id", "label": "Bad", "group": ["a/b"], "data": {}}]),
        (
            ("presets", "audio"),
            [{"name": "id", "label": "Bad", "group": [], "data": {"action": "copy", "bitrate_kbps": 128}}],
        ),
    ],
)
def test_invalid_backup_is_rejected_without_partial_changes(tmp_path, location, value):
    with make_client(tmp_path) as client:
        seed(client, tmp_path)
        before = export(client)
        bad = copy.deepcopy(before)
        target = bad
        for key in location[:-1]:
            target = target[key]
        target[location[-1]] = value
        for action in ("preview", "import"):
            response = client.post(f"/api/configuration/{action}", json=bad)
            assert response.status_code == 422, response.text
        assert export(client) == before


def test_missing_profiles_and_folders_are_previewed_and_can_be_restored(tmp_path):
    with make_client(tmp_path) as client:
        doc = export(client)
        doc["settings"]["profile"] = "not-installed"
        doc["settings"]["roots"] = [str(tmp_path / "not-mounted")]
        result = client.post("/api/configuration/preview", json=doc)
        assert result.status_code == 200, result.text
        assert any("not-installed" in warning for warning in result.json()["warnings"])
        assert any("not-mounted" in warning for warning in result.json()["warnings"])
        assert client.post("/api/configuration/import", json=doc).status_code == 200
        assert client.get("/api/config").json()["profile"] == "manual"
        assert export(client)["settings"]["profile"] == "not-installed"


def test_legacy_grouped_presets_and_deleted_defaults_export_cleanly(tmp_path):
    with make_client(tmp_path) as client:
        client.put("/api/presets/encoder/Legacy", json={"crf": 22})
        client.put("/api/presets/audio/Legacy", json={"action": "copy"})
        client.app.state.store.set_setting("template_defaults", {"manual": "Deleted template"})
        doc = export(client)
        assert doc["template_defaults"] == {}
        assert doc["presets"]["encoder"][0]["label"] == "Legacy"
        assert doc["presets"]["audio"][0]["group"] == []
        assert client.post("/api/configuration/import", json=doc).status_code == 200
        assert export(client) == doc


def test_unknown_fields_duplicates_and_unsupported_files_are_rejected(tmp_path):
    with make_client(tmp_path) as client:
        seed(client, tmp_path)
        original = export(client)
        for modify in (
            lambda doc: doc.update(jobs=[]),
            lambda doc: doc["settings"].update(unknown=True),
            lambda doc: doc["presets"]["encoder"].append(copy.deepcopy(doc["presets"]["encoder"][0])),
            lambda doc: doc["presets"]["audio"].append(doc["presets"]["audio"][0] | {"name": "other-id"}),
        ):
            bad = copy.deepcopy(original)
            modify(bad)
            with pytest.raises(ValueError):
                read_configuration(bad)
        for raw in (b"{broken", b"\xff", b"[" * 2000):
            assert client.post("/api/configuration/import", content=raw).status_code == 422
        assert client.post("/api/configuration/import", content=b" " * (MAX_BYTES + 1)).status_code == 413
        assert export(client) == original


def test_storage_rolls_back_libraries_and_settings_on_failure():
    store = Store(":memory:")
    try:
        store.save_preset("encoder", "original", {"crf": 18})
        store.set_setting("profile", "manual")
        store._db.execute(
            "CREATE TRIGGER reject_restore BEFORE INSERT ON settings WHEN NEW.key = 'fail' "
            "BEGIN SELECT RAISE(ABORT, 'forced failure'); END"
        )
        with pytest.raises(sqlite3.IntegrityError):
            store.restore_configuration({"profile": "other", "fail": True}, {"encoder": {"new": {"crf": 22}}})
        assert store.presets("encoder") == {"original": {"crf": 18}}
        assert store.get_setting("profile") == "manual"
    finally:
        store.close()


def test_configuration_codec_restores_matching_rules_as_tuples(tmp_path):
    with make_client(tmp_path) as client:
        doc = export(client)
    app = from_json(AppConfig, doc["application"])
    assert isinstance(app.matching.encode_extensions, tuple)
