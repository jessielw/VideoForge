"""The external tools: what each one is for, whether it's there, and its version.

detect() runs every tool's version command in parallel (with a timeout) and keeps
the first output line that looks like a version, so the Settings page can show
"mkvmerge v100.0 ('...') 64-bit" next to the path it found.

DeeZy 2 runs only DEE 6.7 (a folder of tools) and, when it is given one, dee_shim 0.3.0 or newer: a version it
would refuse is UNSUPPORTED here and blocks the encodes that need it (dee_issues).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
import dataclasses
from dataclasses import asdict, dataclass
from enum import StrEnum
import errno
import functools
import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess

from videoforge.core import dee
from videoforge.core.config import Tools, wine_target
from videoforge.core.execute.audio import ENCODES, SHIM_ATMOS_MODES, AudioSettings, dee_shim, track_option
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
    pattern: re.Pattern[str] | None = None  # the version is this match in the output, not the first version line


TOOLS: tuple[ToolInfo, ...] = (
    ToolInfo("vspipe", "vspipe", "Feeds the VapourSynth script's frames to the video encoder"),
    ToolInfo(
        "vs_plugins",
        "VapourSynth plugins",
        "Source filters (BestSource, L-SMASH, FFMS2) and the other filters scripts use",
        folder=True,
    ),
    ToolInfo("x264", "x264", "H.264 video encoder"),
    ToolInfo("x265", "x265", "HEVC video encoder"),
    ToolInfo("svtav1", "SvtAv1EncApp", "AV1 video encoder (SVT-AV1)"),
    ToolInfo("svtav1hdr", "SvtAv1EncApp (HDR)", "AV1 video encoder with HDR10+ and Dolby Vision (SVT-AV1-HDR)"),
    ToolInfo("mkvmerge", "mkvmerge", "Reads sources' tracks and builds MKV files (MKVToolNix)"),
    ToolInfo("mp4box", "MP4Box", "Builds MP4 files (GPAC)", (("-version",),)),
    ToolInfo(
        "ffmpeg",
        "ffmpeg",
        "Encodes VP8 and VP9 video, and FLAC, Opus, AAC, AC-3, E-AC-3, MP3 and Vorbis audio. Decodes audio for the "
        "other encoders",
        (("-version",),),
    ),
    ToolInfo(
        "ffprobe",
        "ffprobe",
        "Reads each track's start and the frame rate in MP4 and TS sources. Without it, VideoForge uses MediaInfo's, "
        "which misses some MP4 edit lists",
        (("-version",),),
    ),
    ToolInfo("qaac", "qaac", "AAC encoder (needs Apple's CoreAudioToolbox)", (("--check",),)),
    ToolInfo("opusenc", "opusenc", "Opus encoder (opus-tools)"),
    ToolInfo("deezy", "DeeZy", "Runs DEE for DDP and DDP Atmos encodes (DeeZy 2)"),
    ToolInfo(
        "dee",
        "Dolby Encoding Engine",
        "The DEE 6.7 tools folder DeeZy encodes DDP / Atmos with (not redistributable)",
        (("--help",),),
        pattern=dee.VERSION,
    ),
    ToolInfo("truehdd", "truehdd", "Decodes TrueHD Atmos for DDP Atmos encodes"),
    ToolInfo(
        "dee_shim",
        "dee_shim",
        "Optional, for DeeZy: DDP 7.1 and the 7.1 Atmos modes need it, and Atmos encodes run through it (faster)",
    ),
    ToolInfo("dovi_tool", "dovi_tool", "Carries a source's Dolby Vision metadata (RPU) into the encode"),
    ToolInfo("hdr10plus_tool", "hdr10plus_tool", "Carries a source's HDR10+ metadata into the encode"),
)
TOOL_NAMES = tuple(t.name for t in TOOLS)


class ToolStatus(StrEnum):
    OK = "ok"  # found, and it printed a version
    UNKNOWN = "unknown"  # found and it ran, but no version line
    UNSUPPORTED = "unsupported"  # found, but a version DeeZy 2 won't run (detail says which it needs)
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
    gone = {name: not find(name, paths[name]) for name in {n for e in ENCODES.values() for n in e.tools}}
    have = None if gone.get("ffmpeg", True) else ffmpeg_encoders(tools.ffmpeg)
    out: dict[AudioAction, list[str]] = {}
    for action, e in ENCODES.items():
        missing = [_LABEL[n] for n in e.tools if gone[n]]
        if e.ffmpeg_encoder and have is not None and e.ffmpeg_encoder not in have:
            missing.append(f"an ffmpeg build with {e.ffmpeg_encoder}")
        out[action] = missing
    return out


def tool_issues(plan: Plan, tools: Tools, container: str = "mkv", settings: AudioSettings | None = None) -> list[Issue]:
    """A BLOCK for each kind of audio encode the plan needs whose tools are missing, and for
    the container's muxer and subtitle extraction. settings: the rule set's (its Atmos mode)."""
    missing = missing_for_encodes(tools)
    issues = []
    muxer = MUXERS[container]
    if not locate(getattr(tools, muxer.tool)):
        issues.append(
            Issue(
                Severity.BLOCK, "tools.missing", f"{muxer.label} needs {_LABEL[muxer.tool]}. Set it in Settings › Tools"
            )
        )
    if container == "mp4" and any(s.source.format is SubFormat.SRT and not s.source.is_external for s in plan.subs):
        for tool in ("mkvmerge", "mkvextract"):
            if not locate(getattr(tools, tool)):
                issues.append(
                    Issue(
                        Severity.BLOCK,
                        "tools.missing",
                        f"SRT subtitles from the source need {tool} for MP4. Set the MKVToolNix path in Settings › Tools",
                    )
                )
    for action in dict.fromkeys(a.action for a in plan.audio):
        if missing.get(action):
            issues.append(
                Issue(
                    Severity.BLOCK,
                    "tools.missing",
                    f"{ENCODES[action].label} needs {', '.join(missing[action])}. Set it in Settings › Tools",
                )
            )
    issues += _dee_issues(plan, tools, settings)
    return issues


def _dee_issues(plan: Plan, tools: Tools, settings: AudioSettings | None = None) -> list[Issue]:
    """DeeZy's encodes: a DeeZy, DEE or dee_shim version DeeZy 2 won't run blocks them (dee_shim too, since VideoForge
    hands DeeZy any dee_shim it finds), and so does a missing dee_shim for DDP 7.1 and the 7.1 Atmos modes; a
    loudness target can't be combined with a dialnorm or Blu-ray DDP."""
    deezy = [a for a in plan.audio if a.action is not AudioAction.COPY and "deezy" in ENCODES[a.action].tools]
    if not deezy:
        return []
    issues = []
    label = ", ".join(dict.fromkeys(ENCODES[a.action].label for a in deezy))
    for c in checks(tools, ("deezy", "dee", "dee_shim")).values():
        if c is not None and c.status is ToolStatus.UNSUPPORTED:
            issues.append(
                Issue(
                    Severity.BLOCK,
                    "tools.version",
                    f"{label}: {c.detail}, not {c.version}. Set {c.label} in Settings › Tools",
                )
            )
    shim = bool(dee_shim(tools))
    for a in deezy:
        bluray = track_option(a, "ddp_mode", settings) == "bluray"
        if not shim and a.action is AudioAction.DDP and not bluray and a.out_layout.channels > 6:
            issues.append(
                Issue(
                    Severity.BLOCK,
                    "tools.dee_shim",
                    f"{ENCODES[a.action].label} 7.1 needs dee_shim, or the Blu-ray DDP mode. Set dee_shim in "
                    "Settings › Tools",
                )
            )
        if (
            not shim
            and a.action is AudioAction.ATMOS
            and (mode := track_option(a, "atmos_mode", settings)) in (SHIM_ATMOS_MODES)
        ):
            issues.append(
                Issue(
                    Severity.BLOCK,
                    "tools.dee_shim",
                    f"{ENCODES[a.action].label} {mode} mode (7.1) needs dee_shim, or the streaming mode. Set dee_shim "
                    "in Settings › Tools",
                )
            )
        if a.action is not AudioAction.DDP or not a.options.get("loudness_target"):
            continue
        if a.options.get("dialnorm", "0") not in ("", "0"):
            issues.append(
                Issue(Severity.BLOCK, "tools.dee_loudness", "A loudness target can't be combined with a dialnorm")
            )
        if bluray:
            issues.append(
                Issue(Severity.BLOCK, "tools.dee_loudness", "A loudness target isn't available for Blu-ray DDP")
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


def find(name: str, path: str) -> str:
    """Where a tool's configured path leads ("" when nowhere): the DEE tools folder for dee, else the program."""
    return dee.folder(path) if name == "dee" else locate(path)


# The oldest of each that works with VideoForge's DeeZy arguments: (major, minor, patch), and why.
_MINIMUM = {
    "deezy": ((2, 0, 0), "VideoForge needs DeeZy 2.0 or newer"),
    "dee_shim": ((0, 3, 0), "DeeZy needs dee_shim 0.3.0 or newer"),
}


def _numbers(version: str) -> tuple[int, ...] | None:
    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", version)
    return tuple(int(g or 0) for g in match.groups()) if match else None


def unsupported(name: str, version: str) -> str:
    """Why DeeZy 2 won't run this version of a tool ("" when it will, or for a version it can't read)."""
    if name == "dee":
        found = dee.version(version)
        return f"DeeZy 2 needs DEE {dee.SUPPORTED}" if found and not dee.supported(found) else ""
    if name in _MINIMUM:
        least, why = _MINIMUM[name]
        numbers = _numbers(version)
        return why if numbers is not None and numbers < least else ""
    return ""


def x265_avx512(path: str) -> bool | None:
    """Ask the configured x265 which instructions it would use with AVX-512 enabled."""
    found = locate(path)
    if not found:
        return None
    try:
        return _x265_avx512(found, Path(found).stat().st_mtime_ns)
    except (OSError, subprocess.SubprocessError):
        return None


@functools.lru_cache(maxsize=8)
def _x265_avx512(exe: str, _stamp: int) -> bool | None:
    output = _run([exe, "--asm", "avx512", "--version"], 3.0)
    flags = re.search(r"using cpu capabilities:[ \t]*([^\r\n]+)", output, re.IGNORECASE)
    if flags is None:
        return None
    return bool(re.search(r"\bAVX-?512\b", flags[1], re.IGNORECASE))


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


def _friendly_error(e: BaseException, found: str) -> str:
    """Plain words for the OS errors a tool that can't start gives on Linux; "" for anything else."""
    if os.name == "nt" or not isinstance(e, OSError):
        return ""
    if e.errno == errno.ENOEXEC:
        if found.lower().endswith(".exe"):
            return "This is a Windows program, so it needs Wine to run here. The Docker image has Wine"
        return "Not a program this system can run (wrong build for this CPU or system?)"
    if e.errno == errno.EACCES:
        return (
            "This file or the programs next to it can't be read or run. Make them readable and executable "
            "(chmod -R a+rX), or in Docker set PUID and PGID so VideoForge fixes this when it starts"
        )
    return ""


def check(info: ToolInfo, path: str, *, runner: Runner = _run, timeout: float = 8.0) -> ToolCheck:
    """One tool's check, showing the Windows .exe it was given rather than the Wine launcher standing in for it."""
    result = _check(info, path, runner=runner, timeout=timeout)
    return dataclasses.replace(
        result, path=wine_target(result.path) or result.path, found=wine_target(result.found) or result.found
    )


def _check(info: ToolInfo, path: str, *, runner: Runner, timeout: float) -> ToolCheck:
    if info.folder:
        return _plugins(path)
    found = find(info.name, path)
    base = (info.name, info.label, info.purpose, path)
    if not found:
        return ToolCheck(*base, "", ToolStatus.MISSING, detail=_missing(info.name, path))
    output, error = "", ""
    for args in info.args:
        try:
            output = runner([dee.program(found), *args], timeout)
        except (OSError, subprocess.SubprocessError) as e:
            error = f"{type(e).__name__}: {e}"
            error = _friendly_error(e, found) or error
            continue
        if line := _version(info, output):
            if why := unsupported(info.name, line):
                return ToolCheck(*base, found, ToolStatus.UNSUPPORTED, version=line, detail=why)
            return ToolCheck(*base, found, ToolStatus.OK, version=line)
    if error and not output:
        return ToolCheck(*base, found, ToolStatus.BROKEN, detail=error)
    first = next((ln.strip() for ln in output.splitlines() if ln.strip()), "")
    return ToolCheck(*base, found, ToolStatus.UNKNOWN, detail=first[:160])


def _missing(name: str, path: str) -> str:
    p = Path(path)
    if name == "dee" and p.is_dir():
        return f"No DEE {dee.SUPPORTED} tools ({dee.MARKER}) in this folder"
    if name == "dee" and p.is_file():
        return f"Choose the DEE {dee.SUPPORTED} tools folder (the one with {dee.MARKER})"
    return "This is a folder. Choose the program in it" if p.is_dir() else "Not found at this path or on PATH"


def _version(info: ToolInfo, output: str) -> str:
    if info.pattern is None:
        return version_line(output)
    match = info.pattern.search(output)
    return match.group(0) if match else ""


def detect(tools: Tools, *, runner: Runner = _run, timeout: float = 8.0) -> list[ToolCheck]:
    """Every tool in TOOLS order, checked in parallel."""
    paths = asdict(tools)
    with ThreadPoolExecutor(max_workers=min(len(TOOLS), (os.cpu_count() or 4) + 2)) as pool:
        return list(pool.map(lambda info: check(info, paths[info.name], runner=runner, timeout=timeout), TOOLS))


_CHECKS: dict[tuple[str, str, int], ToolCheck] = {}  # (tool, file, mtime ns) -> its check


def checks(
    tools: Tools, names: Sequence[str], *, runner: Runner | None = None, timeout: float = 8.0
) -> dict[str, ToolCheck | None]:
    """Each named tool's check (None when it is missing), cached per file and mtime so a queue of jobs asks each
    tool once. DEE's file is its folder's dee_ddp_encoder."""
    paths = asdict(tools)
    infos = {t.name: t for t in TOOLS if not t.folder}
    out: dict[str, ToolCheck | None] = {}
    for name in names:
        info = infos.get(name)
        found = find(name, paths.get(name, "")) if info else ""
        out[name] = None
        if info is None or not found:
            continue
        try:
            key = (name, os.path.normcase(os.path.abspath(found)), Path(dee.program(found)).stat().st_mtime_ns)
        except OSError:
            continue
        if key not in _CHECKS:
            _CHECKS[key] = check(info, found, runner=runner or _run, timeout=timeout)
        out[name] = _CHECKS[key]
    return out


def versions(
    tools: Tools, names: Sequence[str], *, runner: Runner | None = None, timeout: float = 8.0
) -> dict[str, str]:
    """The version line of each named tool ("" when it printed none or is missing), cached as checks() is."""
    found = checks(tools, names, runner=runner, timeout=timeout)
    return {name: c.version if c is not None else "" for name, c in found.items()}
