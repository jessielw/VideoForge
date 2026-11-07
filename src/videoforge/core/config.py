"""Load videoforge.toml (and videoforge.local.toml over it): tool paths, matching rules, the default rule set."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import hashlib
import importlib.util
import os
from pathlib import Path
import re
import shutil
import sys
import sysconfig
import tempfile
import tomllib

from videoforge.core.execute.control import Priority
from videoforge.core.pairing import MatchRules

# The app's folder: videoforge.toml, tools/ and the built frontend. The checkout by default; a portable
# build's launcher sets VIDEOFORGE_ROOT to its own folder (the package is installed in its Python).
PROJECT_ROOT = Path(os.environ.get("VIDEOFORGE_ROOT") or Path(__file__).resolve().parents[3])


def app_data_dir() -> Path:
    """The default data folder (`serve --data-dir` moves it): %APPDATA%\\VideoForge, else the XDG data home's."""
    base = os.environ.get("APPDATA") or os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "VideoForge"


@dataclass(frozen=True)
class Tools:
    mkvmerge: str
    deezy: str
    dee: str
    truehdd: str
    qaac: str
    ffmpeg: str
    ffprobe: str = "ffprobe"  # default: next to ffmpeg
    mkvpropedit: str = "mkvpropedit"  # default: next to mkvmerge
    mkvextract: str = "mkvextract"  # default: next to mkvmerge
    x264: str = "x264"
    x265: str = "x265"
    svtav1: str = "SvtAv1EncApp"
    opusenc: str = "opusenc"
    mp4box: str = "MP4Box"
    dovi_tool: str = "dovi_tool"  # Dolby Vision RPU extract / edit
    hdr10plus_tool: str = "hdr10plus_tool"  # HDR10+ metadata extract
    vspipe: str = ""  # default: the one pip's vapoursynth installs next to this Python
    vs_plugins: str = ""  # extra VapourSynth plugin folder (VAPOURSYNTH_EXTRA_PLUGIN_PATH)


@dataclass(frozen=True)
class AppConfig:
    tools: Tools
    matching: MatchRules = field(default_factory=MatchRules)
    rule_set: str | None = None  # default rule set id for new jobs; None = the built-in one
    allow_commands: bool = False  # [actions] commands: the Settings page's command actions may run
    plugins: dict[str, dict] = field(default_factory=dict)  # [plugins.<id>]: each plugin's own settings
    parallel_audio: int = 2  # audio encodes run alongside a job's video, this many at once; 0 = one by one
    delete_work_dir: bool = False  # delete a job's <source>_tmp/ once it's done (its records are kept elsewhere)
    min_free_gb: float = 20  # a run doesn't start with less free on its work or output folder's disk; 0 = off
    # StaxRip's defaults: the video encode (the encoder and the vspipe feeding it) below normal, other tools normal
    encoder_priority: Priority = Priority.BELOW_NORMAL
    tool_priority: Priority = Priority.NORMAL

    @staticmethod
    def upgrade_json(data: dict) -> dict:
        """Settings saved before rule sets had their name: `profile` held the default rule set's id."""
        return {"rule_set": data["profile"], **data} if "profile" in data else data


# Tools found next to another unless set: MKVToolNix's next to mkvmerge, ffprobe next to ffmpeg.
_SIBLINGS = {"mkvpropedit": "mkvmerge", "mkvextract": "mkvmerge", "ffprobe": "ffmpeg"}
# Existing source checkouts may use PATH before running the new provisioner. Only
# these bundled defaults fall back; an explicitly configured custom path must stay explicit.
_BUNDLED_FALLBACKS = {"tools/ffmpeg/bin/ffmpeg.exe": "ffmpeg", "tools/GPAC/mp4box.exe": "MP4Box"}


WINE_RUN = "/opt/wine/bin/wine-run"  # the Docker image's Wine launcher


def _wine_launcher(exe: Path) -> str:
    """A Windows .exe can't be executed on Linux: a small script that runs it through Wine stands in for it, so
    a path to the .exe just works (the Docker image has wine-run; elsewhere the .exe is left as it is)."""
    if sys.platform == "win32" or exe.suffix.lower() != ".exe" or not Path(WINE_RUN).is_file():
        return str(exe)
    folder = Path(tempfile.gettempdir()) / f"videoforge-wine-{os.getuid()}"
    folder.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(str(exe).encode(), usedforsecurity=False).hexdigest()[:8]
    launcher = folder / f"{exe.stem}-{digest}"
    script = f'#!/bin/sh\nexec {WINE_RUN} "{exe}" "$@"\n'
    if not launcher.is_file() or launcher.read_text() != script:
        launcher.write_text(script)
        launcher.chmod(0o755)
    return str(launcher)


def wine_target(path: str) -> str:
    """The .exe a launcher made by _wine_launcher runs, so Settings can show the path that was typed; "" for
    any other file."""
    p = Path(path)
    if not p.parent.name.startswith("videoforge-wine-"):
        return ""
    try:
        match = re.search(r'^exec \S+ "(.+)" "\$@"$', p.read_text(), re.MULTILINE)
    except OSError:
        return ""
    return match.group(1) if match else ""


# Where the Docker image's /tools folder keeps a tool, for one that isn't on PATH (added after the container
# started, so it has no launcher yet).
_TOOLS_FOLDER = {
    "dee": ("/tools/dee/dee", "/tools/wine/dee/dee.exe"),
    "qaac": ("/tools/wine/qaac/qaac64.exe",),
}


def _resolve_tool(value: str, base: Path) -> str:
    candidate = base / value
    if candidate.exists():
        return _wine_launcher(candidate) if candidate.is_file() else str(candidate)
    found = shutil.which(_BUNDLED_FALLBACKS.get(value.replace("\\", "/"), value))
    if not found and sys.platform != "win32":
        found = next((_wine_launcher(Path(p)) for p in _TOOLS_FOLDER.get(value, ()) if Path(p).is_file()), None)
    return found or value


def default_vspipe() -> str:
    """The vspipe pip's vapoursynth installed: the binary in its package, else next to this Python (a venv's) or
    in its scripts folder. The package's first: the scripts folder's is an installer launcher holding this
    Python's absolute path, which a moved portable folder no longer has."""
    name = "vspipe.exe" if sys.platform == "win32" else "vspipe"
    spec = importlib.util.find_spec("vapoursynth")
    package = [Path(p) for p in (spec.submodule_search_locations or [])] if spec else []
    for folder in (*package, Path(sys.executable).parent, Path(sysconfig.get_path("scripts"))):
        if (folder / name).is_file():
            return str(folder / name)
    return shutil.which("vspipe") or "vspipe"


def _merged(base: dict, over: dict) -> dict:
    out = dict(base)
    for key, value in over.items():
        out[key] = _merged(out[key], value) if isinstance(value, dict) and isinstance(out.get(key), dict) else value
    return out


def with_tools(cfg: AppConfig, paths: dict[str, str], base: Path = PROJECT_ROOT) -> AppConfig:
    """cfg with some tool paths replaced (the Settings page's; relative ones resolve against base).
    A new mkvmerge brings the mkvpropedit and mkvextract next to it (a new ffmpeg its ffprobe), unless those
    are set too."""
    names = asdict(cfg.tools)
    for name, value in paths.items():
        if name in names and value:
            names[name] = _resolve_tool(value, base)
    for tool, beside in _SIBLINGS.items():
        if paths.get(beside) and not paths.get(tool):
            main = Path(names[beside])
            sibling = main.with_name(tool + main.suffix)
            if sibling.is_file():
                names[tool] = str(sibling)
    return replace(cfg, tools=Tools(**names))


def load_app_config(path: Path | None = None) -> AppConfig:
    path = path or PROJECT_ROOT / "videoforge.toml"
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    local = path.with_name(path.stem + ".local.toml")
    if local.is_file():
        data = _merged(data, tomllib.loads(local.read_text(encoding="utf-8")))
    base = path.parent
    names = {name: _resolve_tool(v, base) for name, v in data["tools"].items()}
    for tool, beside in _SIBLINGS.items():
        if tool not in names and beside in names:
            sibling = Path(names[beside]).with_name(tool + Path(names[beside]).suffix)
            names[tool] = str(sibling) if sibling.is_file() else _resolve_tool(tool, base)
    if "vspipe" not in names:
        names["vspipe"] = default_vspipe()
    tools = Tools(**names)
    pairing = data.get("pairing", {})
    d = MatchRules()
    matching = MatchRules(
        encode_suffixes=tuple(pairing.get("encode_suffixes", d.encode_suffixes)),
        encode_extensions=tuple(e.lower() for e in pairing.get("encode_extensions", d.encode_extensions)),
        scan_source_folder=pairing.get("scan_source_folder", d.scan_source_folder),
        staxrip_temp=pairing.get("staxrip_temp", d.staxrip_temp),
    )
    allow_commands = bool(data.get("actions", {}).get("commands", False))
    plugins = {k: v for k, v in data.get("plugins", {}).items() if isinstance(v, dict)}
    pipeline = data.get("pipeline", {})
    parallel_audio = max(0, int(pipeline.get("parallel_audio", AppConfig.parallel_audio)))
    delete_work_dir = bool(pipeline.get("delete_work_dir", AppConfig.delete_work_dir))
    min_free_gb = max(0.0, float(pipeline.get("min_free_gb", AppConfig.min_free_gb)))
    encoder_priority = Priority(pipeline.get("encoder_priority", AppConfig.encoder_priority))
    tool_priority = Priority(pipeline.get("tool_priority", AppConfig.tool_priority))
    return AppConfig(
        tools=tools,
        matching=matching,
        rule_set=data.get("rule_set", data.get("profile")),  # `profile`: its name before 0.1.0-beta.11
        allow_commands=allow_commands,
        plugins=plugins,
        parallel_audio=parallel_audio,
        delete_work_dir=delete_work_dir,
        min_free_gb=min_free_gb,
        encoder_priority=encoder_priority,
        tool_priority=tool_priority,
    )
