"""Output names from a template of tokens, in NfoForge's syntax, so its templates read the same here.

A template is text with tokens: `{title} {release_year} {resolution} {source} {video_codec}-GRP`. The values come
from what the job makes, known before it runs: the plan's first audio output (codec, channels, Atmos), the
encode's codec, bit depth and HDR (what the encode carries, hdr.keeps_dv / keeps_hdr10plus), the resolution
class of the cropped and resized picture; and from the source's name, read by guessit (title, year, season and
episode, edition, BluRay / WEB-DL, Hybrid). The source's own codecs and group in its name are never used: they
describe the source, not the output.

    {token}                 the value; an empty one is dropped, and the spaces around it with it
    {:opt=-:token}          "-" before the value, only when there is one (and {token:opt=-:} after it)
    {token|upper}           filters: upper, lower, dots (spaces become dots)

Literal text stays, so a group tag is just typed: `... {video_codec}-GRP`. An unknown token stays as typed and
warns (`name.token`). The result is made a file name (clean_label): characters Windows refuses dropped.

The template names the file when MuxSettings.template_file_name is on (a name typed for the job still wins) and
an MKV's segment title when template_title is; MuxSettings.name_suffix goes before the extension either way.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from functools import lru_cache
import logging
from pathlib import Path
import re
from typing import TYPE_CHECKING, Any
import unicodedata

from videoforge.core.execute.mux import MuxSettings
from videoforge.core.models import AudioCodec, Issue, Plan, Severity
from videoforge.core.video import hdr
from videoforge.core.video.settings import Encoder

if TYPE_CHECKING:
    from videoforge.core.job import JobSpec
    from videoforge.core.rule_set import RuleSet

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE = (
    "{title} {release_year} {season_episode} {edition} {hybrid} {resolution} {source} "
    "{video_dynamic_range_type} {audio_codec} {audio_channel_s} {atmos} {video_codec}"
)


class NameUse(StrEnum):
    """What Settings makes of a template's naming switch, for one rule set's jobs."""

    TEMPLATE = "template"  # as each template (or the rule set's defaults) says
    ON = "on"
    OFF = "off"

    def given(self, templates: bool) -> bool:
        return templates if self is NameUse.TEMPLATE else self is NameUse.ON


@dataclass(slots=True)
class NamePolicy:
    """Settings' word, per rule set, on the name template's two switches (MuxSettings.template_file_name and
    template_title). It applies where a job takes a template's or the rule set's settings (added, a template
    applied), not to a job's own edit: the Output tab still turns either one on or off for that job."""

    file_name: NameUse = NameUse.TEMPLATE
    title: NameUse = NameUse.TEMPLATE

    def apply(self, mux: MuxSettings) -> MuxSettings:
        return replace(
            mux,
            template_file_name=self.file_name.given(mux.template_file_name),
            template_title=self.title.given(mux.template_title),
        )


@dataclass(frozen=True, slots=True)
class Token:
    name: str
    description: str


TOKENS: tuple[Token, ...] = (
    Token("title", "Title from the source's name (MADE IN ABYSS - Journey's Dawn)"),
    Token("title_clean", "Title with only letters, digits and spaces (MADE IN ABYSS Journeys Dawn)"),
    Token("release_year", "Year from the source's name (2019)"),
    Token("season_episode", "Season and episode from the source's name (S01E02); empty for a movie"),
    Token("episode_title", "Episode title from the source's name"),
    Token("edition", "Edition from the source's name (Director's Cut, Extended)"),
    Token("hybrid", "Hybrid, when the source's name says so"),
    Token("source", "Source medium from the source's name (BluRay, UHD BluRay, WEB-DL, WEBRip, DVD)"),
    Token("resolution", "Resolution class of the cropped and resized picture (1080p)"),
    Token("video_codec", "The encode's codec (x264, x265, AV1, VP9)"),
    Token("video_format", "The encode's format (AVC, HEVC, AV1, VP9)"),
    Token("video_bit_depth_dash", "The encode's bit depth (10-Bit)"),
    Token("video_dynamic_range", "HDR or SDR, as the encode carries it"),
    Token("video_dynamic_range_type", "DV, HDR10+, HDR or HLG the encode carries (DV HDR10+); empty for SDR"),
    Token("audio_codec", "The first audio output's codec (DDP, TrueHD, AAC)"),
    Token("audio_channel_s", "The first audio output's channels (5.1)"),
    Token("atmos", "Atmos, when the first audio output carries it"),
    Token("original_filename", "The source's file name without its extension"),
)
_NAMES = frozenset(t.name for t in TOKENS)
FILTERS = {
    "upper": str.upper,
    "lower": str.lower,
    "dots": lambda v: re.sub(r"\s+-\s+|\s+", ".", v),
}

# {:opt=pre:token|filter|filter:opt=post:}
_TOKEN_RE = re.compile(r"\{(?::opt=([^:}]*):)?\s*([A-Za-z0-9_]+)((?:\s*\|\s*[A-Za-z]+)*)\s*(?::opt=([^:}]*):)?\}")

_AUDIO = {
    AudioCodec.AAC: "AAC",
    AudioCodec.AC3: "DD",
    AudioCodec.EAC3: "DDP",
    AudioCodec.TRUEHD: "TrueHD",
    AudioCodec.DTS: "DTS",
    AudioCodec.DTS_HD_MA: "DTS-HD MA",
    AudioCodec.DTS_HD_HRA: "DTS-HD HRA",
    AudioCodec.LPCM: "LPCM",
    AudioCodec.FLAC: "FLAC",
    AudioCodec.OPUS: "Opus",
    AudioCodec.MP3: "MP3",
    AudioCodec.VORBIS: "Vorbis",
}
_CODEC = {Encoder.X264: "x264", Encoder.X265: "x265", Encoder.SVTAV1: "AV1", Encoder.VP9: "VP9", Encoder.VP8: "VP8"}
_FORMAT = {Encoder.X264: "AVC", Encoder.X265: "HEVC", Encoder.SVTAV1: "AV1", Encoder.VP9: "VP9", Encoder.VP8: "VP8"}
# a reused encode's codec, by its extension (StaxRip's raw streams)
_REUSED = {".264": Encoder.X264, ".h264": Encoder.X264, ".avc": Encoder.X264, ".265": Encoder.X265}
_REUSED |= {".h265": Encoder.X265, ".hevc": Encoder.X265}
_SOURCES = {"Ultra HD Blu-ray": "UHD BluRay", "Blu-ray": "BluRay", "HD-DVD": "HD DVD"}


def resolution_class(width: int, height: int) -> str:
    """A release's resolution for a width x height picture: a crop to a wide aspect keeps its class (1920x800 is
    1080p, 3840x1600 is 2160p)."""
    if width >= 3200 or height >= 1800:
        return "2160p"
    if width >= 2200 or height >= 1300:
        return "1440p"
    if width >= 1700 or height >= 900:
        return "1080p"
    if width >= 1100 or height >= 650:
        return "720p"
    return "576p" if height > 480 else "480p"


@lru_cache(maxsize=1024)
def _guess(name: str) -> dict[str, Any]:
    """guessit's reading of a release name (imported on first use: it takes about a second)."""
    try:
        from guessit import guessit

        return dict(guessit(name))
    except Exception:  # a name guessit can't read names nothing; the source's stem still can
        logger.warning("guessit could not read %r", name, exc_info=True)
        return {}


def _text(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(str(v) for v in value)
    return str(value) if value is not None else ""


def _listed(value: Any) -> list[str]:
    return [str(v) for v in value] if isinstance(value, list) else [str(value)] if value is not None else []


def _season_episode(g: dict[str, Any]) -> str:
    season, episode = g.get("season"), g.get("episode")
    seasons = [int(s) for s in (season if isinstance(season, list) else [season]) if s is not None]
    episodes = [int(e) for e in (episode if isinstance(episode, list) else [episode]) if e is not None]
    out = f"S{seasons[0]:02d}" if seasons else ""
    if episodes:
        out += f"E{episodes[0]:02d}" + (f"-E{episodes[-1]:02d}" if len(episodes) > 1 else "")
    return out


def _clean_title(title: str) -> str:
    plain = "".join(c for c in unicodedata.normalize("NFKD", title) if not unicodedata.combining(c))
    plain = re.sub(r"['’]", "", plain.replace("&", " and "))
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9]", " ", plain)).strip()


def source_stem(plan: Plan) -> str:
    return plan.source.path.stem if plan.source.path is not None else Path(plan.source.name).stem


def name_tokens(stem: str) -> dict[str, str]:
    """The tokens read from a source's name."""
    g = _guess(stem)
    title = _text(g.get("title")) or stem
    alternative = _text(g.get("alternative_title"))
    if alternative and g.get("type") != "episode":  # "Patlabor 2 - The Movie" reads as title + alternative
        title = f"{title} - {alternative}"
    other = _listed(g.get("other"))
    found = _text(g.get("source"))
    if found == "Web":
        found = "WEBRip" if "Rip" in other else "WEB-DL"
    return {
        "title": title,
        "title_clean": _clean_title(title),
        "release_year": _text(g.get("year")),
        "season_episode": _season_episode(g),
        "episode_title": _text(g.get("episode_title")),
        "edition": _text(g.get("edition")),
        "hybrid": "Hybrid" if "Hybrid" in other else "",
        "source": _SOURCES.get(found, found),
        "original_filename": stem,
    }


def _encoder(spec: JobSpec) -> Encoder | None:
    if spec.encodes_video:
        return spec.encoder.encoder
    return _REUSED.get(spec.inputs.encode.suffix.lower()) if spec.inputs.encode is not None else None


def _dynamic_range(spec: JobSpec, plan: Plan) -> list[str]:
    video = plan.source.video
    if video is None:
        return []
    out = ["DV"] if hdr.keeps_dv(video, spec.encoder) else []
    if hdr.keeps_hdr10plus(video, spec.encoder):
        out.append("HDR10+")
    elif video.color.transfer == "smpte2084" and video.hdr.dv_profile != 5:  # profile 5's base layer isn't HDR10
        out.append("HDR")
    elif video.color.transfer == "arib-std-b67":
        out.append("HLG")
    return out


def tokens(spec: JobSpec, plan: Plan) -> dict[str, str]:
    """Every token's value for the job."""
    out = name_tokens(source_stem(plan))
    video = plan.source.video
    if video is not None:
        size = spec.video.output_size(video.width, video.height) if spec.encodes_video else (video.width, video.height)
        out["resolution"] = resolution_class(*size) if size[0] > 0 and size[1] > 0 else ""
    else:
        out["resolution"] = ""
    enc = _encoder(spec)
    out["video_codec"] = _CODEC[enc] if enc else ""
    out["video_format"] = _FORMAT[enc] if enc else ""
    out["video_bit_depth_dash"] = f"{spec.encoder.depth}-Bit" if spec.encodes_video else ""
    ranges = _dynamic_range(spec, plan)
    out["video_dynamic_range"] = ("HDR" if ranges else "SDR") if video is not None else ""
    out["video_dynamic_range_type"] = " ".join(ranges)
    first = plan.audio[0] if plan.audio else None
    out["audio_codec"] = _AUDIO.get(first.out_codec, "") if first else ""
    out["audio_channel_s"] = str(first.out_layout) if first else ""
    atmos = first is not None and first.out_atmos and first.out_codec in (AudioCodec.TRUEHD, AudioCodec.EAC3)
    out["atmos"] = "Atmos" if atmos else ""
    return out


def render(template: str, values: dict[str, str]) -> str:
    """The template with its tokens filled in; an unknown token stays as typed. Spaces and dots left doubled by
    empty tokens are made single, and the ends trimmed."""

    def fill(m: re.Match[str]) -> str:
        pre, name, filters, post = m.group(1) or "", m.group(2), m.group(3), m.group(4) or ""
        if name not in values:
            return m.group(0)
        value = values[name]
        for f in (f.strip() for f in filters.split("|") if f.strip()):
            if f in FILTERS:
                value = FILTERS[f](value)
        return f"{pre}{value}{post}" if value else ""

    text = _TOKEN_RE.sub(fill, template)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\.{2,}", ".", text)
    return text.strip(" .-_")


def template_name(spec: JobSpec, plan: Plan) -> str:
    """The job's name from its template, made a file name; "" when it renders to nothing."""
    from videoforge.core.job import clean_label

    return clean_label(render(spec.mux.name_template or DEFAULT_TEMPLATE, tokens(spec, plan)))


def file_stem(spec: JobSpec, plan: Plan, rule_set: RuleSet) -> str:
    """The output's name without its extension: the name typed for the job, else the template's (when it names
    the file), else the rule set's; then the label and the suffix: `<name>.<label>.<suffix>`."""
    from videoforge.core.job import clean_label

    name = spec.output_name
    if not name and spec.mux.template_file_name:
        name = template_name(spec, plan)
    name = name or rule_set.output_stem(plan)
    suffix = clean_label(spec.mux.name_suffix).lstrip(".")
    return ".".join(p for p in (name, spec.label, suffix) if p)


def title(spec: JobSpec, plan: Plan) -> str:
    """The output's title (an MKV's segment title): the template's name when the job asks for it, else none."""
    return template_name(spec, plan) if spec.mux.template_title else ""


def issues(spec: JobSpec) -> list[Issue]:
    """An unknown token or filter in the job's template, when the template is used."""
    if not (spec.mux.template_file_name or spec.mux.template_title) or not spec.mux.name_template:
        return []
    out = []
    for m in _TOKEN_RE.finditer(spec.mux.name_template):
        if m.group(2) not in _NAMES:
            out.append(Issue(Severity.WARN, "name.token", f"Unknown token {m.group(0)} in the name template"))
        bad = [f.strip() for f in m.group(3).split("|") if f.strip() and f.strip() not in FILTERS]
        if bad:
            out.append(Issue(Severity.WARN, "name.filter", f"Unknown filter {', '.join(bad)} in {m.group(0)}"))
    return out
