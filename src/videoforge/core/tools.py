"""The external tools: what each one is for, whether it's there, and its version.

detect() runs every tool's version command in parallel (with a timeout) and keeps
the first output line that looks like a version, so the Settings page can show
"mkvmerge v100.0 ('...') 64-bit" next to the path it found.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from enum import StrEnum
import functools
import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess

from videoforge.core.config import Tools
from videoforge.core.execute.audio import ENCODES
from videoforge.core.execute.mux import MUXERS
from videoforge.core.models import AudioAction, Issue, Plan, Severity, SubFormat

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_VERSION = re.compile(r"\d+\.\d+|\br\d{2,}\b|\bv\d+\b", re.IGNORECASE)
_NOT_A_VERSION = re.compile(r"\berror\b|unknown option|unrecognized|invalid option", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ToolInfo:
    name: str  # the Tools field
    label: str
    purpose: str
    args: tuple[tuple[str, ...], ...] = (("--version",),)  # tried in order until one prints a version
    folder: bool = False  # a folder (the VapourSynth plugins), not a program


TOOLS: tuple[ToolInfo, ...] = (
    ToolInfo("vspipe", "vspipe", "Runs the VapourSynth script into the video encoder"),
    ToolInfo(
        "vs_plugins", "VapourSynth plugins", "Source filters (BestSource, L-SMASH, FFMS2) and filters", folder=True
    ),
    ToolInfo("x264", "x264", "H.264 video encoder"),
    ToolInfo("x265", "x265", "HEVC video encoder"),
    ToolInfo("svtav1", "SvtAv1EncApp", "AV1 video encoder (SVT-AV1)"),
    ToolInfo("mkvmerge", "mkvmerge", "Reads sources and muxes the output (MKVToolNix)"),
    ToolInfo("mp4box", "MP4Box", "Muxes MP4 output (GPAC)", (("-version",),)),
    ToolInfo(
        "ffmpeg",
        "ffmpeg",
        "Decodes audio for the other encoders; its own FLAC, Opus, AAC, AC-3, E-AC-3",
        (("-version",),),
    ),
    ToolInfo(
        "ffprobe",
        "ffprobe",
        "Times an MP4 or TS source's tracks (their start, the frame rate); without it, MediaInfo's",
        (("-version",),),
    ),
    ToolInfo("qaac", "qaac", "AAC encoder (needs Apple's CoreAudioToolbox)", (("--check",),)),
    ToolInfo("opusenc", "opusenc", "Opus encoder (opus-tools)"),
    ToolInfo("deezy", "DeeZy", "Drives DEE for DDP and DDP Atmos encodes"),
    ToolInfo(
        "dee", "Dolby Encoding Engine", "DDP / Atmos encoder used by DeeZy (not redistributable)", (("--help",), ())
    ),
    ToolInfo("truehdd", "truehdd", "Decodes TrueHD Atmos for DDP Atmos encodes"),
    ToolInfo("dovi_tool", "dovi_tool", "Carries a source's Dolby Vision metadata (RPU) into the encode"),
    ToolInfo("hdr10plus_tool", "hdr10plus_tool", "Carries a source's HDR10+ metadata into the encode"),
)
TOOL_NAMES = tuple(t.name for t in TOOLS)


class ToolStatus(StrEnum):
    OK = "ok"  # found, and it printed a version
    UNKNOWN = "unknown"  # found and it ran, but no version line
    MISSING = "missing"  # not at that path, not on PATH
    BROKEN = "broken"  # found, but it wouldn't start


@dataclass(frozen=True, slots=True)
class ToolCheck:
    name: str
    label: str
    purpose: str
    path: str  # as configured
    found: str  # the file it resolved to ("" when missing)
    status: ToolStatus
    version: str = ""
    detail: str = ""  # why it's missing/broken, or what a folder holds


_LABEL = {t.name: t.label for t in TOOLS}


def ffmpeg_encoders(path: str) -> frozenset[str] | None:
    """The encoders an ffmpeg build has (`ffmpeg -encoders`, cached per file and its mtime),
    or None when it can't be asked (then nothing is assumed missing)."""
    found = locate(path)
    if not found:
        return None
    try:
        stamp = os.stat(found).st_mtime_ns
    except OSError:
        return None
    return _encoders(found, stamp)


@functools.lru_cache(maxsize=8)
def _encoders(found: str, _stamp: int) -> frozenset[str] | None:
    try:
        out = subprocess.run(
            [found, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=15, creationflags=_NO_WINDOW
        ).stdout
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    # " A....D flac   FLAC (Free Lossless Audio Codec)": six flag columns, then the name.
    names = {
        parts[1]
        for parts in (line.split() for line in out.splitlines())
        if len(parts) >= 2 and len(parts[0]) == 6 and parts[0][0] in "VAS"
    }
    return frozenset(names) or None


def missing_for_encodes(tools: Tools) -> dict[AudioAction, list[str]]:
    """Each audio encode's missing tools (by label), from execute.audio.ENCODES; an empty list =
    it can run. Looks for the files, and asks ffmpeg (once per build) which encoders it has."""
    paths = asdict(tools)
    gone = {name: not locate(paths[name]) for name in {n for e in ENCODES.values() for n in e.tools}}
    have = None if gone.get("ffmpeg", True) else ffmpeg_encoders(tools.ffmpeg)
    out: dict[AudioAction, list[str]] = {}
    for action, e in ENCODES.items():
        missing = [_LABEL[n] for n in e.tools if gone[n]]
        if e.ffmpeg_encoder and have is not None and e.ffmpeg_encoder not in have:
            missing.append(f"an ffmpeg build with {e.ffmpeg_encoder}")
        out[action] = missing
    return out


def tool_issues(plan: Plan, tools: Tools, container: str = "mkv") -> list[Issue]:
    """A BLOCK for each kind of audio encode the plan needs whose tools are missing, and for
    the container's muxer and subtitle extraction."""
    missing = missing_for_encodes(tools)
    issues = []
    muxer = MUXERS[container]
    if not locate(getattr(tools, muxer.tool)):
        issues.append(
            Issue(Severity.BLOCK, "tools.missing", f"{muxer.label} needs {_LABEL[muxer.tool]}: set it in Settings")
        )
    if container == "mp4" and any(s.source.format is SubFormat.SRT and not s.source.is_external for s in plan.subs):
        for tool in ("mkvmerge", "mkvextract"):
            if not locate(getattr(tools, tool)):
                issues.append(
                    Issue(
                        Severity.BLOCK,
                        "tools.missing",
                        f"Source SRT subtitles for MP4 need {tool}: set the MKVToolNix path in Settings",
                    )
                )
    for action in dict.fromkeys(a.action for a in plan.audio):
        if missing.get(action):
            issues.append(
                Issue(
                    Severity.BLOCK,
                    "tools.missing",
                    f"{ENCODES[action].label} needs {', '.join(missing[action])}: set it in Settings",
                )
            )
    return issues


Runner = Callable[[Sequence[str], float], str]


def _run(argv: Sequence[str], timeout: float) -> str:
    """stdout + stderr of a version command (exit code ignored: some tools exit 1 on --version)."""
    r = subprocess.run(
        list(argv),
        capture_output=True,
        timeout=timeout,
        creationflags=_NO_WINDOW,
        stdin=subprocess.DEVNULL,
        check=False,
    )
    return (r.stdout + b"\n" + r.stderr).decode("utf-8", "replace")


def version_line(output: str) -> str:
    """The first non-empty line that carries a version number, cleaned of log prefixes."""
    for line in output.splitlines():
        line = re.sub(r"^\S+\s+\[info\]:\s*", "", line.strip())  # x265 prints "x265 [info]: HEVC encoder version ..."
        if _NOT_A_VERSION.search(line):  # e.g. DEE: "[2026-10-13 15:28:38.673] ERROR: Unknown option"
            continue
        if line and _VERSION.search(line):
            return line[:160]
    return ""


def locate(path: str) -> str:
    """The file a configured tool path points at: as given, or found on PATH; "" when neither."""
    if not path:
        return ""
    if Path(path).is_file():
        return path
    return shutil.which(path) or ""


_SOURCE_FILTERS = {"bestsource": "BestSource", "lsmashsource": "L-SMASH", "vslsmashsource": "L-SMASH", "ffms2": "FFMS2"}


def bundled_plugin_folder() -> Path | None:
    """The vapoursynth package's own plugins folder, which VapourSynth always loads (the Docker image's plugins
    are there); None when it has none."""
    spec = importlib.util.find_spec("vapoursynth")
    folder = Path(spec.origin).parent / "plugins" if spec and spec.origin else None
    return folder if folder is not None and folder.is_dir() else None


def _plugin_names(folder: Path) -> list[str]:
    """The plugins in folder: its libraries, and its subfolders with a manifest.vs (one plugin built for several
    CPU levels), named without a "lib" prefix."""
    names = [
        p.stem if p.is_file() else p.name
        for p in folder.iterdir()
        if (p.is_file() and p.suffix.lower() in (".dll", ".so", ".dylib")) or (p / "manifest.vs").is_file()
    ]
    return sorted(n.lower().removeprefix("lib") for n in names)


def _plugins(path: str) -> ToolCheck:
    info = next(t for t in TOOLS if t.name == "vs_plugins")
    folder = Path(path) if path else None
    bundled_folder = bundled_plugin_folder()
    bundled = _plugin_names(bundled_folder) if bundled_folder else []
    if (folder is None or not folder.is_dir()) and not bundled:
        return ToolCheck(
            info.name,
            info.label,
            info.purpose,
            path,
            "",
            ToolStatus.MISSING,
            detail="Not set" if folder is None else "No such folder",
        )
    names = _plugin_names(folder) if folder is not None and folder.is_dir() else []
    found = set(names) | set(bundled)
    sources = list(dict.fromkeys(label for stem, label in _SOURCE_FILTERS.items() if stem in found))
    status = ToolStatus.OK if sources else ToolStatus.UNKNOWN
    detail = f"{len(names) + len(bundled)} plugins" + (f" ({len(bundled)} bundled)" if bundled else "")
    detail += (
        f"; source filters: {', '.join(sources)}" if sources else "; no source filter (BestSource, L-SMASH or FFMS2)"
    )
    shown = str(folder) if folder is not None and folder.is_dir() else str(bundled_folder)
    return ToolCheck(info.name, info.label, info.purpose, path, shown, status, detail=detail)


def check(info: ToolInfo, path: str, *, runner: Runner = _run, timeout: float = 8.0) -> ToolCheck:
    if info.folder:
        return _plugins(path)
    found = locate(path)
    base = (info.name, info.label, info.purpose, path)
    if not found:
        detail = "A folder: point at the program in it" if Path(path).is_dir() else "Not found at this path or on PATH"
        return ToolCheck(*base, "", ToolStatus.MISSING, detail=detail)
    output, error = "", ""
    for args in info.args:
        try:
            output = runner([found, *args], timeout)
        except (OSError, subprocess.SubprocessError) as e:
            error = f"{type(e).__name__}: {e}"
            if isinstance(e, PermissionError) and os.name != "nt":
                error = f"Not executable (chmod +x it, and the programs next to it): {error}"
            continue
        if line := version_line(output):
            return ToolCheck(*base, found, ToolStatus.OK, version=line)
    if error and not output:
        return ToolCheck(*base, found, ToolStatus.BROKEN, detail=error)
    first = next((ln.strip() for ln in output.splitlines() if ln.strip()), "")
    return ToolCheck(*base, found, ToolStatus.UNKNOWN, detail=first[:160])


def detect(tools: Tools, *, runner: Runner = _run, timeout: float = 8.0) -> list[ToolCheck]:
    """Every tool in TOOLS order, checked in parallel."""
    paths = asdict(tools)
    with ThreadPoolExecutor(max_workers=min(len(TOOLS), (os.cpu_count() or 4) + 2)) as pool:
        return list(pool.map(lambda info: check(info, paths[info.name], runner=runner, timeout=timeout), TOOLS))


_VERSIONS: dict[tuple[str, str, int], str] = {}  # (tool, file, mtime ns) -> version line


def versions(tools: Tools, names: Sequence[str], *, runner: Runner = _run, timeout: float = 8.0) -> dict[str, str]:
    """The version line of each named tool ("" when it printed none or is missing), cached per file
    and mtime so a queue of jobs asks each tool once."""
    paths = asdict(tools)
    infos = {t.name: t for t in TOOLS if not t.folder}
    out: dict[str, str] = {}
    for name in names:
        info = infos.get(name)
        found = locate(paths.get(name, "")) if info else ""
        if info is None or not found:
            out[name] = ""
            continue
        try:
            key = (name, os.path.normcase(os.path.abspath(found)), Path(found).stat().st_mtime_ns)
        except OSError:
            out[name] = ""
            continue
        if key not in _VERSIONS:
            _VERSIONS[key] = check(info, found, runner=runner, timeout=timeout).version
        out[name] = _VERSIONS[key]
    return out
