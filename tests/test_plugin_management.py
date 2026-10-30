"""ZIPs remain data until restart; installation transactions survive interrupted renames."""

from dataclasses import replace
import io
import json
from pathlib import Path
import stat
import sys
import threading
import uuid
import zipfile

import pytest
from test_server import APP, make_client

from videoforge.core.events import EventBus, IndexFinished, JobFinished, JobStarted, QueueFinished
from videoforge.core.job import JobResult, JobSpec, JobStatus
from videoforge.core.models import JobInputs
from videoforge.plugins import Plugin
from videoforge.plugins.loader import LoadedPlugin, PluginHost, PluginReport
from videoforge.plugins.manager import PluginConflict, PluginManager, read_package
from videoforge.plugins.manifest import MANIFEST, PluginError, parse_manifest, read_manifest
from videoforge.server.settings import ServerSettings


def zip_files(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return stream.getvalue()


def plugin_zip(*, version="1.0", pid="example", module=None, code=None, settings="", prefix=""):
    module = module or f"vf_test_{uuid.uuid4().hex}"
    manifest = (
        f'id = "{pid}"\nmodule = "{module}"\nname = "Example"\nversion = "{version}"\n'
        f'api_version = 1\ndescription = "Test plugin"\n{settings}'
    )
    code = code or f'from videoforge.plugins import Plugin\nplugin = Plugin("Example", version="{version}")\n'
    return zip_files({prefix + MANIFEST: manifest, prefix + module + ".py": code})


FIELDS = """
[[settings]]
key = "url"
label = "Server URL"
default = "http://default"
required = true
[[settings]]
key = "token"
label = "API key"
type = "password"
[[settings]]
key = "enabled"
type = "checkbox"
default = true
[[settings]]
key = "count"
type = "integer"
default = 2
[[settings]]
key = "when"
type = "choice"
choices = ["job", "queue"]
default = "queue"
"""


@pytest.mark.parametrize("prefix", ["", "example/"])
def test_preview_and_stage_never_import_python(tmp_path, prefix):
    marker = tmp_path / "executed"
    raw = plugin_zip(
        code=f"from pathlib import Path\nPath({str(marker)!r}).touch()\nraise SystemExit(7)", prefix=prefix
    )
    with make_client(tmp_path) as client:
        preview = client.post("/api/plugins/preview", content=raw)
        assert preview.status_code == 200, preview.text
        assert preview.json()["revision"] == "absent"
        installed = client.post("/api/plugins/import?revision=absent", content=raw)
        assert installed.status_code == 200, installed.text
        item = installed.json()["items"][0]
        assert item["pending"] == "install" and item["enabled"] and not item["running"]
        assert installed.json()["restart"]
        assert not (tmp_path / "data" / "plugins" / "example").exists()
        assert not marker.exists()
    with make_client(tmp_path) as client:
        assert marker.exists()
        assert "exited" in client.get("/api/plugins").json()["items"][0]["error"]
        assert client.get("/api/health").status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        "../escape.py",
        "/absolute.py",
        "C:/escape.py",
        "pkg\\escape.py",
        "aux.py",
        "a./b.py",
        "a /b.py",
        "a//b.py",
        "pkg/../b.py",
    ],
)
def test_unsafe_zip_names_are_rejected(path):
    raw = zip_files({path: "bad"})
    if "\\" in path:
        # ZipInfo normalises the local OS separator; corrupt both stored filename copies instead.
        raw = raw.replace(path.replace("\\", "/").encode(), path.encode())
    with pytest.raises(PluginError, match="Unsafe archive path"):
        read_package(raw)


def test_duplicates_links_and_implicit_case_collisions_are_rejected():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        info = zipfile.ZipInfo("link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, "../outside")
    with pytest.raises(PluginError, match="links"):
        read_package(stream.getvalue())
    for files in ({"pkg/a.py": "", "Pkg/b.py": ""}, {"file": "", "file/sub.py": ""}):
        with pytest.raises(PluginError):
            read_package(zip_files(files))
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("same", "one")
        with pytest.warns(UserWarning):
            archive.writestr("same", "two")
    with pytest.raises(PluginError, match="Duplicate"):
        read_package(stream.getvalue())


def test_zip_limits_invalid_modules_and_api(monkeypatch):
    import videoforge.plugins.manager as manager

    raw = plugin_zip()
    monkeypatch.setattr(manager, "MAX_ZIP_BYTES", 1)
    with pytest.raises(PluginError, match="50 MiB"):
        read_package(raw)
    monkeypatch.setattr(manager, "MAX_ZIP_BYTES", len(raw))
    monkeypatch.setattr(manager, "MAX_ENTRIES", 1)
    with pytest.raises(PluginError, match="entries"):
        read_package(raw)
    monkeypatch.setattr(manager, "MAX_ENTRIES", 5000)
    monkeypatch.setattr(manager, "MAX_EXTRACTED_BYTES", 1)
    with pytest.raises(PluginError, match="250 MiB"):
        read_package(raw)
    with pytest.raises(PluginError):
        read_package(b"not a zip")
    with pytest.raises(PluginError):
        parse_manifest('id="test"\nmodule="test"\nname="Test"\nversion="1"\napi_version=99', package=True)
    with pytest.raises(PluginError):
        parse_manifest('id="../test"\nmodule="test"\nname="Test"\nversion="1"\napi_version=1', package=True)


def test_replace_and_remove_preserve_data_and_require_fresh_preview(tmp_path):
    manager = PluginManager(tmp_path)
    first = read_package(plugin_zip())
    manager.stage_install(first, "absent")
    manager.apply_pending()
    target = manager.folder / "example"
    data = tmp_path / "plugin-data" / "example"
    data.mkdir(parents=True)
    (data / "state").write_text("keep")
    replacement = read_package(plugin_zip(version="2.0"))
    preview = manager.preview(replacement)
    with pytest.raises(PluginConflict, match="Replace"):
        manager.stage_install(replacement, preview["revision"])
    (target / "extra.txt").write_text("changed")
    with pytest.raises(PluginConflict, match="changed"):
        manager.stage_install(replacement, preview["revision"], replace=True)
    revision = manager.preview(replacement)["revision"]
    manager.stage_install(replacement, revision, replace=True)
    assert read_manifest(target / MANIFEST).version == "1.0"
    with pytest.raises(PluginConflict, match="pending"):
        manager.stage_remove("example", revision)
    manager.apply_pending()
    assert read_manifest(target / MANIFEST).version == "2.0"
    revision = manager.preview(replacement)["revision"]
    manager.stage_remove("example", revision)
    assert target.exists()
    manager.apply_pending()
    assert not target.exists() and (data / "state").read_text() == "keep"
    assert not manager.pending()


@pytest.mark.parametrize("interruption", ["old_renamed", "new_renamed", "remove_renamed"])
def test_recover_interrupted_directory_swaps(tmp_path, interruption):
    manager = PluginManager(tmp_path)
    package = read_package(plugin_zip())
    manager.stage_install(package, "absent")
    manager.apply_pending()
    target = manager.folder / "example"
    revision = manager.preview(package)["revision"]
    if interruption == "remove_renamed":
        manager.stage_remove("example", revision)
    else:
        manager.stage_install(read_package(plugin_zip(version="2.0")), revision, replace=True)
    operation, _ = manager.pending()[0]
    target.rename(operation / "old")
    if interruption == "new_renamed":
        (operation / "new").rename(target)
    recovered = PluginManager(tmp_path)
    recovered.apply_pending()
    assert recovered.startup_failures == [] and not recovered.pending()
    if interruption == "remove_renamed":
        assert not target.exists()
    else:
        assert read_manifest(target / MANIFEST).version == "2.0"


def test_failed_swap_restores_previous_files(tmp_path, monkeypatch):
    manager = PluginManager(tmp_path)
    package = read_package(plugin_zip())
    manager.stage_install(package, "absent")
    manager.apply_pending()
    manager.stage_install(read_package(plugin_zip(version="2.0")), manager.preview(package)["revision"], replace=True)
    rename = Path.rename

    def blocked(path, destination):
        if path.name == "new":
            raise PermissionError("in use")
        return rename(path, destination)

    monkeypatch.setattr(Path, "rename", blocked)
    manager.apply_pending()
    assert read_manifest(manager.folder / "example" / MANIFEST).version == "1.0"
    assert manager.startup_failures and manager.pending()


def test_committed_cleanup_is_retried_without_reapplying_changes(tmp_path, monkeypatch):
    import videoforge.plugins.manager as implementation

    manager = PluginManager(tmp_path)
    manager.stage_install(read_package(plugin_zip()), "absent")
    remove = implementation.shutil.rmtree

    def interrupted(path, *args, **kwargs):
        if Path(path).name.startswith(".done-"):
            raise PermissionError("interrupted cleanup")
        return remove(path, *args, **kwargs)

    monkeypatch.setattr(implementation.shutil, "rmtree", interrupted)
    manager.apply_pending()
    assert manager.startup_failures == [] and not manager.pending()
    assert list(manager.staging.glob(".done-*"))
    monkeypatch.setattr(implementation.shutil, "rmtree", remove)
    PluginManager(tmp_path).apply_pending()
    assert list(manager.staging.iterdir()) == []
    assert read_manifest(manager.folder / "example" / MANIFEST).version == "1.0"


def test_settings_forms_precedence_passwords_and_restart(tmp_path):
    module = f"vf_test_{uuid.uuid4().hex}"
    code = """from videoforge.plugins import Plugin
def setup(ctx):
    import json
    (ctx.data_dir / "settings.json").write_text(json.dumps(dict(ctx.settings)))
plugin = Plugin("Example", setup=setup)
"""
    raw = plugin_zip(module=module, code=code, settings=FIELDS)
    with make_client(tmp_path) as client:
        assert client.post("/api/plugins/import?revision=absent", content=raw).status_code == 200
        client.app.state.base_config = replace(APP, plugins={"example": {"url": "http://toml", "private": "preserved"}})
        inventory = client.get("/api/plugins").json()
        assert inventory["items"][0]["values"]["url"] == "http://toml"
        response = client.put("/api/plugins/example/settings", json={"values": {"url": "http://ui", "token": "SECRET"}})
        assert response.status_code == 200, response.text
        assert "SECRET" not in response.text
        assert response.json()["items"][0]["configured_passwords"] == ["token"]
        assert client.put("/api/plugins/example/settings", json={"values": {"count": True}}).status_code == 422
        assert client.put("/api/plugins/example/settings", json={"values": {"url": ""}}).status_code == 422
        assert client.put("/api/plugins/example/settings", json={"values": {"unknown": "x"}}).status_code == 422
        assert client.put("/api/plugins/example/settings", json={"values": {"when": "bad"}}).status_code == 422
        assert client.put("/api/plugins/example/settings", json={"values": {"count": 5}}).status_code == 200
        # Ordinary settings saves must retain plugin overrides.
        client.put("/api/config", json={"parallel_audio": 3})
        saved = client.app.state.saved.plugin_settings["example"]
        assert saved == {"url": "http://ui", "token": "SECRET", "count": 5}
        assert client.get("/api/configuration/export").json()["settings"]["plugin_settings"]["example"] == saved
    with make_client(tmp_path) as client:
        client.app.state.plugins.wait()
        settings = json.loads((tmp_path / "data" / "plugin-data" / "example" / "settings.json").read_text())
        assert settings["url"] == "http://ui" and settings["when"] == "queue"
        assert settings["token"] == saved["token"]
        assert client.get("/api/plugins").json()["items"][0]["running"]
        result = client.put("/api/plugins/example/settings", json={"values": {}, "reset": ["url"]})
        assert result.status_code == 200 and result.json()["items"][0]["values"]["url"] == "http://default"
        client.put("/api/config", json={"disabled_plugins": ["missing"]})
        assert client.put("/api/plugins/example/enabled", json={"enabled": False}).status_code == 200
        assert client.app.state.saved.disabled_plugins == ["example", "missing"]
    sys.modules.pop(module, None)


def test_old_backups_upgrade_and_management_is_not_transferable(tmp_path):
    with make_client(tmp_path) as client:
        bundle = client.get("/api/configuration/export").json()
        assert bundle["version"] == 4
        bundle["version"] = 1
        del bundle["settings"]["plugin_settings"], bundle["settings"]["sample_quality"], bundle["subs_default"]
        response = client.post("/api/configuration/import", json=bundle)
        assert response.status_code == 200, response.text
        assert client.app.state.saved.plugin_settings == {}
        assert "plugin_management" not in client.get("/api/configuration/export").text
        client.app.state.settings.plugin_management = False
        raw = plugin_zip()
        for path in ("/preview", "/import?revision=absent"):
            assert client.post("/api/plugins" + path, content=raw).status_code == 403
        assert client.delete("/api/plugins/example?revision=absent").status_code == 403
        assert client.put("/api/plugins/example/settings", json={"values": {}}).status_code == 403
        assert client.get("/api/plugins").json()["management_enabled"] is False
    assert ServerSettings().can_manage_plugins
    assert ServerSettings(host="::1").can_manage_plugins
    assert not ServerSettings(host="0.0.0.0").can_manage_plugins  # noqa: S104
    assert ServerSettings(host="0.0.0.0", plugin_management=True).can_manage_plugins  # noqa: S104


def test_server_restart_activation_events_replacement_and_removal(tmp_path):
    module = f"vf_test_{uuid.uuid4().hex}"
    code = """from videoforge.plugins import Plugin
def event(event, ctx):
    with (ctx.data_dir / "events.txt").open("a") as stream:
        stream.write(type(event).__name__ + "\\n")
plugin = Plugin("Example", version="1.0", on_job_started=event, on_index_finished=event,
                on_job_finished=event, on_queue_finished=event)
"""
    raw = plugin_zip(module=module, code=code)
    with make_client(tmp_path) as client:
        assert client.post("/api/plugins/import?revision=absent", content=raw).status_code == 200
    with make_client(tmp_path) as client:
        spec = JobSpec(id="one", profile="manual", inputs=JobInputs(source=tmp_path / "source.mkv"))
        for event in (
            JobStarted(spec, None),
            IndexFinished(spec),
            JobFinished(spec, JobResult(None, JobStatus.DONE), 1),
            QueueFinished((JobStatus.DONE,), 1),
        ):
            client.app.state.queue.bus.emit(event)
        client.app.state.plugins.wait()
        events = tmp_path / "data" / "plugin-data" / "example" / "events.txt"
        assert events.read_text().splitlines() == ["JobStarted", "IndexFinished", "JobFinished", "QueueFinished"]
        replacement = plugin_zip(version="2.0")
        preview = client.post("/api/plugins/preview", content=replacement).json()
        assert (
            client.post(
                "/api/plugins/import", params={"revision": preview["revision"]}, content=replacement
            ).status_code
            == 409
        )
        response = client.post(
            "/api/plugins/import", params={"revision": preview["revision"], "replace": True}, content=replacement
        )
        assert response.status_code == 200, response.text
        item = response.json()["items"][0]
        assert item["running_version"] == "1.0" and item["version"] == "2.0" and item["pending"] == "replace"
    with make_client(tmp_path) as client:
        item = client.get("/api/plugins").json()["items"][0]
        assert item["running_version"] == "2.0" and item["pending"] is None
        response = client.delete("/api/plugins/example", params={"revision": item["revision"]})
        assert response.status_code == 200, response.text
        assert response.json()["items"][0]["running"] and response.json()["items"][0]["pending"] == "remove"
    with make_client(tmp_path) as client:
        assert client.get("/api/plugins").json()["items"] == []
        assert events.exists()
    sys.modules.pop(module, None)


def test_invalid_imports_and_encrypted_entries_never_change_files(tmp_path):
    with make_client(tmp_path) as client:
        before = client.get("/api/plugins").json()
        for action in ("/preview", "/import?revision=absent"):
            response = client.post("/api/plugins" + action, content=zip_files({"../outside.py": "bad"}))
            assert response.status_code == 422
        assert client.get("/api/plugins").json() == before
        assert not client.app.state.plugin_manager.staging.exists()
    raw = bytearray(zip_files({"file.py": "bad"}))
    # Set the encrypted bit in the central header (the local header need not be decoded).
    central = raw.index(b"PK\x01\x02")
    raw[central + 8] |= 1
    with pytest.raises(PluginError, match="Encrypted"):
        read_package(bytes(raw))


def test_invalid_staging_metadata_does_not_prevent_server_start(tmp_path):
    staging = tmp_path / "data" / "plugin-staging" / "interrupted"
    staging.mkdir(parents=True)
    (staging / "operation.json").write_text('{"id": 3}')
    with make_client(tmp_path) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/plugins").json()["failures"]


def test_event_logger_controls_use_ids_in_json_and_preserve_restart_behavior(tmp_path):
    raw = plugin_zip(pid="event_logger", settings=FIELDS)
    with make_client(tmp_path) as client:
        assert client.post("/api/plugins/import?revision=absent", content=raw).status_code == 200
    with make_client(tmp_path) as client:
        for enabled in (False, True):
            response = client.put("/api/plugins/enabled", json={"id": "event_logger", "enabled": enabled})
            assert response.status_code == 200, response.text
            item = response.json()["items"][0]
            assert item["enabled"] is enabled and item["running"]
            assert ("event_logger" in client.app.state.saved.disabled_plugins) is not enabled
        response = client.put("/api/plugins/settings", json={"id": "event_logger", "values": {"count": 4}})
        assert response.status_code == 200, response.text
        assert response.json()["items"][0]["values"]["count"] == 4
        assert client.app.state.saved.plugin_settings["event_logger"] == {"count": 4}
        revision = response.json()["items"][0]["revision"]
        response = client.post("/api/plugins/remove", json={"id": "event_logger", "revision": revision})
        assert response.status_code == 200, response.text
        assert response.json()["items"][0]["pending"] == "remove"
    with make_client(tmp_path) as client:
        assert client.get("/api/plugins").json()["items"] == []
        assert client.app.state.saved.plugin_settings["event_logger"] == {"count": 4}


@pytest.mark.parametrize(
    "path,method,body",
    [
        ("/enabled", "put", {"enabled": True}),
        ("/enabled", "put", {"id": 4, "enabled": True}),
        ("/enabled", "put", {"id": "example", "enabled": "yes"}),
        ("/settings", "put", {"values": {}}),
        ("/remove", "post", {"id": "example"}),
        ("/remove", "post", {"id": "example", "revision": 4}),
    ],
)
def test_id_in_body_endpoints_validate_requests_and_obey_management_gate(tmp_path, path, method, body):
    with make_client(tmp_path) as client:
        send = getattr(client, method)
        assert send("/api/plugins" + path, json=body).status_code == 422
        client.app.state.settings.plugin_management = False
        assert send("/api/plugins" + path, json=body).status_code == 403


def test_each_plugin_gets_independent_snapshots_and_slow_handlers_do_not_block(tmp_path):
    bus = EventBus()
    blocked, release = threading.Event(), threading.Event()
    seen = []

    def mutate(event, _ctx):
        event.spec.label = "changed"
        blocked.set()
        release.wait(5)

    def observe(event, _ctx):
        seen.append(event.spec.label)

    spec = JobSpec(id="one", profile="manual", inputs=JobInputs(source=tmp_path / "source.mkv"))
    report = PluginReport(
        loaded=(
            LoadedPlugin("slow", Plugin("Slow", on_job_started=mutate), ""),
            LoadedPlugin("fast", Plugin("Fast", on_job_started=observe), ""),
        )
    )
    host = PluginHost(report, bus, data_dir=tmp_path / "data")
    try:
        bus.emit(JobStarted(spec, None))
        assert blocked.wait(2)
        host._pools["fast"].submit(lambda: None).result(timeout=2)
        assert seen == [""] and spec.label == ""
    finally:
        release.set()
        host.wait()
        host.close()


def test_four_slots_order_callback_failure_and_failed_setup(tmp_path):
    seen = []

    def hook(event, _ctx):
        seen.append(type(event).__name__)
        if isinstance(event, JobStarted):
            raise SystemExit(4)

    def bad_setup(_ctx):
        raise RuntimeError("needs configuration")

    bus = EventBus()
    plugin = Plugin("Four", on_job_started=hook, on_job_finished=hook, on_queue_finished=hook, on_index_finished=hook)
    report = PluginReport(
        loaded=(
            LoadedPlugin("four", plugin, ""),
            LoadedPlugin("broken", Plugin("Broken", setup=bad_setup, on_queue_finished=hook), ""),
        )
    )
    host = PluginHost(report, bus, data_dir=tmp_path)
    spec = JobSpec(id="one", profile="manual", inputs=JobInputs(source=tmp_path / "source.mkv"))
    for event in (
        JobStarted(spec, None),
        IndexFinished(spec),
        JobFinished(spec, JobResult(None, JobStatus.DONE), 1),
        QueueFinished((JobStatus.DONE,), 1),
    ):
        bus.emit(event)
    host.wait()
    host.close()
    assert seen == ["JobStarted", "IndexFinished", "JobFinished", "QueueFinished"]
    assert "broken" in host.setup_failed and "JobStarted" in host.failures["four"]
