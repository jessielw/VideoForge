"""A rule set that arrives as a plugins-folder package (an installed ZIP), not an entry point."""

import io
from pathlib import Path
import sys
import zipfile

import pytest

from videoforge import rule_sets
from videoforge.plugins.manager import read_package
from videoforge.plugins.manifest import PluginError, parse_manifest

MODULE = "vf_test_folder_rules"
RULES = """
from videoforge.rule_sets.manual import ManualRuleSet


class FolderRules(ManualRuleSet):
    id = "folderrules"
    name = "Folder rules"
"""


def manifest(pid: str = "folderrules", extra: str = "") -> str:
    return f'id = "{pid}"\nmodule = "{MODULE}"\nrule_set = "FolderRules"\nname = "F"\nversion = "1"\napi_version = 1\n{extra}'


@pytest.fixture
def plugins(tmp_path: Path):
    folder = tmp_path / "plugins"
    yield folder
    rule_sets.use_folder(None)
    sys.modules.pop(MODULE, None)
    for p in [p for p in sys.path if str(tmp_path) in p]:
        sys.path.remove(p)


def install(folder: Path, text: str | None = None, module_text: str = RULES, name: str = "folderrules") -> None:
    root = folder / name
    root.mkdir(parents=True)
    (root / "videoforge-plugin.toml").write_text(text or manifest(), encoding="utf-8")
    (root / f"{MODULE}.py").write_text(module_text, encoding="utf-8")


def test_manifest_names_the_class() -> None:
    assert parse_manifest(manifest()).rule_set == "FolderRules"
    assert parse_manifest('id = "a"\nmodule = "a"\n').rule_set == ""
    with pytest.raises(PluginError):
        parse_manifest('id = "a"\nmodule = "a"\nrule_set = "not a name"\n')


def test_folder_rule_set_is_registered_and_loads(plugins: Path) -> None:
    install(plugins)
    rule_sets.use_folder(plugins)
    assert rule_sets.rule_set_ids() == ["manual", "folderrules"]
    assert rule_sets.get_rule_set("folderrules").name == "Folder rules"
    assert rule_sets.folder_failures() == {}


def test_disabled_folder_rule_set_is_left_out(plugins: Path) -> None:
    install(plugins)
    rule_sets.use_folder(plugins, ["folderrules"])
    assert rule_sets.rule_set_ids() == ["manual"]


def test_the_builtin_keeps_its_id(plugins: Path) -> None:
    install(plugins, manifest("manual"), name="manual")
    rule_sets.use_folder(plugins)
    assert rule_sets.registry()["manual"] == "videoforge.rule_sets.manual:ManualRuleSet"


def test_vendor_folder_is_importable(plugins: Path) -> None:
    install(plugins, module_text=RULES + "\nimport vf_vendored_dep\n")
    vendor = plugins / "folderrules" / "vendor"
    vendor.mkdir()
    (vendor / "vf_vendored_dep.py").write_text("VALUE = 1\n", encoding="utf-8")
    rule_sets.use_folder(plugins)
    try:
        assert rule_sets.get_rule_set("folderrules").name == "Folder rules"
    finally:
        sys.modules.pop("vf_vendored_dep", None)


def test_module_already_loaded_elsewhere_fails_that_rule_set(plugins: Path) -> None:
    install(plugins)
    sys.modules[MODULE] = sys  # stands in for a module loaded from another place
    rule_sets.use_folder(plugins)
    assert rule_sets.rule_set_ids() == ["manual"]
    assert "already loaded" in rule_sets.folder_failures()["folderrules"]


def test_zip_with_a_rule_set_installs(plugins: Path) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("videoforge-plugin.toml", manifest())
        z.writestr(f"{MODULE}.py", RULES)
    package = read_package(buffer.getvalue())
    assert package.manifest.rule_set == "FolderRules"
