"""Pinned downloads and selective extraction shared by tool and plugin provisioning.

Installers are read as archives, never run. The content-addressed cache is rechecked on every read.
"""

from __future__ import annotations

import fnmatch
import hashlib
import io
from pathlib import Path, PureWindowsPath
import subprocess
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "build" / "plugin-cache"
SEVENZIP = (
    "https://github.com/ip7z/7zip/releases/download/26.03/7zr.exe",
    "ad4c82fadcbdf93c03b4fc440f300509c7d60c5c2f4d183e35d9d70d6957037d",
)
# The full reader handles GPAC's NSIS installer. 7zr reads this 7z SFX to bootstrap it.
FULL_SEVENZIP = (
    "https://github.com/ip7z/7zip/releases/download/26.05/7z2605-x64.exe",
    "fd99e86f57d8f429ef5ed045bf98315af962e2309b0f1ba87a147a44c71647d0",
)


def relative_path(name: str) -> str:
    """Validate a manifest/archive path, including when running on Linux."""
    path = PureWindowsPath(name)
    if not name or not path.parts or path.root or path.drive or ".." in path.parts or ":" in name:
        raise ValueError(f"unsafe artifact path: {name!r}")
    return path.as_posix()


def download(url: str, sha256: str) -> bytes:
    cached = CACHE / sha256
    if cached.is_file():
        data = cached.read_bytes()
    else:
        print(f"  {url}", flush=True)
        with urllib.request.urlopen(url, timeout=120) as response:  # noqa: S310 - pinned https manifests
            data = response.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != sha256:
        raise ValueError(f"{url}: sha256 {digest}, expected {sha256}; remove corrupt cache file {cached}")
    CACHE.mkdir(parents=True, exist_ok=True)
    if not cached.exists():
        with tempfile.NamedTemporaryFile(dir=CACHE, delete=False) as stream:
            pending = Path(stream.name)
            stream.write(data)
        try:
            pending.replace(cached)
        finally:
            pending.unlink(missing_ok=True)
    return data


def _run(argv: list) -> str:
    result = subprocess.run(
        argv,
        capture_output=True,
        stdin=subprocess.DEVNULL,
        timeout=240,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode:
        raise ValueError(
            f"archive extraction failed: {result.stdout.decode('utf-8', 'replace')}"
            f"{result.stderr.decode('utf-8', 'replace')}"
        )
    return result.stdout.decode("utf-8", "replace")


def _reader(folder: Path, *, full: bool = False) -> Path:
    exe = folder / "7zr.exe"
    exe.write_bytes(download(*SEVENZIP))
    if not full:
        return exe
    installer = folder / "7zip.exe"
    installer.write_bytes(download(*FULL_SEVENZIP))
    _run([exe, "x", "-y", f"-o{folder / 'reader'}", installer, "7z.exe", "7z.dll"])
    return folder / "reader" / "7z.exe"


def unpack(url: str, data: bytes, files: dict[str, str]) -> dict[str, bytes]:
    """Exact destination -> archive member mappings (also used by the plugin manifest)."""
    for dest, member in files.items():
        relative_path(dest)
        relative_path(member)
    name = url.rsplit("/", 1)[-1]
    if not name.endswith((".zip", ".whl", ".7z", ".exe", ".cab")) or not files:
        return {relative_path(next(iter(files), name)): data}
    if name.endswith((".zip", ".whl")):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return {dest: archive.read(member) for dest, member in files.items()}
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        exe = _reader(folder, full=name.endswith((".exe", ".cab")))
        archive = folder / name
        archive.write_bytes(data)
        out = folder / "out"
        _run([exe, "x", "-y", f"-o{out}", archive, "--", *files.values()])
        missing = [m for m in files.values() if not (out / m).is_file()]
        if missing:
            raise ValueError(f"{url}: not in the archive: {', '.join(missing)}")
        return {dest: (out / member).read_bytes() for dest, member in files.items()}


def extract(url: str, data: bytes, prefix: str, include: list[str]) -> dict[str, bytes]:
    """Strip an archive prefix and select globs, retaining directories and notices."""
    if prefix:
        prefix = relative_path(prefix).rstrip("/") + "/"
    for pattern in include:
        relative_path(pattern)
    if url.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = [n for n in archive.namelist() if not n.endswith("/")]
    else:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            exe = _reader(folder, full=url.endswith(".exe"))
            archive = folder / url.rsplit("/", 1)[-1]
            archive.write_bytes(data)
            listing = _run([exe, "l", "-slt", "-ba", archive])
            members = [line.removeprefix("Path = ") for line in listing.splitlines() if line.startswith("Path = ")]
    files = {}
    matched = set()
    for member in members:
        normalized = relative_path(member)
        if not normalized.startswith(prefix):
            continue
        dest = normalized.removeprefix(prefix)
        for pattern in include:
            # Root-level *.dll excludes an installer's $PLUGINSDIR/*.dll.
            if "/" not in pattern and "/" in dest:
                continue
            if fnmatch.fnmatchcase(dest, pattern):
                if dest in files and files[dest] != member:
                    raise ValueError(f"duplicate archive destination: {dest}")
                files[dest] = member
                matched.add(pattern)
    if missing := set(include) - matched:
        raise ValueError(f"{url}: no files match {sorted(missing)}")
    return unpack(url, data, files)
