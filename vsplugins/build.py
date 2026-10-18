"""Build the VapourSynth plugins in manifest.toml (Linux; run by vsplugins/Dockerfile).

    python3 build.py [NAME ...]     build the plugins (all, or the ones named)
    python3 build.py --check        load every built plugin together and list the runtime packages they need

Plugins land in PREFIX/vs-plugins (with any `files` next to them; a plugin with CPU variants in its own folder
with a manifest.vs). FFmpeg is already in PREFIX (the Dockerfile builds it first), so they link against it.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import io
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tomllib
import urllib.request
import zipfile

HERE = Path(__file__).resolve().parent
PREFIX = Path(os.environ.get("VF_PREFIX", "/opt/vf"))
PLUGINS = PREFIX / "vs-plugins"
WORK = Path(os.environ.get("VF_WORK", "/build"))
JOBS = str(os.cpu_count() or 2)


def run(*cmd: str | Path, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], cwd=cwd, env=env, check=True)


def output(*cmd: str) -> str:
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout.strip()


def manifest() -> dict:
    return tomllib.loads((HERE / "manifest.toml").read_text(encoding="utf-8"))


def fetch(entry: dict) -> Path:
    """The repo at entry's ref (a tag, branch or commit), in WORK/<name>, with the submodules asked for."""
    dest = WORK / entry["name"]
    if dest.exists():
        shutil.rmtree(dest)
    run("git", "init", "-q", dest)
    run("git", "-C", dest, "fetch", "-q", "--depth", "1", entry["repo"], entry["ref"])
    run("git", "-C", dest, "checkout", "-q", "FETCH_HEAD")
    submodules = entry.get("submodules", False)
    if submodules:
        paths = [] if submodules is True else list(submodules)
        run("git", "-C", dest, "submodule", "update", "-q", "--init", "--recursive", "--depth", "1", "--", *paths)
    return dest


def build(entry: dict, src: Path, extra: tuple[str, ...] = ()) -> Path:
    """Build entry from src; returns the folder the build left its files in."""
    top = src / entry.get("subdir", "")
    include = output("pkg-config", "--variable=includedir", "vapoursynth")
    opts = [o.replace("{vs_include}", include) for o in entry.get("options", [])] + list(extra)
    env = {**os.environ, **entry.get("env", {})}
    kind = entry["build"]
    if kind == "meson":
        out = top / "_build"
        run("meson", "setup", out, top, "--buildtype=release", "-Db_ndebug=true", *opts, env=env)
        run("ninja", "-C", out, env=env)
        return out
    if kind == "cmake":
        out = top / "_build"
        run("cmake", "-S", top, "-B", out, "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release", *opts, env=env)
        run("cmake", "--build", out, env=env)
        return out
    if kind == "autotools":
        if (top / "autogen.sh").exists():
            run("sh", "autogen.sh", cwd=top, env=env)
        else:
            run("autoreconf", "-fi", cwd=top, env=env)
        run("./configure", *opts, cwd=top, env=env)
        run("make", f"-j{JOBS}", *entry.get("targets", []), cwd=top, env=env)
        return top
    if kind == "make":
        run("make", f"-j{JOBS}", *opts, cwd=top, env=env)
        return top
    if kind == "zig":
        zig = f"/opt/zig-x86_64-linux-{entry['zig']}/zig"
        out = top / "zig-out"
        shutil.rmtree(out, ignore_errors=True)
        run(zig, "build", "-Doptimize=ReleaseFast", "-Dtarget=x86_64-linux-gnu", *opts, cwd=top, env=env)
        return out
    if kind == "cc":
        sources = sorted(f for pattern in entry["sources"] for f in glob.glob(str(top / pattern)))
        if not sources:
            sys.exit(f"{entry['name']}: no sources match {entry['sources']}")
        cxx = any(s.endswith((".cpp", ".cc")) for s in sources)
        compiler = "g++" if cxx else "gcc"
        std = "-std=c++17" if cxx else "-std=c11"
        out = top / "_build"
        out.mkdir(exist_ok=True)
        run(compiler, std, "-O2", "-fPIC", "-shared", f"-I{include}", *opts, *sources, "-o", out / entry["library"])
        return out
    sys.exit(f"{entry['name']}: unknown build {kind!r}")


def find_library(entry: dict, out: Path) -> Path:
    """The plugin library the build made: the one file matching `library` (default *.so*) outside subprojects."""
    found = [
        p for p in out.rglob(entry.get("library", "*.so*"))
        if p.is_file() and not p.is_symlink() and "subprojects" not in p.parts and p.suffix not in (".a", ".la")
    ]  # fmt: skip
    if len(found) != 1:
        sys.exit(f"{entry['name']}: expected one plugin library in {out}, found {[str(p) for p in found]}")
    return found[0]


def install_download(entry: dict) -> None:
    """A release build (`linux64`: url, sha256, files = {name in the plugin folder = path in the zip})."""
    d = entry["linux64"]
    print("+ download", d["url"], flush=True)
    with urllib.request.urlopen(d["url"], timeout=120) as r:  # noqa: S310 - the manifest's https URL
        data = r.read()
    if (digest := hashlib.sha256(data).hexdigest()) != d["sha256"]:
        sys.exit(f"{entry['name']}: sha256 {digest}, expected {d['sha256']}")
    PLUGINS.mkdir(parents=True, exist_ok=True)
    libs = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name, member in d["files"].items():
            dest = PLUGINS / name
            dest.write_bytes(z.read(member))
            libs += [dest] if dest.suffix == ".so" else []
    smoke(entry["namespace"], libs)
    print(f"== {entry['name']}: {', '.join(d['files'])}", flush=True)


def install_plugin(entry: dict) -> None:
    if entry["build"] == "download":
        install_download(entry)
        return
    src = fetch(entry)
    env = {**os.environ, **entry.get("env", {})}
    for command in entry.get("before", []):
        run("sh", "-ec", command, cwd=src, env=env)
    PLUGINS.mkdir(parents=True, exist_ok=True)
    variants: dict[str, str] = entry.get("variants", {})
    if variants:  # one build per CPU level, in their own folder: VapourSynth loads the best the CPU runs
        folder = PLUGINS / entry["name"]
        folder.mkdir(exist_ok=True)
        base = ""
        for suffix, cpu in variants.items():
            lib = find_library(entry, build(entry, src, (f"-Dcpu={cpu}",)))
            base = re.sub(r"\.so(\.\d+)*$", "", lib.name)
            dest = folder / (f"{base}.{suffix}.so" if suffix else f"{base}.so")
            install_file(lib, dest)
        (folder / "manifest.vs").write_text(f"[VapourSynth Manifest V1]\n{base}\n", encoding="utf-8")
        loaded = folder / f"{base}.so"
    else:
        lib = find_library(entry, build(entry, src))
        loaded = PLUGINS / re.sub(r"\.so(\.\d+)*$", ".so", lib.name)
        install_file(lib, loaded)
        folder = PLUGINS
    for f in entry.get("files", []):
        shutil.copy2(src / f, folder / Path(f).name)
    smoke(entry["namespace"], [loaded])
    shutil.rmtree(src)
    print(f"== {entry['name']}: {loaded.relative_to(PLUGINS)}", flush=True)


def install_file(lib: Path, dest: Path) -> None:
    shutil.copy2(lib, dest)
    run("strip", "--strip-unneeded", dest)


def smoke(namespace: str, libs: list[Path]) -> None:
    """Load libs into a fresh core and check the namespace is there."""
    code = (
        "import sys, vapoursynth as vs\n"
        "core = vs.core\n"
        "for lib in sys.argv[2:]: core.std.LoadPlugin(lib)\n"
        "ns = sys.argv[1]\n"
        "assert hasattr(core, ns), f'no vs.core.{ns}'\n"
        "print(ns, 'ok:', ', '.join(sorted(f.name for f in getattr(core, ns).functions()))[:200])\n"
    )
    run(sys.executable, "-c", code, namespace, *libs)


def check() -> None:
    """Every plugin loaded together (one namespace each), and the Debian packages the binaries need."""
    m = manifest()
    namespaces = [p["namespace"] for p in m["plugin"]]
    code = (
        "import sys, vapoursynth as vs\n"
        "core = vs.core\n"
        "core.std.LoadAllPlugins(sys.argv[2])\n"
        "missing = [ns for ns in sys.argv[1].split(',') if not hasattr(core, ns)]\n"
        "assert not missing, f'missing namespaces: {missing}'\n"
        "print(len(sys.argv[1].split(',')), 'plugins loaded')\n"
    )
    run(sys.executable, "-c", code, ",".join(namespaces), PLUGINS)
    libs = sorted(PLUGINS.rglob("*.so"))
    packages = runtime_packages([*libs, *PREFIX.glob("bin/*"), *PREFIX.glob("lib/*.so*")])
    (PREFIX / "runtime-packages.txt").write_text("\n".join(packages) + "\n", encoding="utf-8")
    print("runtime packages:", " ".join(packages))


def runtime_packages(files: list[Path]) -> list[str]:
    """The Debian packages owning the shared libraries files link to outside PREFIX."""
    needed: set[str] = set()
    for f in files:
        if not f.is_file() or f.is_symlink():
            continue
        result = subprocess.run(["ldd", str(f)], capture_output=True, text=True)
        if result.returncode != 0:
            continue
        for line in result.stdout.splitlines():
            if "not found" in line:
                sys.exit(f"{f}: {line.strip()}")
            m = re.search(r"=> (/\S+)", line)
            if m and not os.path.realpath(m.group(1)).startswith(str(PREFIX)):
                needed.add(m.group(1))
    packages: set[str] = set()
    for path in sorted(needed):
        real = os.path.realpath(path)
        for candidate in dict.fromkeys(
            (path, real, *(p.removeprefix("/usr") for p in (path, real) if p.startswith("/usr/")))
        ):
            owner = subprocess.run(["dpkg", "-S", candidate], capture_output=True, text=True)
            if owner.returncode == 0:
                packages.add(owner.stdout.split(":")[0])
                break
        else:
            sys.exit(f"no package owns {path}")
    # The C runtime is in every Debian image.
    return sorted(packages - {"libc6", "libgcc-s1", "libstdc++6"})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("names", nargs="*", help="libraries/plugins to build (default: all)")
    parser.add_argument("--check", action="store_true", help="load all built plugins; write runtime-packages.txt")
    args = parser.parse_args()
    if args.check:
        check()
        return
    m = manifest()
    wanted = set(args.names)
    if unknown := wanted - {e["name"] for e in m["plugin"]}:
        sys.exit(f"not in the manifest: {', '.join(sorted(unknown))}")
    WORK.mkdir(parents=True, exist_ok=True)
    for entry in m["plugin"]:
        if not wanted or entry["name"] in wanted:
            install_plugin(entry)


if __name__ == "__main__":
    main()
