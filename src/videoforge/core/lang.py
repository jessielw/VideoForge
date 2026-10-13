"""Language normalization.

Everything is normalized to a short IETF tag. Regions are dropped except for the
variant families the spec cares about (Spanish, French, Chinese), which keep a
canonical variant: es-419 / es-ES, fr-FR / fr-CA, zh-Hans / zh-Hant / yue.
"""

from __future__ import annotations

import re

# 2-letter code -> (English name, ISO 639-2 codes)
_LANGS: dict[str, tuple[str, tuple[str, ...]]] = {
    "ar": ("Arabic", ("ara",)),
    "bg": ("Bulgarian", ("bul",)),
    "ca": ("Catalan", ("cat",)),
    "cs": ("Czech", ("cze", "ces")),
    "da": ("Danish", ("dan",)),
    "de": ("German", ("ger", "deu")),
    "el": ("Greek", ("gre", "ell")),
    "en": ("English", ("eng",)),
    "es": ("Spanish", ("spa",)),
    "et": ("Estonian", ("est",)),
    "fa": ("Persian", ("per", "fas")),
    "fi": ("Finnish", ("fin",)),
    "fil": ("Filipino", ("fil", "tgl")),
    "fr": ("French", ("fre", "fra")),
    "he": ("Hebrew", ("heb",)),
    "hi": ("Hindi", ("hin",)),
    "hr": ("Croatian", ("hrv",)),
    "hu": ("Hungarian", ("hun",)),
    "id": ("Indonesian", ("ind",)),
    "is": ("Icelandic", ("ice", "isl")),
    "it": ("Italian", ("ita",)),
    "ja": ("Japanese", ("jpn",)),
    "ko": ("Korean", ("kor",)),
    "lt": ("Lithuanian", ("lit",)),
    "lv": ("Latvian", ("lav",)),
    "ms": ("Malay", ("may", "msa")),
    "nl": ("Dutch", ("dut", "nld")),
    "no": ("Norwegian", ("nor", "nob", "nno")),
    "pl": ("Polish", ("pol",)),
    "pt": ("Portuguese", ("por",)),
    "ro": ("Romanian", ("rum", "ron")),
    "ru": ("Russian", ("rus",)),
    "sk": ("Slovak", ("slo", "slk")),
    "sl": ("Slovenian", ("slv",)),
    "sr": ("Serbian", ("srp",)),
    "sv": ("Swedish", ("swe",)),
    "ta": ("Tamil", ("tam",)),
    "te": ("Telugu", ("tel",)),
    "th": ("Thai", ("tha",)),
    "tr": ("Turkish", ("tur",)),
    "uk": ("Ukrainian", ("ukr",)),
    "vi": ("Vietnamese", ("vie",)),
    "zh": ("Chinese", ("chi", "zho", "cmn")),
    "yue": ("Cantonese", ("yue",)),
}

_ISO3_TO_2 = {iso3: code for code, (_, iso3s) in _LANGS.items() for iso3 in iso3s}
_NAME_TO_2 = {name.lower(): code for code, (name, _) in _LANGS.items()}
_NAME_TO_2.update({"mandarin": "zh", "flemish": "nl", "castilian": "es", "farsi": "fa"})

FAMILY_VARIANTS = {"es", "fr", "zh"}

VARIANT_LABELS = {
    "es-419": "Latin American",
    "es-ES": "Castilian",
    "fr-FR": "Parisian",
    "fr-CA": "Canadian",
    "zh-Hans": "Simplified",
    "zh-Hant": "Traditional",
    "yue": "Cantonese",
}

# Title hints, checked in order (most specific first).
_TITLE_HINTS: list[tuple[str, re.Pattern[str]]] = [
    ("yue", re.compile(r"(?i)cantonese|\byue\b")),
    ("zh-Hans", re.compile(r"(?i)simplified|\bhans\b|简")),
    ("zh-Hant", re.compile(r"(?i)traditional|\bhant\b|taiwan|繁")),
    ("es-419", re.compile(r"(?i)latin|latam|\b419\b|m[eé]xic|americas?\b")),
    ("es-ES", re.compile(r"(?i)castilian|castellano|spain|espa[nñ]a|\bes-es\b|european|iberian")),
    ("fr-CA", re.compile(r"(?i)canad|qu[eé]b")),
    ("fr-FR", re.compile(r"(?i)parisian|france|metropolitan|\bfr-fr\b|european")),
]


def _region_variant(base: str, rest: list[str]) -> str | None:
    """Map region/script subtags of a family language to its canonical variant."""
    parts = [p.lower() for p in rest]
    if base == "es":
        if "es" in parts:
            return "es-ES"
        if parts and any(p == "419" or (len(p) == 2 and p != "es") for p in parts):
            return "es-419"  # es-MX, es-AR, es-US ... are Latin American
    elif base == "fr":
        if "ca" in parts:
            return "fr-CA"
        if any(p in ("fr", "be", "ch", "lu") for p in parts):
            return "fr-FR"
    elif base == "zh":
        # Script subtags win over regions ("cmn-Hant-CN" is Traditional).
        if "yue" in parts:
            return "yue"
        if "hans" in parts:
            return "zh-Hans"
        if "hant" in parts:
            return "zh-Hant"
        if any(p in ("cn", "sg") for p in parts):
            return "zh-Hans"
        if any(p in ("tw", "hk", "mo") for p in parts):
            return "zh-Hant"
    return None


def normalize(tag: str | None) -> str:
    """Normalize an IETF/ISO 639 tag ("spa", "es-MX", "cmn-Hant-CN") to our canonical form."""
    if not tag:
        return "und"
    parts = re.split(r"[-_]", tag.strip())
    head = parts[0].lower()
    if head in ("yue",):
        return "yue"
    base = _ISO3_TO_2.get(head, head)
    if head == "cmn":
        base = "zh"
    if base not in _LANGS and len(base) != 2:
        return "und" if head in ("und", "") else head
    if base in FAMILY_VARIANTS:
        return _region_variant(base, parts[1:]) or base
    return base


# MediaInfo text names: "Spanish (Latin America)", "French (CA)", "English (US)", "Mandarin-Hant-CN"
_MI_REGION_WORDS = {
    "latin america": "419",
    "traditional": "Hant",
    "simplified": "Hans",
}


def from_mediainfo_name(value: str | None) -> str:
    """Parse a MediaInfo *display* language ("Spanish (Latin America)") into a tag."""
    if not value:
        return "und"
    value = value.strip()
    m = re.match(r"^([^(]+?)\s*(?:\(([^)]+)\))?$", value)
    if not m:
        return normalize(value)
    name, region = m.group(1).strip(), (m.group(2) or "").strip()
    if "-" in name and " " not in name:  # e.g. "Mandarin-Hant-CN"
        first, *rest = name.split("-")
        code = _NAME_TO_2.get(first.lower(), first)
        return normalize("-".join([code, *rest]))
    code = _NAME_TO_2.get(name.lower())
    if code is None:
        return normalize(name)
    if region:
        region = _MI_REGION_WORDS.get(region.lower(), region)
        return normalize(f"{code}-{region}")
    return normalize(code)


def variant_from_title(base: str, title: str) -> str | None:
    """Guess a family variant from a track title. Returns None if no hint matches."""
    if base not in FAMILY_VARIANTS or not title:
        return None
    for variant, pattern in _TITLE_HINTS:
        if base_of(variant) == base and pattern.search(title):
            return variant
    return None


def base_of(tag: str) -> str:
    base = tag.split("-")[0]
    return "zh" if base == "yue" else base


def has_variant(tag: str) -> bool:
    return tag in VARIANT_LABELS


def display_name(tag: str) -> str:
    """English name of the base language ("Spanish" for "es-419")."""
    base = base_of(tag)
    return _LANGS.get(base, (tag, ()))[0]


def variant_label(tag: str) -> str | None:
    return VARIANT_LABELS.get(tag)
