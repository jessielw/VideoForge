"""vsplugins/manifest.toml: the shape scripts/fetch_plugins.py and vsplugins/build.py read."""

from __future__ import annotations

from pathlib import Path
import re
import tomllib

MANIFEST = tomllib.loads((Path(__file__).parents[1] / "vsplugins" / "manifest.toml").read_text(encoding="utf-8"))
BUILDS = {"meson", "cmake", "autotools", "make", "zig", "cc", "download"}
SHA256 = re.compile(r"[0-9a-f]{64}")


def downloads(plugin: dict) -> list[dict]:
    win = plugin["win64"]
    return [win] if isinstance(win, dict) else win


def test_every_plugin_has_a_source_a_build_and_a_windows_download():
    for p in MANIFEST["plugin"]:
        assert {"name", "namespace", "repo", "ref", "license", "build", "win64"} <= p.keys(), p["name"]
        assert p["build"] in BUILDS, p["name"]
        assert p["repo"].startswith("https://"), p["name"]
        if p["build"] == "zig":
            assert re.fullmatch(r"\d+\.\d+\.\d+", p["zig"]), p["name"]
        if p["build"] == "cc":
            assert p["sources"] and p["library"], p["name"]
        linux = [p["linux64"]] if p["build"] == "download" else []
        for d in downloads(p) + linux:
            assert d["url"].startswith("https://") and SHA256.fullmatch(d["sha256"]), p["name"]
            if d["url"].endswith((".zip", ".whl", ".7z")):
                assert d["files"], f"{p['name']}: an archive needs `files`"


def test_names_and_namespaces_are_unique():
    names = [p["name"] for p in MANIFEST["plugin"]]
    namespaces = [p["namespace"] for p in MANIFEST["plugin"]]
    assert len(set(names)) == len(names) and len(set(namespaces)) == len(namespaces)


def test_scripts_are_pinned():
    for s in MANIFEST["script"]:
        assert s["url"].startswith("https://") and SHA256.fullmatch(s["sha256"]), s["name"]
        assert all(isinstance(old, str) and isinstance(new, str) for old, new in s.get("replace", {}).items())
