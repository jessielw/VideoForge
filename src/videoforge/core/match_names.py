"""Reading file names to match them to sources: episode numbers however they are spelled, a name's words, its
shape (the name with its numbers blanked) and the numbers that set a batch's names apart.

Nothing here touches the disk; pairing.py decides what goes where.
"""

from __future__ import annotations

from collections.abc import Sequence
from difflib import SequenceMatcher
import re

# Episode spellings with a season, as (season, episode). Not \b: "_" is a word character, and gMKVExtract
# names files "Show.S01E01_track7_[eng].srt".
_SEASON_EPISODE = (
    re.compile(r"(?i)(?<![a-z0-9])S(\d{1,2})[ ._-]?E(\d{1,3})(?!\d)"),  # S01E01, S01.E01, s1e1, S01 E01
    re.compile(r"(?<![\d.])(\d{1,2})x(\d{2,3})(?!\d)"),  # 1x01 (not 1920x1080: no digit before; not 5.1x264)
)
# Spellings without one: E01, Ep 01, Episode 1, and the anime "Show - 01 [1080p]" / "Show - 01v2".
_EPISODE_ONLY = (
    re.compile(r"(?i)(?<![a-z0-9])(?:episode|ep|e)[ ._-]?(\d{1,4})(?!\d)"),
    re.compile(r"(?i)(?:^|\s)-\s+(\d{1,4})(?:v\d)?(?![\d.])"),
)
_DIGITS_RE = re.compile(r"\d+")
_WORD_SPLIT_RE = re.compile(r"[\W_]+")


def episode_token(name: str) -> str | None:
    """A name's "SxxEyy", from any spelling with a season ("S1E2", "S01.E02", "1x02")."""
    for pattern in _SEASON_EPISODE:
        if m := pattern.search(name):
            return f"S{int(m.group(1)):02d}E{int(m.group(2)):02d}"
    return None


def episode_of(name: str) -> tuple[int | None, int] | None:
    """A name's (season, episode), the season None where the name has only an episode number."""
    for pattern in _SEASON_EPISODE:
        if m := pattern.search(name):
            return int(m.group(1)), int(m.group(2))
    for pattern in _EPISODE_ONLY:
        if m := pattern.search(name):
            return None, int(m.group(1))
    return None


def words(stem: str) -> set[str]:
    """A name's words, case-folded, numbers without leading zeros ("01" and "1" are the same)."""
    return {str(int(w)) if w.isdigit() else w for w in _WORD_SPLIT_RE.split(stem.casefold()) if w}


def shape(stem: str) -> str:
    """The name with every number blanked: files of one set ("Show - 01.ass", "Show - 02.ass") share it."""
    return _DIGITS_RE.sub("#", stem.casefold())


def numbers(stem: str) -> list[int]:
    return [int(d) for d in _DIGITS_RE.findall(stem)]


def likeness(a: str, b: str) -> float:
    """0-1, how alike two names read (case-folded, separators ignored): a tie-breaker, never a match alone."""
    return SequenceMatcher(None, _clean(a), _clean(b)).ratio()


def _clean(name: str) -> str:
    return " ".join(_WORD_SPLIT_RE.split(name.casefold())).strip()


def numbering(stems: Sequence[str]) -> list[int] | None:
    """The number that tells a set of names apart, one per name: each one's episode when every name has a
    different one, or else the one number that differs between names of the same shape. None if neither."""
    eps = [episode_of(s) for s in stems]
    if all(eps) and len({e[1] for e in eps if e}) == len(stems):
        return [e[1] for e in eps if e]
    if len(stems) > 1 and len({shape(s) for s in stems}) == 1:
        nums = [numbers(s) for s in stems]
        apart = [i for i in range(len(nums[0])) if len({n[i] for n in nums}) > 1]
        if len(apart) == 1 and len({n[apart[0]] for n in nums}) == len(stems):
            return [n[apart[0]] for n in nums]
    return None


def numbered_position(stems: Sequence[str], wanted: set[int]) -> int | None:
    """Which number in a set of same-shape names counts episodes: of the numbers that change between them, the
    one whose values are all among `wanted` (the sources' numbers) and take the most different values. None
    when no number fits or two fit equally."""
    nums = [numbers(s) for s in stems]
    if len(nums) < 2:
        return None
    fits = []
    for i in range(len(nums[0])):
        values = {n[i] for n in nums}
        if len(values) > 1 and values <= wanted:
            fits.append((len(values), i))
    fits.sort(reverse=True)
    if not fits or (len(fits) > 1 and fits[1][0] == fits[0][0]):
        return None
    return fits[0][1]


def position_of(stem: str, number: int) -> int | None:
    """Where a number stands among a name's numbers, if it is there exactly once."""
    at = [i for i, n in enumerate(numbers(stem)) if n == number]
    return at[0] if len(at) == 1 else None
