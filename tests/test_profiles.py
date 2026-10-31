"""Profiles: each a whole configuration (settings, templates, preset libraries), one active; jobs are shared."""

import json
import sqlite3

import pytest
from test_configuration_transfer import export, seed
from test_server import add, make_client, make_files

from videoforge.server.store import FIRST_PROFILE, ProfileInUse, Store


def test_a_store_from_before_profiles_becomes_the_first_profile(tmp_path):
    db = tmp_path / "videoforge.db"
    old = sqlite3.connect(db)
    old.executescript(
        "CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);"
        "CREATE TABLE presets (kind TEXT NOT NULL, name TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY (kind, name));"
    )
    old.executemany(
        "INSERT INTO settings VALUES (?, ?)",
        [("tools", json.dumps({"x264": "my-x264"})), ("profile", '"manual"'), ("index_lane", '["a", "b"]')],
    )
    old.execute("INSERT INTO presets VALUES ('template', 'Film', '{}')")
    old.commit()
    old.close()
    store = Store(db)
    assert [p["name"] for p in store.profiles()] == [FIRST_PROFILE]
    assert store.get_setting("tools") == {"x264": "my-x264"}
    assert store.get_setting("rule_set") == "manual" and store.get_setting("profile") is None
    assert store.presets("template") == {"Film": {}}
    assert store.get_global("index_lane") == ["a", "b"] and store.get_setting("index_lane") is None
    store.close()
    store = Store(db)  # opened again: nothing to migrate, same profile
    assert [p["name"] for p in store.profiles()] == [FIRST_PROFILE] and store.presets("template") == {"Film": {}}
    store.close()


def test_profiles_keep_their_own_settings_and_presets(tmp_path):
    db = tmp_path / "videoforge.db"
    store = Store(db)
    first = store.profile
    store.set_setting("tools", {"x264": "mine"})
    store.save_preset("template", "Film", {"qpf": False})
    fresh = store.create_profile("Clean")
    copy = store.create_profile("Copy", copy_of=first)
    store.switch_profile(fresh)
    assert store.get_setting("tools") is None and store.presets("template") == {}  # a fresh install's
    store.save_preset("template", "Anime", {})
    store.switch_profile(copy)
    assert store.get_setting("tools") == {"x264": "mine"} and store.presets("template") == {"Film": {"qpf": False}}
    store.close()
    store = Store(db)
    assert store.profile == copy  # the active profile is kept
    assert [p["name"] for p in store.profiles()] == [FIRST_PROFILE, "Clean", "Copy"]
    store.switch_profile(first)
    assert store.presets("template") == {"Film": {"qpf": False}}  # Anime went into Clean only
    store.close()


def test_profile_names_and_what_cant_be_deleted():
    store = Store(":memory:")
    only = store.profile
    with pytest.raises(ProfileInUse, match="last profile"):
        store.delete_profile(only)
    other = store.create_profile("  Work  ")
    assert store.profiles()[1] == {"id": other, "name": "Work"}
    for name in ("", "   ", "x" * 81, "work", FIRST_PROFILE.upper()):
        with pytest.raises(ValueError):
            store.create_profile(name)
    with pytest.raises(ValueError):
        store.rename_profile(other, FIRST_PROFILE)
    store.rename_profile(other, "WORK")  # its own name in another case
    with pytest.raises(ProfileInUse, match="Switch to another"):
        store.delete_profile(only)
    with pytest.raises(KeyError):
        store.switch_profile("nope")
    store.save_preset("template", "Kept", {})
    store.switch_profile(other)
    store.delete_profile(only)
    assert [p["id"] for p in store.profiles()] == [other] and store.presets("template") == {}
    store.close()


def test_switching_profiles_applies_their_settings_and_keeps_the_queue(tmp_path):
    make_files(tmp_path)
    with make_client(tmp_path) as client:
        seed(client, tmp_path)
        jobs = add(client, tmp_path)  # (adding saves its output folder)
        original = export(client)
        listing = client.get("/api/profiles").json()
        first = listing["active"]
        listing = client.post("/api/profiles", json={"name": "Clean"}).json()
        clean = listing["profiles"][1]["id"]
        assert listing["active"] == first
        assert client.post("/api/profiles", json={"name": "clean"}).status_code == 422

        switched = client.post(f"/api/profiles/{clean}/activate").json()
        assert switched["active"] == clean
        assert all(t["custom"] is None for t in switched["config"]["tools"])  # videoforge.toml's
        assert switched["config"]["parallel_audio"] == 2 and switched["presets"]["template"] == []
        assert client.app.state.queue.app.parallel_audio == 2
        assert [j["id"] for j in client.get("/api/jobs").json()] == jobs  # one queue for every profile
        assert client.delete(f"/api/profiles/{clean}").status_code == 409  # the active one

        copied = client.post("/api/profiles", json={"name": "Copy of Clean", "copy": True}).json()
        assert [p["name"] for p in copied["profiles"]] == [FIRST_PROFILE, "Clean", "Copy of Clean"]
        assert client.patch(f"/api/profiles/{clean}", json={"name": "Fresh"}).json()["profiles"][1]["name"] == "Fresh"

        back = client.post(f"/api/profiles/{first}/activate").json()
        assert back["config"]["parallel_audio"] == 4
        assert export(client) == original
        assert client.delete(f"/api/profiles/{clean}").json()["profiles"][1]["name"] == "Copy of Clean"
        assert client.post("/api/profiles/nope/activate").status_code == 404
    with make_client(tmp_path) as client:  # restarted: still the first profile's settings
        assert export(client) == original


def test_switching_waits_for_the_queue(tmp_path):
    with make_client(tmp_path) as client:
        other = client.post("/api/profiles", json={"name": "Other"}).json()["profiles"][1]["id"]
        client.app.state.queue._active = True  # as while the queue runs
        try:
            assert client.post(f"/api/profiles/{other}/activate").status_code == 409
        finally:
            client.app.state.queue._active = False
        assert client.post(f"/api/profiles/{other}/activate").json()["active"] == other
