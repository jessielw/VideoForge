"""Provision pinned Windows x64 tools for a checkout or portable release.

    uv run python scripts/fetch_tools.py [--tools DIR] [--only NAME ...]

scripts/tools.toml owns the inventory. Unrelated files (DEE licenses, QTfiles64,
custom tools) are preserved. Receipts detect changes and repair incomplete installs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import string
import sys
import tempfile
import tomllib

from artifacts import ROOT, download, extract, relative_path, unpack

MANIFEST = Path(__file__).with_name("tools.toml")


def load_manifest() -> dict:
    manifest = tomllib.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest["schema"] != 1:
        raise ValueError("unsupported tool manifest schema")
    names = [t["name"] for t in manifest["tool"]]
    if len(names) != len(set(names)):
        raise ValueError("duplicate tool name in manifest")
    for tool in manifest["tool"]:
        win = tool["windows"]
        relative_path(win["directory"])
        for path in win["executables"].values():
            relative_path(path)
        for artifact in [win, *tool.get("notice", [])]:
            if (
                not artifact["url"].startswith("https://")
                or len(artifact["sha256"]) != 64
                or any(c not in string.hexdigits for c in artifact["sha256"])
            ):
                raise ValueError(f"{tool['name']}: downloads need HTTPS and a pinned SHA-256")
    return manifest


def require_windows() -> None:
    if sys.platform != "win32" or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise ValueError("tool provisioning supports Windows x64; use Docker on Linux/macOS")


def fingerprint(tool: dict) -> str:
    return hashlib.sha256(json.dumps(tool, sort_keys=True).encode()).hexdigest()


def installed(tool: dict, dest: Path) -> bool:
    receipt = dest / ".videoforge" / f"{tool['name']}.json"
    try:
        record = json.loads(receipt.read_text(encoding="utf-8"))
        if record["manifest"] != fingerprint(tool) or not record["files"]:
            return False
        return all(
            hashlib.sha256((dest / relative_path(name)).read_bytes()).hexdigest() == digest
            for name, digest in record["files"].items()
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False


def write_file(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        pending = Path(stream.name)
        stream.write(data)
    try:
        pending.replace(path)
    finally:
        pending.unlink(missing_ok=True)


def provision(tool: dict, dest: Path) -> None:
    if installed(tool, dest):
        print(f"{tool['name']}: verified installed files", flush=True)
        return
    print(f"{tool['name']}: {tool['version']}", flush=True)
    win = tool["windows"]
    data = download(win["url"], win["sha256"])
    original = data
    if container := win.get("container"):
        start, size = container["offset"], container["size"]
        cabinet = data[start : start + size]
        if len(cabinet) != size or cabinet[:4] != b"MSCF":
            raise ValueError(f"{tool['name']}: pinned runtime cabinet is missing")
        data = unpack("payload.cab", cabinet, {"runtime.cab": container["member"]})["runtime.cab"]
    files = (
        unpack("runtime.cab" if win.get("container") else win["url"], data, win["files"])
        if "files" in win
        else extract(win["url"], data, win["prefix"], win["include"])
    )
    if mapping := win.get("installer_files"):
        files.update(unpack(win["url"], original, mapping))
    for notice in tool.get("notice", []):
        files[relative_path(notice["file"])] = download(notice["url"], notice["sha256"])
    for path in win["executables"].values():
        if path not in files:
            raise ValueError(f"{tool['name']}: executable {path} missing from archive selection")
    record = {
        "manifest": fingerprint(tool),
        "version": tool["version"],
        "url": win["url"],
        "sha256": win["sha256"],
        "files": {},
    }
    for directory in [win["directory"], *win.get("deploy", [])]:
        for path, content in files.items():
            name = f"{relative_path(directory)}/{relative_path(path)}"
            write_file(dest / name, content)
            record["files"][name] = hashlib.sha256(content).hexdigest()
    write_file(dest / ".videoforge" / f"{tool['name']}.json", json.dumps(record, indent=2).encode())


def write_inventory(manifest: dict, dest: Path) -> None:
    lines = [
        "# VideoForge Windows tools",
        "",
        "Pinned inventory; .videoforge/*.json records installed files.",
        "",
        "Keep upstream notices with the binaries. Source/build information is linked per tool.",
        "",
    ]
    for tool in manifest["tool"]:
        lines += [
            f"## {tool['name']} — {tool['version']}",
            "",
            tool["purpose"],
            "",
            f"License: {tool['license']}",
            f"Source/build: {tool['source']}",
            f"Binary: {tool['windows']['url']}",
            f"SHA-256: {tool['windows']['sha256']}",
            "",
        ]
    lines += ["## Other runtime dependencies", ""]
    lines += [f"- {item['name']}: {item['provider']}" for item in manifest["external"]]
    write_file(dest / "THIRD_PARTY.md", "\n".join(lines).encode("utf-8"))


def sync_runtime(manifest: dict, tools: Path, runtime: Path) -> None:
    """Copy the pinned runtime beside Python/VS hosts as well as external tools."""
    tool = next(t for t in manifest["tool"] if t["name"] == "vcruntime")
    if not installed(tool, tools):
        raise ValueError("provision vcruntime before copying it into the Python runtime")
    if not runtime.is_dir() or not (runtime / "python.exe").is_file():
        raise ValueError(f"not a Python runtime folder: {runtime}")
    source = tools / tool["windows"]["directory"]
    for folder in (runtime, runtime / "Scripts", runtime / "Lib" / "site-packages" / "vapoursynth"):
        if folder.is_dir():
            for name in [
                *tool["windows"]["files"],
                *tool["windows"].get("installer_files", {}),
                *(n["file"] for n in tool.get("notice", [])),
            ]:
                write_file(folder / name, (source / name).read_bytes())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tools", type=Path, default=ROOT / "tools", help="the tools folder")
    ap.add_argument("--only", nargs="+", default=[], metavar="NAME", help="just these tools")
    ap.add_argument("--list", action="store_true", help="show the inventory without downloading")
    ap.add_argument("--runtime-dir", type=Path, help="also copy Microsoft runtime DLLs beside this Python runtime")
    args = ap.parse_args()
    try:
        manifest = load_manifest()
        known = {t["name"] for t in manifest["tool"]}
        if unknown := set(args.only) - known:
            ap.error(f"unknown tools: {', '.join(sorted(unknown))}")
        if args.list:
            for tool in manifest["tool"]:
                print(f"{tool['name']}: {tool['version']} - {tool['purpose']}")
            for item in manifest["external"]:
                print(f"{item['name']}: {item['provider']}")
            return 0
        require_windows()
        dest = args.tools.resolve()
        for tool in manifest["tool"]:
            if not args.only or tool["name"] in args.only:
                provision(tool, dest)
        write_inventory(manifest, dest)
        if args.runtime_dir:
            sync_runtime(manifest, dest, args.runtime_dir.resolve())
    except (OSError, ValueError) as error:
        ap.exit(1, f"{error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
