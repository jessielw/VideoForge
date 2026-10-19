"""Load videoforge.toml (and videoforge.local.toml over it): tool paths, matching rules, the default profile."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import os
from pathlib import Path
import shutil
import sys
import sysconfig
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
    mkvpropedit: str = "mkvpropedit"  # default: next to mkvmerge
    mkvextract: str = "mkvextract"  # default: next to mkvmerge
    x264: str = "x264"
    x265: str = "x265"
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
    profile: str | None = None  # default profile id for new jobs; None = the built-in one
    allow_commands: bool = False  # [actions] commands: the Settings page's command actions may run
    plugins: dict[str, dict] = field(default_factory=dict)  # [plugins.<id>]: each plugin's own settings
    parallel_audio: int = 2  # audio encodes run alongside a job's video, this many at once; 0 = one by one
    delete_work_dir: bool = False  # delete a job's <source>_tmp/ once it's done (its records are kept elsewhere)
    # StaxRip's defaults: the video encode (x264 / x265 and the vspipe feeding it) below normal, other tools normal
    encoder_priority: Priority = Priority.BELOW_NORMAL
    tool_priority: Priority = Priority.NORMAL


_MKVMERGE_SIBLINGS = ("mkvpropedit", "mkvextract")  # MKVToolNix's other tools: found next to mkvmerge


def _resolve_tool(value: str, base: Path) -> str:
    candidate = base / value
    if candidate.exists():
        return str(candidate)
    found = shutil.which(value)
    return found or value


def default_vspipe() -> str:
    """The vspipe pip's vapoursynth installed: next to this Python (a venv's) or in its scripts folder."""
    name = "vspipe.exe" if sys.platform == "win32" else "vspipe"
    for folder in (Path(sys.executable).parent, Path(sysconfig.get_path("scripts"))):
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
    A new mkvmerge brings the mkvpropedit and mkvextract next to it, unless those are set too."""
    names = asdict(cfg.tools)
    for name, value in paths.items():
        if name in names and value:
            names[name] = _resolve_tool(value, base)
    for tool in _MKVMERGE_SIBLINGS:
        if paths.get("mkvmerge") and not paths.get(tool):
            mkvmerge = Path(names["mkvmerge"])
            sibling = mkvmerge.with_name(tool + mkvmerge.suffix)
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
    for tool in _MKVMERGE_SIBLINGS:
        if tool not in names:
            sibling = Path(names["mkvmerge"]).with_name(tool + Path(names["mkvmerge"]).suffix)
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
    encoder_priority = Priority(pipeline.get("encoder_priority", AppConfig.encoder_priority))
    tool_priority = Priority(pipeline.get("tool_priority", AppConfig.tool_priority))
    return AppConfig(
        tools=tools,
        matching=matching,
        profile=data.get("profile"),
        allow_commands=allow_commands,
        plugins=plugins,
        parallel_audio=parallel_audio,
        delete_work_dir=delete_work_dir,
        encoder_priority=encoder_priority,
        tool_priority=tool_priority,
    )
