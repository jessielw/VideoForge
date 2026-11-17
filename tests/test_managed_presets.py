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


def test_reset_restores_the_shipped_version(store):
    store.use_packs([pack()], {})
    store.save_preset("template", "Acme remux", {"qpf": "mine"})
    store.use_packs([pack(doc(2))], {})
    assert store.reset_managed("acme", "template", "remux") == "Acme remux"
    assert templates(store)["Acme remux"]["qpf"] is False
    assert (template_row(store)["state"], template_row(store)["update_available"]) == ("current", False)


def test_a_key_dropped_from_the_pack_is_retired_not_deleted(store):
    store.use_packs([pack(doc(templates=("remux", "extra")))], {})
    assert [c["action"] for c in store.use_packs([pack(doc(templates=("remux",)))], {})] == ["retired"]
    assert "Acme extra" in templates(store)
    assert next(m for m in store.managed_presets() if m["key"] == "extra")["retired"]


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


def test_a_library_emptied_by_an_older_build_gets_the_presets_back(store):
    store.use_packs([pack()], {})
    store._db.execute("DELETE FROM presets")  # what a reset did before it forgot the managed rows
    store.use_packs([pack()], {})
    assert list(templates(store)) == ["Acme remux"]
    assert len(store.presets("encoder")) == 1


def row(store, kind="template"):
    return next(m for m in store.managed_presets() if m["kind"] == kind)


def shipped_template(version=1):
    return doc(version)["presets"]["template"][0]["data"]


def test_an_edited_preset_is_put_back_at_the_next_start(store):
    store.use_packs([pack()], {})
    store.save_preset("template", "Acme remux", {"qpf": "mine"})
    assert (template_row(store)["state"], template_row(store)["stale"]) == ("edited", True)
    assert [c["action"] for c in store.use_packs([pack()], {})] == ["updated"]
    assert templates(store)["Acme remux"] == shipped_template()
    assert (template_row(store)["state"], template_row(store)["stale"]) == ("current", False)


def test_an_edited_preset_takes_a_newer_pack_too(store):
    store.use_packs([pack()], {})
    store.save_preset("template", "Acme remux", {"qpf": "mine"})
    store.use_packs([pack(doc(2))], {})
    assert templates(store)["Acme remux"] == shipped_template(2)


def test_a_deleted_preset_comes_back(store):
    store.use_packs([pack()], {})
    store.delete_preset("template", "Acme remux")
    assert (template_row(store)["state"], template_row(store)["stale"]) == ("removed", True)
    assert [c["action"] for c in store.use_packs([pack()], {})] == ["restored"]
    assert templates(store)["Acme remux"] == shipped_template()


def test_reset_puts_one_back_before_the_next_start(store):
    store.use_packs([pack()], {})
    store.delete_preset("template", "Acme remux")
    assert store.reset_managed("acme", "template", "remux") == "Acme remux"
    assert template_row(store)["state"] == "current"


def test_the_users_preset_with_its_name_is_taken_over_not_numbered(store):
    store.save_preset("template", "Acme remux", {"qpf": "theirs"})
    actions = {c["kind"]: c["action"] for c in store.use_packs([pack()], {})}
    assert actions == {"template": "took over", "encoder": "new"}
    assert templates(store) == {"Acme remux": shipped_template()}
    assert template_row(store)["name"] == "Acme remux"


def test_an_identical_preset_the_user_already_has_is_taken_over_silently(store):
    d = doc()
    store.save_preset("template", "Acme remux", d["presets"]["template"][0]["data"])
    store.import_encoder_presets(
        [{"label": "UHD", "group": ["Acme"], "data": d["presets"]["encoder"][0]["data"]}], max_name=80
    )
    store.use_packs([pack(d)], {})
    assert list(templates(store)) == ["Acme remux"]
    assert len(store.presets("encoder")) == 1
    assert {m["state"] for m in store.managed_presets()} == {"current"}


def test_a_numbered_copy_beside_the_users_preset_folds_into_it(store):
    # what an older VideoForge left: the plugin's as "(2)" beside the user's own older copy, the default on the copy
    store.use_packs([pack()], {"template": ("Acme remux",)})
    assert list(templates(store)) == ["Acme remux (2)"]
    store.set_setting("template_defaults", {"acme": "Acme remux (2)"})
    store.save_preset("template", "Acme remux", {"qpf": "theirs"})
    assert [c["action"] for c in store.use_packs([pack(doc(2))], {}) if c["kind"] == "template"] == ["took over"]
    assert templates(store) == {"Acme remux": shipped_template(2)}
    assert store.get_setting("template_defaults") == {"acme": "Acme remux"}


def test_a_deleted_numbered_copy_beside_the_users_preset_takes_the_users_over(store):
    # the trap the plugin pack fell into: "(2)" deleted as a duplicate, the user's older copy left in use
    store.use_packs([pack()], {"template": ("Acme remux",)})
    store.delete_preset("template", "Acme remux (2)")
    store.save_preset("template", "Acme remux", {"qpf": "theirs"})
    r = template_row(store)
    assert (r["state"], r["replaced_by"], r["stale"]) == ("replaced", "Acme remux", True)
    store.use_packs([pack(doc(2))], {})
    assert templates(store) == {"Acme remux": shipped_template(2)}
    assert (template_row(store)["name"], template_row(store)["state"]) == ("Acme remux", "current")


def test_a_numbered_copy_goes_back_under_its_name_once_free(store):
    store.use_packs([pack()], {"template": ("Acme remux",)})
    store.use_packs([pack()], {})
    assert list(templates(store)) == ["Acme remux"]
    assert template_row(store)["name"] == "Acme remux"


def test_the_users_encoder_preset_in_its_folder_and_label_is_taken_over(store):
    d = doc()
    mine = {**d["presets"]["encoder"][0]["data"], "bitrate_kbps": 1}
    store.import_encoder_presets([{"label": "UHD", "group": ["Acme"], "data": mine}], max_name=80)
    (before,) = store.presets("encoder")
    store.use_packs([pack(d)], {})
    assert list(store.presets("encoder")) == [before]
    assert store.presets("encoder")[before]["settings"] == d["presets"]["encoder"][0]["data"]
    managed = next(m for m in store.managed_presets() if m["kind"] == "encoder")
    store.delete_presets("encoder", [managed["name"]])
    store.import_encoder_presets([{"label": "UHD", "group": ["Acme"], "data": mine}], max_name=80)
    managed = next(m for m in store.managed_presets() if m["kind"] == "encoder")
    assert (managed["state"], managed["replaced_by"], managed["group"]) == ("replaced", "UHD", ["Acme"])
    store.use_packs([pack(d)], {})
    assert len(store.presets("encoder")) == 1


def test_a_settings_only_reset_puts_a_deleted_preset_back(store):
    store.use_packs([pack()], {})
    store.delete_preset("template", "Acme remux")
    store.reset_configuration(("rule_set",), ())
    assert "Acme remux" in templates(store)


def test_a_retired_preset_is_no_longer_kept_in_line(store):
    store.use_packs([pack(doc(templates=("remux", "extra")))], {})
    store.use_packs([pack(doc(templates=("remux",)))], {})
    store.save_preset("template", "Acme extra", {"qpf": "mine"})
    assert store.use_packs([pack(doc(templates=("remux",)))], {}) == []
    assert templates(store)["Acme extra"] == {"qpf": "mine"}
    assert not next(m for m in store.managed_presets() if m["key"] == "extra")["stale"]
