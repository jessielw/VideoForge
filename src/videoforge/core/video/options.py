"""The option names each video encoder takes, read from its own help, so a mistyped option warns before the run
(StaxRip has an option editor per encoder; a typo in VideoForge's options failed only when the encoder ran).

x264 and x265 list theirs with --fullhelp, SvtAv1EncApp with --help; ffmpeg (VP8 / VP9) with `-h encoder=libvpx*`
(the encoder's own options) and `-h full` (ffmpeg's main options and the codec options every encoder takes, -g,
-qmin ...). Each list is read once per executable, its size and mtime. A name the help doesn't list warns only:
builds can take options their help leaves out (Patman's x265 takes --dhdr10-info).
"""

from __future__ import annotations

import difflib
import functools
import logging
import os
import re
import subprocess

from videoforge.core.arguments import split_args
from videoforge.core.config import Tools
from videoforge.core.models import Issue, Severity
from videoforge.core.tools import locate
from videoforge.core.video.settings import Encoder, EncoderSettings

logger = logging.getLogger(__name__)

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_TIMEOUT = 15.0
# x264 "  -b, --bframes <integer>  Number of ...", x265 "-D/--output-depth 8|10|12  ..." and "   --[no-]ssim  ...",
# SvtAv1EncApp "      --preset   Encoder preset ...". Deeper lines continue a description (x264's preset list).
_DASHDASH = re.compile(r"^ {0,8}(?:-[A-Za-z0-9](?:, ?|/))?--(\[no-\])?([A-Za-z0-9][\w-]*)(.*)$")
# ffmpeg "  -lag-in-frames     <int>        E..V....... Number of frames ..." and "-pix_fmt format  set pixel format"
_FFMPEG = re.compile(r"^ {0,2}-([A-Za-z0-9][\w-]*)(?:\[:<stream_spec>\])?\s+(.*)$")
_AVOPTION_FLAGS = re.compile(r"^(?:<\w+>\s+)?([E.][D.][F.][V.][A.][S.]\S*)\s*(.*)$")
# Taken though the help leaves them out (checked on the builds VideoForge ships with).
_UNLISTED: dict[Encoder, dict[str, str]] = {
    Encoder.X265: {"dhdr10-info": "HDR10+ dynamic metadata JSON (Patman's build takes it; its help leaves it out)"},
}


def dashes(encoder: Encoder) -> str:
    """What the encoder's options start with (ffmpeg's take one dash)."""
    return "-" if encoder.libvpx else "--"


def _help(description: str) -> str:
    return " ".join(description.split())[:300]


def parse_dashdash(text: str) -> dict[str, str]:
    """x264 / x265 / SvtAv1EncApp help: {name: its help line}; "--[no-]name" gives name and no-name."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        m = _DASHDASH.match(line)
        if m is None:
            continue
        neg, name, rest = m.groups()
        out.setdefault(name, _help(rest))
        if neg:
            out.setdefault("no-" + name, _help(rest))
    return out


def parse_ffmpeg(text: str, encoder_options: bool) -> dict[str, str]:
    """ffmpeg's help. encoder_options: an `-h encoder=` text (every option is the encoder's); else `-h full`,
    where only the options before the per-format sections count, and of the codec options only the video
    encoding ones (E..V)."""
    out: dict[str, str] = {}
    section = ""
    for line in text.splitlines():
        if line.endswith("AVOptions:"):
            section = line
            continue
        m = _FFMPEG.match(line)
        if m is None:
            continue
        name, rest = m.groups()
        flags = _AVOPTION_FLAGS.match(rest)
        if not encoder_options:
            if section and section != "AVCodecContext AVOptions:":
                continue
            if section and (flags is None or flags.group(1)[0] != "E" or flags.group(1)[3] != "V"):
                continue
        out.setdefault(name, _help(flags.group(2) if flags else rest))
    return out


def _run(argv: list[str]) -> str:
    out = subprocess.run(
        argv, capture_output=True, timeout=_TIMEOUT, creationflags=_NO_WINDOW, check=False,
        stdin=subprocess.DEVNULL,
    )  # fmt: skip
    return (out.stdout + out.stderr).decode("utf-8", "replace")


@functools.lru_cache(maxsize=16)
def _read(encoder: Encoder, exe: str, _size: int, _mtime: int) -> dict[str, str]:
    if encoder is Encoder.X264 or encoder is Encoder.X265:
        return parse_dashdash(_run([exe, "--fullhelp"]))
    if encoder is Encoder.SVTAV1:
        return parse_dashdash(_run([exe, "--help"]))
    lib = "libvpx-vp9" if encoder is Encoder.VP9 else "libvpx"
    own = parse_ffmpeg(_run([exe, "-hide_banner", "-h", f"encoder={lib}"]), encoder_options=True)
    if not own:  # this ffmpeg has no libvpx: nothing to check against
        return {}
    return own | {
        k: v for k, v in parse_ffmpeg(_run([exe, "-hide_banner", "-h", "full"]), False).items() if k not in own
    }


def _exe(encoder: Encoder, tools: Tools) -> str:
    if encoder.libvpx:
        return tools.ffmpeg
    return tools.x264 if encoder is Encoder.X264 else tools.x265 if encoder is Encoder.X265 else tools.svtav1


def known_options(encoder: Encoder, tools: Tools) -> dict[str, str]:
    """{option name: help} from the encoder's help; {} when the encoder isn't there or lists nothing."""
    exe = locate(_exe(encoder, tools))
    if not exe:
        return {}
    try:
        st = os.stat(exe)
        known = _read(encoder, exe, st.st_size, st.st_mtime_ns)
    except (OSError, subprocess.SubprocessError) as ex:
        logger.info("No option list from %s: %s", exe, ex)
        return {}
    return known | _UNLISTED.get(encoder, {}) if known else {}


def used_options(settings: EncoderSettings) -> list[str]:
    """The option names the job sets: the options' and the flags in the extra arguments, in order, once each."""
    names = [k.lstrip("-") for k in settings.options]
    one = dashes(settings.encoder) == "-"
    for arg in split_args(settings.extra):
        flag = arg.partition("=")[0]
        if one and re.match(r"^-[A-Za-z]", flag):
            names.append(flag[1:].partition(":")[0])  # -b:v -> b
        elif not one and flag.startswith("--") and len(flag) > 2:
            names.append(flag[2:])
    return list(dict.fromkeys(n for n in names if n))


def option_issues(settings: EncoderSettings, tools: Tools | None) -> list[Issue]:
    """A WARN for each option the encoder's help doesn't list, with the nearest listed name."""
    known = known_options(settings.encoder, tools) if tools is not None else {}
    if not known:
        return []
    out, d = [], dashes(settings.encoder)
    for name in used_options(settings):
        if name in known:
            continue
        near = difflib.get_close_matches(name, list(known), n=1, cutoff=0.75)
        hint = f": did you mean {d}{near[0]}?" if near else ": check its spelling."
        out.append(
            Issue(
                Severity.WARN,
                "video.option_unknown",
                f"{settings.encoder.label}'s help doesn't list {d}{name}{hint} An option it doesn't take fails the "
                "encode when it runs",
            )
        )
    return out
