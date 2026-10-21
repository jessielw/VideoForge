"""Provisioning must cover runtime tools, reject unsafe files and repair damaged installations."""

import hashlib
import importlib
import io
import json
from pathlib import Path
import tomllib
import zipfile

import pytest

from videoforge.core.config import Tools, load_app_config

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def provisioner(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    return importlib.import_module("fetch_tools")


def archive(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as z:
        for name, content in files.items():
            z.writestr(name, content)
    return stream.getvalue()


def test_inventory_covers_all_runtime_paths_and_matches_shipped_config(provisioner):
    manifest = provisioner.load_manifest()
    defaults = tomllib.loads((ROOT / "videoforge.toml").read_text(encoding="utf-8"))["tools"]
    covered = [name for entry in manifest["external"] for name in entry["provides"]]
    for tool in manifest["tool"]:
        win = tool["windows"]
        for name, path in win["executables"].items():
            covered.append(name)
            expected = f"tools/{win['directory']}/{path}"
            if name in {"ffprobe", "mkvextract", "mkvpropedit"}:
                parent = "ffmpeg" if name == "ffprobe" else "mkvmerge"
                assert Path(defaults[parent]).with_name(name + ".exe").as_posix() == expected
            else:
                assert defaults[name] == expected
    assert set(covered) == set(Tools.__dataclass_fields__)
    assert len(covered) == len(set(covered)), "a runtime tool must have exactly one provider"


def test_bundled_defaults_prefer_local_files_and_keep_existing_path_setups(monkeypatch, tmp_path):
    config = tmp_path / "videoforge.toml"
    config.write_bytes((ROOT / "videoforge.toml").read_bytes())
    monkeypatch.setattr("videoforge.core.config.shutil.which", lambda name: f"PATH/{name}")
    app = load_app_config(config)
    assert app.tools.ffmpeg == "PATH/ffmpeg"
    assert app.tools.mp4box == "PATH/MP4Box"
    bundled = tmp_path / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe"
    bundled.parent.mkdir(parents=True)
    bundled.write_bytes(b"exe")
    assert load_app_config(config).tools.ffmpeg == str(bundled)


def test_extract_preserves_selected_dlls_and_notices_without_installer_files(provisioner):
    artifacts = importlib.import_module("artifacts")
    data = archive(
        {
            "pkg/tool.exe": b"exe",
            "pkg/runtime.dll": b"dll",
            "pkg/doc/LICENSE": b"notice",
            "pkg/$PLUGINSDIR/installer.dll": b"installer",
            "pkg/unused.exe": b"unused",
        }
    )
    result = artifacts.extract("https://example.test/tools.zip", data, "pkg", ["tool.exe", "*.dll", "doc/*"])
    assert result == {"tool.exe": b"exe", "runtime.dll": b"dll", "doc/LICENSE": b"notice"}
    with pytest.raises(ValueError, match="no files match"):
        artifacts.extract("https://example.test/tools.zip", data, "pkg", ["missing.dll"])


@pytest.mark.parametrize(
    "name",
    ["../escape.exe", "C:/escape.exe", "/escape.exe", "\\escape.exe", "safe/../../escape.exe", "safe.exe:stream"],
)
def test_unsafe_archive_and_destination_paths_are_rejected(provisioner, name):
    artifacts = importlib.import_module("artifacts")
    with pytest.raises(ValueError, match="unsafe artifact path"):
        artifacts.extract("https://example.test/tools.zip", archive({name: b"bad"}), "", ["*.exe"])
    with pytest.raises(ValueError, match="unsafe artifact path"):
        artifacts.unpack("https://example.test/tool.bin", b"data", {name: "tool.bin"})


def test_cached_downloads_are_rehashed_and_corruption_fails_closed(provisioner, monkeypatch, tmp_path):
    artifacts = importlib.import_module("artifacts")
    monkeypatch.setattr(artifacts, "CACHE", tmp_path)
    digest = hashlib.sha256(b"correct").hexdigest()
    (tmp_path / digest).write_bytes(b"correct")
    assert artifacts.download("https://example.test/tool.zip", digest) == b"correct"
    (tmp_path / digest).write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="sha256"):
        artifacts.download("https://example.test/tool.zip", digest)


def test_repeat_install_is_offline_and_missing_companion_is_repaired(provisioner, monkeypatch, tmp_path):
    tool = {
        "name": "test",
        "version": "1",
        "windows": {
            "url": "https://example.test/tool.zip",
            "sha256": "a" * 64,
            "directory": "test",
            "prefix": "",
            "include": ["tool.exe", "runtime.dll"],
            "executables": {"test": "tool.exe"},
        },
        "notice": [{"file": "LICENSE", "url": "https://example.test/LICENSE", "sha256": "b" * 64}],
    }
    payload = archive({"tool.exe": b"exe", "runtime.dll": b"dll"})
    calls = []

    def download(url, _sha):
        calls.append(url)
        return b"license" if url.endswith("LICENSE") else payload

    monkeypatch.setattr(provisioner, "download", download)
    user_file = tmp_path / "test" / "QTfiles64" / "user.dll"
    user_file.parent.mkdir(parents=True)
    user_file.write_bytes(b"user supplied")
    provisioner.provision(tool, tmp_path)
    assert provisioner.installed(tool, tmp_path)
    provisioner.provision(tool, tmp_path)
    assert len(calls) == 2
    (tmp_path / "test" / "runtime.dll").unlink()
    assert not provisioner.installed(tool, tmp_path)
    provisioner.provision(tool, tmp_path)
    assert len(calls) == 4
    assert user_file.read_bytes() == b"user supplied"
    assert (tmp_path / "test" / "runtime.dll").read_bytes() == b"dll"
    receipt = json.loads((tmp_path / ".videoforge" / "test.json").read_text())
    assert "test/LICENSE" in receipt["files"]


def test_unavailable_archive_member_leaves_existing_files_untouched(provisioner, monkeypatch, tmp_path):
    tool = {
        "name": "test",
        "version": "1",
        "windows": {
            "url": "https://example.test/tool.zip",
            "sha256": "a" * 64,
            "directory": "test",
            "prefix": "",
            "include": ["tool.exe", "runtime.dll"],
            "executables": {"test": "tool.exe"},
        },
    }
    monkeypatch.setattr(provisioner, "download", lambda *_: archive({"tool.exe": b"new"}))
    existing = tmp_path / "test" / "tool.exe"
    existing.parent.mkdir()
    existing.write_bytes(b"old")
    with pytest.raises(ValueError, match="runtime.dll"):
        provisioner.provision(tool, tmp_path)
    assert existing.read_bytes() == b"old"
    assert not (tmp_path / ".videoforge" / "test.json").exists()
