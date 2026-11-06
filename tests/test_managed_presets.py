"""Presets a plugin ships stay current without overwriting a user's edits."""

import copy
import json

import pytest
from test_server import make_client

from videoforge.core.plan_io import to_json
from videoforge.core.template import Template
from videoforge.core.video.settings import EncoderSettings
from videoforge.server.managed_presets import digest, load_packs, read_pack
from videoforge.server.preset_pack import FORMAT, read_preset_pack
from videoforge.server.store import Store


def doc(version=1, *, templates=("remux",)):
    template = to_json(Template())
    template["qpf"] = version == 1
    return {
        "format": FORMAT,
        "version": 1,
        "presets": {
            "template": [{"key": k, "name": f"Acme {k}", "data": template} for k in templates],
            "video": [],
            "encoder": [{"key": "x265-uhd", "label": "UHD", "group": ["Acme"], "data": to_json(EncoderSettings())}],
            "audio": [],
        },
    }


def pack(d=None):
    return read_pack("acme", d or doc())


@pytest.fixture
def store():
    s = Store(":memory:")
    yield s
    s.close()


def templates(store):
    return store.presets("template")


def template_row(store):
    return next(m for m in store.managed_presets() if m["kind"] == "template")


def test_a_pack_adds_its_presets_once(store):
    first = store.use_packs([pack()], {})
    assert {(c["kind"], c["action"]) for c in first} == {("template", "new"), ("encoder", "new")}
    assert store.use_packs([pack()], {}) == []
    assert list(templates(store)) == ["Acme remux"]
    assert len(store.presets("encoder")) == 1


def test_an_untouched_preset_follows_the_pack_in_place(store):
    store.use_packs([pack()], {})
    changed = store.use_packs([pack(doc(2))], {})
    assert [(c["kind"], c["action"], c["name"]) for c in changed] == [("template", "updated", "Acme remux")]
    assert templates(store)["Acme remux"]["qpf"] is False
    assert template_row(store)["state"] == "current"


def test_an_edited_preset_is_kept_and_flags_the_update(store):
    store.use_packs([pack()], {})
    mine = {**templates(store)["Acme remux"], "qpf": "mine"}
    store.save_preset("template", "Acme remux", mine)
    assert [c["action"] for c in store.use_packs([pack(doc(2))], {})] == ["kept"]
    assert templates(store)["Acme remux"] == mine
    assert (template_row(store)["state"], template_row(store)["update_available"]) == ("edited", True)
    # the same pack again says nothing new, and the flag stays
    assert store.use_packs([pack(doc(2))], {}) == []
    assert template_row(store)["update_available"]


def test_reset_restores_the_shipped_version(store):
    store.use_packs([pack()], {})
    store.save_preset("template", "Acme remux", {"qpf": "mine"})
    store.use_packs([pack(doc(2))], {})
    assert store.reset_managed("acme", "template", "remux") == "Acme remux"
    assert templates(store)["Acme remux"]["qpf"] is False
    assert (template_row(store)["state"], template_row(store)["update_available"]) == ("current", False)


def test_a_deleted_preset_stays_deleted_until_reset(store):
    store.use_packs([pack()], {})
    store.delete_preset("template", "Acme remux")
    store.use_packs([pack(doc(2))], {})
    assert "Acme remux" not in templates(store)
    assert template_row(store)["state"] == "removed"
    store.reset_managed("acme", "template", "remux")
    assert "Acme remux" in templates(store)


def test_a_key_dropped_from_the_pack_is_retired_not_deleted(store):
    store.use_packs([pack(doc(templates=("remux", "extra")))], {})
    assert [c["action"] for c in store.use_packs([pack(doc(templates=("remux",)))], {})] == ["retired"]
    assert "Acme extra" in templates(store)
    assert next(m for m in store.managed_presets() if m["key"] == "extra")["retired"]


def test_a_name_the_user_already_has_gets_a_numbered_copy(store):
    store.save_preset("template", "Acme remux", {"qpf": "theirs"})
    assert sorted(c["action"] for c in store.use_packs([pack()], {})) == ["copy", "new"]
    assert templates(store)["Acme remux"] == {"qpf": "theirs"}
    assert "Acme remux (2)" in templates(store)


def test_an_identical_preset_the_user_already_has_is_adopted_not_copied(store):
    d = doc()
    store.save_preset("template", "Acme remux", d["presets"]["template"][0]["data"])
    store.import_encoder_presets(
        [{"label": "UHD", "group": ["Acme"], "data": d["presets"]["encoder"][0]["data"]}], max_name=80
    )
    assert sorted(c["action"] for c in store.use_packs([pack(d)], {})) == ["new", "new"]
    assert list(templates(store)) == ["Acme remux"]
    assert len(store.presets("encoder")) == 1
    assert {m["name"] for m in store.managed_presets() if m["kind"] == "template"} == {"Acme remux"}


def test_an_identical_numbered_copy_is_adopted_too(store):
    d = doc()
    store.save_preset("template", "Acme remux (2)", d["presets"]["template"][0]["data"])
    store.use_packs([pack(d)], {})
    assert list(templates(store)) == ["Acme remux (2)"]
    assert template_row(store)["name"] == "Acme remux (2)"


def test_a_reserved_name_is_not_taken(store):
    store.use_packs([pack()], {"template": ("Acme remux",)})
    assert list(templates(store)) == ["Acme remux (2)"]


def test_every_profile_and_new_profiles_get_the_presets(store):
    other = store.create_profile("Other")
    store.use_packs([pack()], {})
    store.switch_profile(other)
    assert sorted(m["key"] for m in store.managed_presets()) == ["remux", "x265-uhd"]
    third = store.create_profile("Third")
    store.switch_profile(third)
    assert len(store.managed_presets()) == 2
    copied = store.create_profile("Copy", copy_of=third)
    store.switch_profile(copied)
    assert len(store.managed_presets()) == 2
    store.switch_profile(other)
    store.delete_profile(third)


def test_a_pack_needs_a_key_on_every_entry():
    bad = doc()
    del bad["presets"]["template"][0]["key"]
    with pytest.raises(ValueError, match="needs a key"):
        pack(bad)


def test_keys_are_unique_and_dropped_from_a_users_import():
    with pytest.raises(ValueError, match="unique"):
        read_preset_pack(doc(templates=("a", "a")))
    bad = copy.deepcopy(doc())
    bad["presets"]["template"][0]["key"] = "Bad Key"
    with pytest.raises(ValueError, match="unique"):
        read_preset_pack(bad)
    imported = read_preset_pack(doc())
    assert all("key" not in e for entries in imported["presets"].values() for e in entries)
    assert read_preset_pack(doc(), keep_keys=True)["presets"]["template"][0]["key"] == "remux"


def test_digest_ignores_key_order():
    assert digest({"a": 1, "b": 2}) == digest({"b": 2, "a": 1})


def write_plugin(root, pid="acme", body=None):
    folder = root / pid
    (folder / "presets").mkdir(parents=True)
    (folder / "videoforge-plugin.toml").write_text(f'id = "{pid}"\nmodule = "x"\npresets = "presets/pack.json"\n')
    (folder / "presets" / "pack.json").write_text(json.dumps(body or doc()))
    return folder


def test_load_packs_reads_a_plugins_pack_and_reports_a_broken_one(tmp_path):
    write_plugin(tmp_path)
    write_plugin(tmp_path, "broken", body={"format": "nope"})
    packs, problems = load_packs(tmp_path)
    assert [p.plugin for p in packs] == ["acme"]
    assert len(problems) == 1 and problems[0].startswith("broken:")
    assert load_packs(tmp_path, disabled={"acme"})[0] == []


@pytest.mark.parametrize("path", ["../x.json", "/x.json", "a\\b.json", "pack.txt", "a//b.json"])
def test_manifest_presets_path_must_stay_inside_the_plugin(path):
    from videoforge.plugins.manifest import PluginError, parse_manifest

    with pytest.raises(PluginError, match="presets"):
        parse_manifest(f'id = "a"\nmodule = "a"\npresets = {json.dumps(path)}\n')


def test_the_app_syncs_at_start_and_exposes_the_state(tmp_path):
    write_plugin(tmp_path / "data" / "plugins")
    with make_client(tmp_path) as client:
        listed = client.get("/api/preset-packs/managed").json()
        assert sorted(p["key"] for p in listed["presets"]) == ["remux", "x265-uhd"]
        assert listed["problems"] == []
        assert "Acme remux" in [p["name"] for p in client.get("/api/presets").json()["template"]]
        client.put("/api/presets/template/Acme remux", json={"qpf": False, "crop_mode": "auto"})
        state = {p["key"]: p["state"] for p in client.get("/api/preset-packs/managed").json()["presets"]}
        assert state["remux"] == "edited"
        reset = client.post(
            "/api/preset-packs/managed/reset", json={"plugin": "acme", "kind": "template", "key": "remux"}
        )
        assert reset.status_code == 200, reset.text
        state = {p["key"]: p["state"] for p in client.get("/api/preset-packs/managed").json()["presets"]}
        assert state["remux"] == "current"
        missing = client.post("/api/preset-packs/managed/reset", json={"plugin": "x", "kind": "template", "key": "y"})
        assert missing.status_code == 404


def test_a_reset_or_replaced_library_gets_the_plugins_presets_back(store):
    store.use_packs([pack()], {})
    store.reset_configuration((), ("template", "video", "encoder", "audio"))
    assert list(templates(store)) == ["Acme remux"]
    assert len(store.presets("encoder")) == 1
    store.restore_configuration({}, {"template": {}, "encoder": {}})
    assert list(templates(store)) == ["Acme remux"]
    assert len(store.presets("encoder")) == 1


def test_a_settings_only_reset_keeps_a_deleted_preset_deleted(store):
    store.use_packs([pack()], {})
    store.delete_preset("template", "Acme remux")
    store.reset_configuration(("rule_set",), ())
    assert "Acme remux" not in templates(store)


def test_a_library_emptied_by_an_older_build_gets_the_presets_back(store):
    store.use_packs([pack()], {})
    store._db.execute("DELETE FROM presets")  # what a reset did before it forgot the managed rows
    store.use_packs([pack()], {})
    assert list(templates(store)) == ["Acme remux"]
    assert len(store.presets("encoder")) == 1
