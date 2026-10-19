"""Match a batch of files into jobs: one source, its encode, external subtitles and chapters.

Files come in as explicit slots (sources, encodes, subtitles, chapters) or as one
mixed drop that is sorted first. Everything is matched to a source by stem
("Show.S01E01" + a configured suffix such as "_job") or by its SxxEyy token; with
a single source, every added subtitle and chapter file belongs to it.

Extras, each switchable in MatchRules:
    scan_source_folder   SRTs next to the source and one folder down (e.g. subs/)
    staxrip_temp         <source>_temp/<encode>_staxrip.log ("Job Complete") for the
                         encode state, and a_qpf/qpf_chapters.txt for chapters, while
                         StaxRip still does the video. Without it, an encode still
                         open for writing counts as in progress.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
import os
from pathlib import Path
import re

from videoforge.core import lang
from videoforge.core.models import EncodeState, JobInputs, SubFormat, SubTrack

_EPISODE_RE = re.compile(r"(?i)\bS(\d{1,2})E(\d{1,3})\b")
_TRACK_NO_RE = re.compile(r"(?i)_track(\d+)_")
_TAG_ALIASES = {"forced": "forced", "sdh": "sdh", "hi": "sdh", "cc": "sdh", "dub": "dub", "dubtitle": "dub"}
# Filename words skipped while looking for the language token from the end.
_NOISE_WORDS = {"synced", "sync", "full", "default", "srt", "subs", "sub", "cleaned", "ocr", "fixed"}

# Containers a source can come in (mkvmerge reads them all): MKV, MP4 and MPEG transport streams.
SOURCE_EXTENSIONS = (".mkv", ".mp4", ".m4v", ".m2ts", ".mts", ".ts")
SUBTITLE_EXTENSIONS = (".srt",)
CHAPTER_EXTENSIONS = (".txt", ".xml")
_CHAPTER_NAME_RE = re.compile(r"(?i)chapter|qpf")


@dataclass(frozen=True, slots=True)
class MatchRules:
    encode_suffixes: tuple[str, ...] = ("_job", "_out", "_new", "")
    encode_extensions: tuple[str, ...] = (".h264", ".264", ".avc", ".hevc", ".265", ".h265")
    scan_source_folder: bool = True
    staxrip_temp: bool = True


@dataclass(slots=True)
class FileSets:
    sources: list[Path] = field(default_factory=list)
    encodes: list[Path] = field(default_factory=list)
    subtitles: list[Path] = field(default_factory=list)
    chapters: list[Path] = field(default_factory=list)


@dataclass(slots=True)
class MatchResult:
    jobs: list[JobInputs]
    unmatched: FileSets  # encodes, subtitles and chapters no source claimed


def episode_token(name: str) -> str | None:
    m = _EPISODE_RE.search(name)
    return f"S{int(m.group(1)):02d}E{int(m.group(2)):02d}" if m else None


def is_chapter_file(path: Path) -> bool:
    return path.suffix.lower() in CHAPTER_EXTENSIONS and bool(_CHAPTER_NAME_RE.search(path.name))


def expand(paths: Iterable[Path], extensions: Iterable[str]) -> list[Path]:
    """Files as given, plus matching files one level inside any folders (sorted, de-duplicated)."""
    wanted = {e.lower() for e in extensions}
    out: list[Path] = []
    for p in paths:
        if p.is_dir():
            out.extend(sorted(c for c in p.iterdir() if c.is_file() and c.suffix.lower() in wanted))
        elif p.suffix.lower() in wanted:
            out.append(p)
    return _unique(out)


def _unique(paths: Iterable[Path]) -> list[Path]:
    seen: set[Path] = set()
    unique = []
    for p in paths:
        key = p.resolve()
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def sort_files(files: Iterable[Path], rules: MatchRules, has_audio: Callable[[Path], bool]) -> FileSets:
    """Sort a mixed drop into slots. A container without audio (an MKV, an MP4) is an encode."""
    raw = {e.lower() for e in rules.encode_extensions}
    sets = FileSets()
    for f in files:
        ext = f.suffix.lower()
        if ext in SUBTITLE_EXTENSIONS:
            sets.subtitles.append(f)
        elif is_chapter_file(f):
            sets.chapters.append(f)
        elif ext in raw:
            sets.encodes.append(f)
        elif ext in SOURCE_EXTENSIONS:
            (sets.sources if has_audio(f) else sets.encodes).append(f)
    return sets


def slot_files(
    sources: Iterable[Path],
    encodes: Iterable[Path],
    subtitles: Iterable[Path],
    chapters: Iterable[Path],
    rules: MatchRules,
) -> FileSets:
    """Files/folders given per slot (the GUI's job setup) to FileSets.

    Folders are read one level deep. A raw stream found in the source slot counts
    as an encode, so a folder holding both works without filling the encode slot.
    Any .txt/.xml given in the chapters slot is a chapter file, whatever its name.
    """
    raw = tuple(e.lower() for e in rules.encode_extensions)
    in_source = expand(sources, (*SOURCE_EXTENSIONS, *raw))
    return FileSets(
        sources=[p for p in in_source if p.suffix.lower() in SOURCE_EXTENSIONS],
        encodes=_unique([*expand(encodes, (".mkv", *raw)), *(p for p in in_source if p.suffix.lower() in raw)]),
        subtitles=expand(subtitles, SUBTITLE_EXTENSIONS),
        chapters=expand(chapters, CHAPTER_EXTENSIONS),
    )


def discover(paths: Iterable[Path], rules: MatchRules, has_audio: Callable[[Path], bool]) -> MatchResult:
    """Expand files/folders, sort them into slots and match them."""
    exts = {*SOURCE_EXTENSIONS, *rules.encode_extensions, *SUBTITLE_EXTENSIONS, *CHAPTER_EXTENSIONS}
    return match_files(sort_files(expand(paths, exts), rules, has_audio), rules)


def _base_stem(stem: str, suffixes: Iterable[str]) -> str:
    for suffix in sorted((s for s in suffixes if s), key=len, reverse=True):
        if stem.endswith(suffix):
            return stem[: -len(suffix)]
    return stem


def _belongs(path: Path, source: Path) -> bool:
    token = episode_token(source.stem)
    return path.name.startswith(source.stem + ".") or bool(token and episode_token(path.stem) == token)


def match_files(sets: FileSets, rules: MatchRules) -> MatchResult:
    """One job per source.

    Encodes match by "<source stem><suffix>", then by SxxEyy; subtitles and
    chapters by a "<source stem>." prefix or SxxEyy. A lone source takes a lone
    encode and every subtitle/chapter file regardless of name.
    """
    sources = _unique(sets.sources)
    encodes = _unique(sets.encodes)
    remaining = list(encodes)
    by_stem = {_base_stem(e.stem, rules.encode_suffixes): e for e in encodes}
    jobs: list[JobInputs] = []
    for s in sources:
        match = by_stem.get(s.stem)
        if match is None and (token := episode_token(s.stem)):
            same_ep = [e for e in remaining if episode_token(e.stem) == token]
            match = same_ep[0] if len(same_ep) == 1 else None
        if match is not None and match in remaining:
            remaining.remove(match)
        else:
            match = None
        jobs.append(JobInputs(s, match))

    if len(jobs) == 1 and jobs[0].encode is None and len(remaining) == 1:
        jobs[0].encode = remaining.pop()

    lone = len(jobs) == 1
    subs_left, chapters_left = _unique(sets.subtitles), _unique(sets.chapters)
    near: dict[Path, list[Path]] = {}  # one listing per source folder (slow on network shares)
    for job in jobs:
        mine = [p for p in subs_left if lone or _belongs(p, job.source)]
        subs_left = [p for p in subs_left if p not in mine]
        if rules.scan_source_folder:
            folder = job.source.parent
            if folder not in near:
                near[folder] = subtitles_near(folder)
            mine += find_external_subs(job.source, near[folder])
        job.subtitles = sorted(_unique(mine))

        chapters = [p for p in chapters_left if lone or _belongs(p, job.source)]
        chapters_left = [p for p in chapters_left if p not in chapters]
        if chapters:
            job.chapters = chapters[0]
        elif rules.staxrip_temp:
            job.chapters = find_qpf_chapters(job.source)
        if job.encode is not None:
            job.encode_state = encode_state(job.source, job.encode, rules.staxrip_temp)
    return MatchResult(jobs, FileSets(encodes=remaining, subtitles=subs_left, chapters=chapters_left))


def staxrip_temp_dir(source: Path) -> Path:
    return source.with_name(source.name + "_temp")


def encode_state(source: Path, encode: Path, use_staxrip_log: bool = True) -> EncodeState:
    log = staxrip_temp_dir(source) / f"{encode.stem}_staxrip.log"
    if use_staxrip_log and log.exists():
        try:
            text = log.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return EncodeState.IN_PROGRESS
        return EncodeState.DONE if "Job Complete" in text else EncodeState.IN_PROGRESS
    return EncodeState.IN_PROGRESS if _is_locked(encode) else EncodeState.UNKNOWN


def _is_locked(path: Path) -> bool:
    """On Windows a file another process has open for writing can't be renamed."""
    try:
        os.rename(path, path)
    except OSError:
        return True
    return False


def find_qpf_chapters(source: Path) -> Path | None:
    chapters = staxrip_temp_dir(source) / "a_qpf" / "qpf_chapters.txt"
    return chapters if chapters.exists() else None


def subtitles_near(folder: Path) -> list[Path]:
    """SRTs in a folder and one folder down (skipping StaxRip *_temp dirs)."""
    folders = [folder] + sorted(d for d in folder.iterdir() if d.is_dir() and not d.name.endswith("_temp"))
    return [p for f in folders for p in f.iterdir() if p.suffix.lower() in SUBTITLE_EXTENSIONS]


def find_external_subs(source: Path, near: list[Path] | None = None) -> list[Path]:
    """SRTs next to the source or one folder down that share its stem or SxxEyy token.

    near: subtitles_near(source.parent), when the caller lists it once for many sources.
    """
    near = subtitles_near(source.parent) if near is None else near
    return sorted(p for p in near if _belongs(p, source))


def _language_from_name(stem: str) -> str | None:
    """Language token searched from the end: "...en.synced", "..._[eng]", "Movie.en.forced"."""
    tokens = [t for t in re.split(r"[.\s_\[\]()-]+", stem) if t]
    for token in reversed(tokens):
        low = token.lower()
        if low in _TAG_ALIASES or low in _NOISE_WORDS:
            continue
        code = lang.normalize(low)
        known = len(low) in (2, 3) and lang.display_name(code) != code
        if known or "-" in token and lang.normalize(token) != "und":
            return lang.normalize(token)
        return None
    return None


def _language_with_region(stem: str) -> str | None:
    """Tokens like "es-419" / "fr-FR" survive splitting on "-", so check them first."""
    for m in re.finditer(r"(?i)(?<![a-z])([a-z]{2,3}-(?:[a-z]{2}|\d{3}|hans|hant))(?![a-z])", stem):
        tag = lang.normalize(m.group(1))
        if lang.has_variant(tag):
            return tag
    return None


def srt_entry_count(path: Path) -> int | None:
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace").count("-->")
    except OSError:
        return None


AUDIO_EXTENSIONS = (
    ".ac3",
    ".eac3",
    ".ec3",
    ".dts",
    ".dtshd",
    ".thd",
    ".truehd",
    ".mlp",
    ".flac",
    ".wav",
    ".w64",
    ".m4a",
    ".aac",
    ".mka",
    ".opus",
    ".ogg",
)
_DELAY_RE = re.compile(r"\bdelay\s*(-?\d+)\s*ms\b", re.IGNORECASE)


def name_language(stem: str) -> str | None:
    """The language a file name carries ("Movie.en.srt", "[eng]", "es-419"), if any."""
    language = _language_with_region(stem) or _language_from_name(stem)
    return language if language and language != "und" else None


def name_without_delay(stem: str) -> str:
    return _DELAY_RE.sub(" ", stem)


def name_delay_ms(stem: str) -> int | None:
    """eac3to-style "DELAY -42ms" in a file name."""
    m = _DELAY_RE.search(stem)
    return int(m.group(1)) if m else None


SUB_FORMATS = {
    ".srt": SubFormat.SRT,
    ".ass": SubFormat.ASS,
    ".ssa": SubFormat.ASS,
    ".sup": SubFormat.PGS,
    ".idx": SubFormat.VOBSUB,
}


def external_sub_track(path: Path, source_stem: str, index: int, *, keep_unknown: bool = False) -> SubTrack | None:
    """Turn an external subtitle file (SRT, ASS/SSA, SUP, IDX) into a SubTrack, or None if no
    language can be found (with keep_unknown, it is kept as "und" for the user to set).

    Language comes from the last language-like token ("en", "[eng]", "es-419");
    forced/sdh/dub words become tags; "_trackN_" (gMKVExtract) links the file
    back to the source track it was extracted from.
    """
    stem = path.stem
    words = {w.lower() for w in re.split(r"[.\s_\[\]()-]+", stem)}
    tags = frozenset(_TAG_ALIASES[w] for w in words if w in _TAG_ALIASES)
    language = _language_with_region(stem) or _language_from_name(stem)
    if not language or language == "und":
        if not keep_unknown:
            return None
        language = "und"
    m = _TRACK_NO_RE.search(stem)
    fmt = SUB_FORMATS.get(path.suffix.lower(), SubFormat.OTHER)
    return SubTrack(
        id=-1,
        index=1000 + index,  # sorts after source tracks when preferences tie
        format=fmt,
        language=language,
        title="",
        forced="forced" in tags,
        hearing_impaired="sdh" in tags,
        element_count=srt_entry_count(path) if fmt is SubFormat.SRT else None,
        external_path=path,
        extracted_from=int(m.group(1)) if m else None,
        tags=tags,
    )
