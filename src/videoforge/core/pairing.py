"""Match a batch of files into jobs: one source, its encode, external subtitles and chapters.

Files come in as explicit slots (sources, encodes, subtitles, chapters) or as one
mixed drop that is sorted first. Everything is matched to a source by stem
("Show.S01E01" + a configured suffix such as "_job") or by its SxxEyy token; with
a single source, every added subtitle and chapter file belongs to it. With several,
a subtitle or chapter file no name ties to a source goes to the one its name is
clearly closest to (rank_sources), and the user can match any file by hand.

Extras, each switchable in MatchRules:
    scan_source_folder   subtitles next to the source and one folder down (e.g. subs/),
                         for a source given no subtitle files of its own
    staxrip_temp         <source>_temp/<encode>_staxrip.log ("Job Complete") for the
                         encode state, and a_qpf/qpf_chapters.txt for chapters, while
                         StaxRip still does the video. Without it, an encode still
                         open for writing counts as in progress.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import os
from pathlib import Path
import re
from typing import Any

from videoforge.core import lang, match_names as names_
from videoforge.core.match_names import episode_token
from videoforge.core.models import EncodeState, JobInputs, SubFormat, SubTrack

# What may follow a source's name in a file named after it: "Show.S01E01.en.srt", "Show.S01E01_track3_".
_NAME_SEPARATORS = "._- [("
_TRACK_NO_RE = re.compile(r"(?i)_track(\d+)_")
_TAG_ALIASES = {
    "forced": "forced",
    "force": "forced",
    "sdh": "sdh",
    "hi": "sdh",
    "cc": "sdh",
    "dub": "dub",
    "dubtitle": "dub",
}
# Filename words skipped while looking for the language token from the end.
_NOISE_WORDS = {"synced", "sync", "full", "default", "srt", "subs", "sub", "cleaned", "ocr", "fixed"}

# Containers a source can come in (mkvmerge reads them all): MKV, MP4 and MPEG transport streams.
SOURCE_EXTENSIONS = (".mkv", ".mp4", ".m4v", ".m2ts", ".mts", ".ts")
# A VobSub is picked up by its .idx; the .sub beside it goes along.
SUB_FORMATS = {
    ".srt": SubFormat.SRT,
    ".ass": SubFormat.ASS,
    ".ssa": SubFormat.ASS,
    ".sup": SubFormat.PGS,
    ".idx": SubFormat.VOBSUB,
}
SUBTITLE_EXTENSIONS = tuple(SUB_FORMATS)
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
    # How files were placed where their names alone don't say (match_reason covers the rest): "manual" (by the
    # user, also for an unmatched file they set to no source), "episode" (its episode number alone), "number"
    # (its place in a numbered set), "similar" (the closest name) or "staxrip" (StaxRip temp folder chapters).
    how: dict[Path, str] = field(default_factory=dict)
    # Per unmatched file, sources to offer, best first, each with why: "pattern" or "similar" (match_files).
    suggestions: dict[Path, list[tuple[Path, str]]] = field(default_factory=dict)


def is_chapter_file(path: Path) -> bool:
    return path.suffix.lower() in CHAPTER_EXTENSIONS and bool(_CHAPTER_NAME_RE.search(path.name))


# On a network share every look at the disk is a round trip (about 12 ms each on an SMB drive), so a season
# of files is listed with os.scandir (a file's kind comes with the listing on Windows), the given paths are
# checked side by side, and paths are compared as text, never resolved.


def _key(path: Path) -> str:
    """A path as the file system compares it (Windows: case-insensitive), without touching the disk."""
    return os.path.normcase(os.path.abspath(path))


def _are_dirs(paths: list[Path]) -> list[bool]:
    """Which of the given paths are folders, checked side by side."""
    if len(paths) < 2:
        return [p.is_dir() for p in paths]
    with ThreadPoolExecutor(max_workers=min(16, len(paths))) as pool:
        return list(pool.map(Path.is_dir, paths))


def _ext(name: str) -> str:
    return os.path.splitext(name)[1].lower()


def expand(paths: Iterable[Path], extensions: Iterable[str]) -> list[Path]:
    """Files as given, plus matching files one level inside any folders (sorted, de-duplicated)."""
    wanted = {e.lower() for e in extensions}
    given = list(paths)
    out: list[Path] = []
    for p, is_dir in zip(given, _are_dirs(given), strict=True):
        if is_dir:
            with os.scandir(p) as listing:
                out.extend(sorted(Path(f.path) for f in listing if f.is_file() and _ext(f.name) in wanted))
        elif p.suffix.lower() in wanted:
            out.append(p)
    return _unique(out)


def _unique(paths: Iterable[Path]) -> list[Path]:
    seen: set[str] = set()
    unique = []
    for p in paths:
        key = _key(p)
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


def _natural_key(path: Path) -> tuple[Any, ...]:
    """Names in the order a person reads them: E2 before E10."""
    parts = re.split(r"(\d+)", path.name.lower())
    return (*(int(p) if i % 2 else p for i, p in enumerate(parts)), str(path))


def _named_after(path: Path, source: Path) -> bool:
    """The file's name is the source's name and more: "Show.S01E01.en.srt", "Show.S01E01_track3_[eng].srt"."""
    name, stem = path.name.casefold(), source.stem.casefold()
    return len(name) > len(stem) and name.startswith(stem) and name[len(stem)] in _NAME_SEPARATORS


def _belongs(path: Path, source: Path) -> bool:
    """Tied to the source by its name alone: named after it, or the same SxxEyy."""
    token = episode_token(source.stem)
    return _named_after(path, source) or bool(token and episode_token(path.stem) == token)


def _other_episode(a: tuple[int | None, int] | None, b: tuple[int | None, int] | None) -> bool:
    """Two (season, episode) that can't be the same episode; a missing season fits any."""
    return bool(a and b and (a[1] != b[1] or (None not in (a[0], b[0]) and a[0] != b[0])))


def rank_sources(path: Path, sources: list[Path]) -> list[tuple[Path, float]]:
    """The sources a file's name is closest to, best first, each scored 0-1: the share of the words that set a
    source's name apart from the batch's other sources ("S01E04", "Movie", "2001", not "1080p" or "BluRay") that
    the file's name also has; an SxxEyy also counts when the file has only its episode number ("Show - 04.ass").
    A source for another episode is never a candidate. Equal scores go by how alike the names read."""
    if not sources:
        return []
    names = [names_.words(s.stem) for s in sources]
    shared = set.intersection(*names) if len(names) > 1 else set()
    words, mine = names_.words(path.stem), names_.episode_of(path.stem)
    ranked = []
    for source, own in zip(sources, names, strict=True):
        theirs = names_.episode_of(source.stem)
        if _other_episode(mine, theirs):
            continue
        token = episode_token(source.stem)
        number = str(theirs[1]) if theirs else None

        def found(w: str, token: str | None = token, number: str | None = number) -> bool:
            return w in words or (token is not None and number in words and episode_token(w) == token)

        apart = own - shared
        if apart and (hits := sum(map(found, apart))):
            ranked.append((source, hits / len(apart), names_.likeness(path.stem, source.stem)))
    ranked.sort(key=lambda r: (-r[1], -r[2]))
    return [(s, score) for s, score, _ in ranked]


def _closest(path: Path, sources: list[Path]) -> Path | None:
    """The one source a file is clearly named for: at least half its telling words, and more than any other."""
    ranked = rank_sources(path, sources)
    if not ranked or ranked[0][1] < 0.5 or (len(ranked) > 1 and ranked[1][1] >= ranked[0][1]):
        return None
    return ranked[0][0]


class _Numbered:
    """The batch's sources by their number: each one's episode, or the number that tells their names apart."""

    def __init__(self, sources: list[Path]) -> None:
        nums = names_.numbering([s.stem for s in sources])
        self.by_number = dict(zip(nums, sources, strict=True)) if nums else {}
        self.number_of = {s: n for n, s in self.by_number.items()}
        eps = [names_.episode_of(s.stem) for s in sources]
        self.seasons = {e[0] for e in eps if e}
        # the numbers are episodes (not, say, the season of "S01E01" and "S02E01")
        self.episodes = bool(nums) and all(eps) and nums == [e[1] for e in eps if e]

    def by_episode(self, path: Path) -> Path | None:
        """The source for a file whose name has only an episode number ("E04", "Show - 04"), or an SxxEyy in
        another spelling than the sources'; a season counts only when the sources all have the one season."""
        ep = names_.episode_of(path.stem)
        if not ep or not self.episodes or (ep[0] is not None and len(self.seasons) > 1):
            return None
        source = self.by_number.get(ep[1])
        return source if source and not _other_episode(ep, names_.episode_of(source.stem)) else None

    def by_position(self, files: list[Path]) -> dict[Path, Path]:
        """Files of one set (at least two of the same shape) whose changing number lines up with the sources'."""
        out: dict[Path, Path] = {}
        if not self.by_number:
            return out
        groups: dict[str, list[Path]] = {}
        for f in files:
            groups.setdefault(names_.shape(f.stem), []).append(f)
        for group in groups.values():
            at = names_.numbered_position([f.stem for f in group], set(self.by_number))
            if at is not None:
                out |= {f: self.by_number[names_.numbers(f.stem)[at]] for f in group}
        return out

    def like(self, example: Path, source: Path, files: list[Path]) -> dict[Path, Path]:
        """Files shaped like one the user matched, matched the same way: the number standing where the source's
        number stands in the example's name picks each one's source."""
        n = self.number_of.get(source)
        at = names_.position_of(example.stem, n) if n is not None else None
        if at is None:
            return {}
        same = names_.shape(example.stem)
        out = {}
        for f in files:
            if f != example and names_.shape(f.stem) == same and (s := self.by_number.get(names_.numbers(f.stem)[at])):
                out[f] = s
        return out


def _assigned(assign: Mapping[Path, Path | None] | None, sources: list[Path]) -> dict[str, tuple[Path, Path | None]]:
    """The user's matches, file key -> (file, source or None for no source), to sources in this batch only."""
    by_key = {_key(s): s for s in sources}
    out: dict[str, tuple[Path, Path | None]] = {}
    for f, s in (assign or {}).items():
        if s is None or not str(s) or str(s) == ".":
            out[_key(f)] = (f, None)
        elif _key(s) in by_key:
            out[_key(f)] = (f, by_key[_key(s)])
    return out


def match_files(sets: FileSets, rules: MatchRules, assign: Mapping[Path, Path | None] | None = None) -> MatchResult:
    """One job per source.

    assign: files the user matched by hand, file -> source, or -> None for no source; they go first and win
    over any other match. A subtitle found near a source can be moved too.

    Encodes match by "<source stem><suffix>", then by SxxEyy. Subtitles and chapters, strongest first: named
    after the source (its name, then a separator), the same SxxEyy; then, with several sources, for a file no
    name ties to any: its episode number alone ("E04", "Show - 04"), its place in a set of files whose changing
    number lines up with the sources' ("number"), or the one source its name is clearly closest to
    (rank_sources, "similar"). A lone source takes a lone encode and every subtitle/chapter file regardless of
    name. Subtitles found near the source only fill in for a source given none of its own.

    Each file left unmatched gets suggestions: the source it would go to the way the user matched a file of its
    shape ("pattern"), then the closest names ("similar").
    """
    sources = sorted(_unique(sets.sources), key=_natural_key)  # one job per episode, in episode order
    manual = _assigned(assign, sources)
    how: dict[Path, str] = {}

    def by_hand(files: list[Path], source: Path) -> list[Path]:
        mine = [f for f in files if (m := manual.get(_key(f))) and m[1] == source]
        how.update(dict.fromkeys(mine, "manual"))
        return mine

    encodes = _unique(sets.encodes)
    remaining = [e for e in encodes if _key(e) not in manual]
    by_stem = {_base_stem(e.stem, rules.encode_suffixes): e for e in remaining}
    jobs: list[JobInputs] = []
    for s in sources:
        chosen = by_hand(encodes, s)
        match = chosen[0] if chosen else by_stem.get(s.stem)
        if not chosen and match is None and (token := episode_token(s.stem)):
            same_ep = [e for e in remaining if episode_token(e.stem) == token]
            match = same_ep[0] if len(same_ep) == 1 else None
        if match is not None and match in remaining:
            remaining.remove(match)
        elif not chosen:
            match = None
        for extra in chosen[1:]:  # one encode per job: more matched to it by hand stay unmatched
            how.pop(extra)
            remaining.append(extra)
        jobs.append(JobInputs(s, match))

    if len(jobs) == 1 and jobs[0].encode is None and len(remaining) == 1:
        jobs[0].encode = remaining.pop()

    near: dict[Path, list[Path]] = {}  # one listing per source folder (slow on network shares)

    def near_of(folder: Path) -> list[Path]:
        if folder not in near:
            near[folder] = subtitles_near(folder)
        return near[folder]

    # A subtitle found near a source that the user matched by hand joins the added ones (if it's still there).
    added = {_key(p) for p in [*sets.subtitles, *sets.chapters, *encodes]}
    moved: list[Path] = []
    if rules.scan_source_folder and any(k not in added for k in manual):
        for folder in dict.fromkeys(s.parent for s in sources):
            moved += [p for p in near_of(folder) if _key(p) in manual and _key(p) not in added]

    lone = len(jobs) == 1
    all_subs, all_chapters = _unique([*sets.subtitles, *moved]), _unique(sets.chapters)
    subs_left = [p for p in all_subs if _key(p) not in manual]
    chapters_left = [p for p in all_chapters if _key(p) not in manual]
    numbered = _Numbered(sources)
    found: dict[Path, Path] = {}  # file -> source, for files no name ties to any source
    if not lone:
        untied = [p for p in subs_left + chapters_left if not any(_belongs(p, s) for s in sources)]
        for p in untied:
            if source := numbered.by_episode(p):
                found[p], how[p] = source, "episode"
        rest = [p for p in untied if p not in found]
        for p, source in numbered.by_position(rest).items():
            found[p], how[p] = source, "number"
        for p in rest:
            if p not in found and (source := _closest(p, sources)):
                found[p], how[p] = source, "similar"
    for job in jobs:
        src = job.source
        mine = [p for p in subs_left if lone or _belongs(p, src) or found.get(p) == src]
        subs_left = [p for p in subs_left if p not in mine]
        if rules.scan_source_folder and not mine:  # added subtitles replace the ones found near it
            mine += [p for p in find_external_subs(src, near_of(src.parent)) if _key(p) not in manual]
        job.subtitles = sorted(_unique([*by_hand(all_subs, src), *mine]))

        chapters = by_hand(all_chapters, src)
        chapters += [p for p in chapters_left if lone or _belongs(p, src) or found.get(p) == src]
        chapters_left = [p for p in chapters_left if p not in chapters]
        if chapters:
            job.chapters = chapters[0]
        elif rules.staxrip_temp and (qpf := find_qpf_chapters(src)):
            job.chapters, how[qpf] = qpf, "staxrip"
        if job.encode is not None:
            job.encode_state = encode_state(src, job.encode, rules.staxrip_temp)

    # Files the user set to no source stay unmatched, marked as theirs.
    held = {_key(f) for f, s in manual.values() if s is None}
    left = FileSets(
        encodes=remaining + [p for p in encodes if _key(p) in held],
        subtitles=subs_left + [p for p in all_subs if _key(p) in held],
        chapters=chapters_left + [p for p in all_chapters if _key(p) in held],
    )
    unmatched = [*left.encodes, *left.subtitles, *left.chapters]
    how.update({p: "manual" for p in unmatched if _key(p) in held})
    examples = [(f, s) for f, s in manual.values() if s is not None]
    return MatchResult(jobs, left, how, _suggest(unmatched, sources, numbered, examples))


SUGGESTIONS = 3  # sources offered for an unmatched file


def _suggest(
    unmatched: list[Path], sources: list[Path], numbered: _Numbered, examples: list[tuple[Path, Path]]
) -> dict[Path, list[tuple[Path, str]]]:
    """Sources to offer each unmatched file, best first: the one it would go to the way the user matched a file of
    its shape ("pattern"), then the closest names ("similar")."""
    learned: dict[Path, Path] = {}
    for example, source in examples:
        learned = numbered.like(example, source, unmatched) | learned  # the first example wins
    out: dict[Path, list[tuple[Path, str]]] = {}
    for p in unmatched:
        offer = [(learned[p], "pattern")] if p in learned else []
        offer += [(s, "similar") for s, _ in rank_sources(p, sources) if s != learned.get(p)]
        out[p] = offer[:SUGGESTIONS]
    return out


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
    """Subtitle files in a folder and one folder down (skipping StaxRip *_temp dirs)."""
    with os.scandir(folder) as listing:
        here = list(listing)
    found = [Path(f.path) for f in here if _ext(f.name) in SUBTITLE_EXTENSIONS]
    for sub in sorted((Path(d.path) for d in here if d.is_dir() and not d.name.endswith("_temp")), key=str):
        with os.scandir(sub) as listing:
            found += [Path(f.path) for f in listing if _ext(f.name) in SUBTITLE_EXTENSIONS]
    return found


def find_external_subs(source: Path, near: list[Path] | None = None) -> list[Path]:
    """Subtitle files next to the source or one folder down that share its stem or SxxEyy token.

    near: subtitles_near(source.parent), when the caller lists it once for many sources.
    """
    near = subtitles_near(source.parent) if near is None else near
    return sorted(p for p in near if _belongs(p, source))


def match_reason(path: Path, source: Path) -> str:
    """Why a file went to a source, from the two names, strongest first:
    "name"           it starts with the source's name ("Show.S01E01.mkv" -> "Show.S01E01.en.srt", "Show.S01E01_track3_")
    "episode"        it carries the source's SxxEyy
    "only_source"    the batch's lone source took it; nothing in the name ties it to that source
    "other_episode"  the lone source took it, but its name carries a different SxxEyy
    match_files also says "manual" (the user matched it) and "similar" (closest name) in MatchResult.how.
    """
    if _named_after(path, source):
        return "name"
    mine, theirs = episode_token(source.stem), episode_token(path.stem)
    if mine and theirs == mine:
        return "episode"
    return "other_episode" if mine and theirs else "only_source"


def subtitle_label(path: Path, source: Path | None = None, how: str | None = None) -> dict[str, Any]:
    """What Matched files shows for a subtitle file, read from its name alone (nothing is opened):
    language, format, forced/sdh/dub and synced words, the source track it was extracted from, and
    (given the source it matched) why it matched: how (MatchResult.how) or else as match_reason says."""
    stem = path.stem
    words = {w.lower() for w in re.split(r"[.\s_\[\]()-]+", stem)}
    tags = sorted({_TAG_ALIASES[w] for w in words if w in _TAG_ALIASES})
    if words & {"synced", "sync"}:
        tags.append("synced")
    language = _language_with_region(stem) or _language_from_name(stem) or "und"
    m = _TRACK_NO_RE.search(stem)
    return {
        "path": str(path),
        "language": language,
        "language_name": lang.display_name(language),
        "format": path.suffix.lower().lstrip("."),
        "tags": tags,
        "track": int(m.group(1)) if m else None,
        "match": how or (match_reason(path, source) if source is not None else None),
    }


def _language_from_name(stem: str) -> str | None:
    """Language token searched from the end: "...en.synced", "..._[eng]", "Movie.en.forced"."""
    tokens = [t for t in re.split(r"[.\s_\[\]()-]+", stem) if t]
    for token in reversed(tokens):
        low = token.lower()
        if low in _TAG_ALIASES or low in _NOISE_WORDS:
            continue
        named = lang.from_name(low)
        if named:
            return named
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
    ".mp3",
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
