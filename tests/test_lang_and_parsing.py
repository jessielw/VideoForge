from __future__ import annotations

from pathlib import Path

import pytest

from videoforge.core import lang
from videoforge.core.classify import parse_audio_format, parse_layout
from videoforge.core.mediainfo_text import parse_mediainfo_text
from videoforge.core.models import AudioCodec, JobInputs, Layout, SubFormat
from videoforge.core.pairing import MatchRules, external_sub_track, match_files, sort_files


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("eng", "en"),
        ("en-US", "en"),
        ("spa", "es"),
        ("es-MX", "es-419"),
        ("es-419", "es-419"),
        ("es-ES", "es-ES"),
        ("fre", "fr"),
        ("fr-CA", "fr-CA"),
        ("fr-FR", "fr-FR"),
        ("chi", "zh"),
        ("zh-CN", "zh-Hans"),
        ("zh-TW", "zh-Hant"),
        ("cmn-Hant-CN", "zh-Hant"),
        ("yue", "yue"),
        ("ger", "de"),
        ("und", "und"),
        (None, "und"),
    ],
)
def test_normalize(tag, expected):
    assert lang.normalize(tag) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("English", "en"),
        ("English (US)", "en"),
        ("Spanish (Latin America)", "es-419"),
        ("Spanish (ES)", "es-ES"),
        ("French (CA)", "fr-CA"),
        ("French (FR)", "fr-FR"),
        ("Chinese (Traditional)", "zh-Hant"),
        ("Chinese (Simplified)", "zh-Hans"),
        ("Mandarin-Hant-CN", "zh-Hant"),
        ("Japanese (JP)", "ja"),
    ],
)
def test_mediainfo_language_names(name, expected):
    assert lang.from_mediainfo_name(name) == expected


@pytest.mark.parametrize(
    ("base", "title", "expected"),
    [
        ("es", "Spanish (Latin American)", "es-419"),
        ("es", "Latin American", "es-419"),
        ("es", "Spanish (Castilian)", "es-ES"),
        ("fr", "Parisian", "fr-FR"),
        ("fr", "Canadian", "fr-CA"),
        ("zh", "Simplified", "zh-Hans"),
        ("zh", "Chinese (Mandarin Traditional)", "zh-Hant"),
        ("zh", "Chinese (Cantonese)", "yue"),
        ("es", "Spanish", None),
        ("de", "German (Latin)", None),
    ],
)
def test_variant_from_title(base, title, expected):
    assert lang.variant_from_title(base, title) == expected


@pytest.mark.parametrize(
    ("layout", "channels", "expected"),
    [
        ("L R C LFE Ls Rs", 6, Layout(5, 1)),
        ("L R C Ls Rs", 5, Layout(5, 0)),
        ("L R Ls Rs LFE", 5, Layout(4, 1)),
        ("L R C LFE Ls Rs Lb Rb / L R C LFE Ls Rs", 8, Layout(7, 1)),
        ("C L R LFE Lb Rb Lss Rss Objects", 8, Layout(7, 1)),
        ("M", 1, Layout(1, 0)),
        (None, 6, Layout(5, 1)),
        (None, 2, Layout(2, 0)),
    ],
)
def test_parse_layout(layout, channels, expected):
    assert parse_layout(layout, channels) == expected


@pytest.mark.parametrize(
    ("fmt", "commercial", "additional", "codec", "atmos", "dtsx"),
    [
        ("MLP FBA", "Dolby TrueHD with Dolby Atmos", "16-ch", AudioCodec.TRUEHD, True, False),
        ("MLP FBA 16-ch", "Dolby TrueHD with Dolby Atmos", None, AudioCodec.TRUEHD, True, False),
        ("MLP FBA", "Dolby TrueHD", None, AudioCodec.TRUEHD, False, False),
        ("E-AC-3 JOC", "Dolby Digital Plus with Dolby Atmos", None, AudioCodec.EAC3, True, False),
        ("E-AC-3", "Dolby Digital Plus", None, AudioCodec.EAC3, False, False),
        ("DTS", "DTS-HD MA + DTS:X", "XLL X", AudioCodec.DTS_HD_MA, False, True),
        ("DTS XLL", "DTS-HD Master Audio", None, AudioCodec.DTS_HD_MA, False, False),
        ("DTS", "DTS", None, AudioCodec.DTS, False, False),
        ("AAC LC", None, None, AudioCodec.AAC, False, False),
        ("PCM", None, None, AudioCodec.LPCM, False, False),
    ],
)
def test_audio_format(fmt, commercial, additional, codec, atmos, dtsx):
    f = parse_audio_format(fmt, commercial, additional)
    assert (f.codec, f.atmos, f.dtsx) == (codec, atmos, dtsx)


SAMPLE = """General
Complete name                            : Movie.2020.2160p.UHD.BluRay.DD+.5.1.Atmos.x265-GROUP.mkv

Video
ID                                       : 1
Format                                   : HEVC
Width                                    : 3 840 pixels
Height                                   : 2 160 pixels

Audio
ID                                       : 2
Format                                   : E-AC-3 JOC
Commercial name                          : Dolby Digital Plus with Dolby Atmos
Bit rate                                 : 1 024 kb/s
Channel(s)                               : 6 channels
Channel layout                           : L R C LFE Ls Rs
Delay relative to video                  : -838 ms
Title                                    : E-AC-3 Atmos 5.1
Language                                 : English
Default                                  : Yes
Forced                                   : No

Text #1
ID                                       : 3
Format                                   : UTF-8
Codec ID                                 : S_TEXT/UTF8
Count of elements                        : 1 234
Title                                    : English (SRT)
Language                                 : English
Default                                  : No
Forced                                   : No

Text #2
ID                                       : 4
Format                                   : PGS
Title                                    : Latin American
Language                                 : Spanish
Default                                  : No
Forced                                   : No

Menu
00:00:00.000                             : en:Chapter 01
"""


def test_parse_mediainfo_text():
    info = parse_mediainfo_text(SAMPLE)
    assert info.name.endswith("x265-GROUP.mkv")
    assert info.video.width == 3840
    assert info.has_chapters
    (a,) = info.audio
    assert (a.id, a.codec, a.layout, a.atmos, a.bitrate_kbps, a.delay_ms) == (1, AudioCodec.EAC3, Layout(5, 1), True, 1024, -838)
    s1, s2 = info.subs
    assert (s1.format, s1.language, s1.element_count) == (SubFormat.SRT, "en", 1234)
    assert (s2.format, s2.language) == (SubFormat.PGS, "es-419")


@pytest.mark.parametrize(
    ("filename", "language", "tags"),
    [
        ("Movie.en.srt", "en", set()),
        ("Movie.eng.forced.srt", "en", {"forced"}),
        ("Movie.en.sdh.srt", "en", {"sdh"}),
        ("Movie.en.dub.srt", "en", {"dub"}),
        ("Movie.es-419.srt", "es-419", set()),
        ("Movie.fr-FR.srt", "fr-FR", set()),
    ],
)
def test_external_sub_names(filename, language, tags):
    t = external_sub_track(Path(filename), "Movie", 0)
    assert t is not None and t.language == language and set(t.tags) == tags
    assert t.forced == ("forced" in tags) and t.hearing_impaired == ("sdh" in tags)


def test_external_sub_bad_name():
    assert external_sub_track(Path("Movie.srt"), "Movie", 0) is None


def match(files, suffixes, has_audio, exts=()):
    rules = MatchRules(encode_suffixes=tuple(suffixes), encode_extensions=tuple(exts))
    return match_files(sort_files(files, rules, has_audio), rules)


def test_pairing_by_stem_and_audio(tmp_path):
    names = ["A.mkv", "A_out.mkv", "B.mkv", "B_out.mkv", "C_out.mkv", "A.en.srt", "A.en.forced.srt"]
    for n in names:
        (tmp_path / n).write_bytes(b"")
    files = sorted(tmp_path.glob("*.mkv"))
    found = match(files, ["_out"], has_audio=lambda p: not p.stem.endswith("_out"))
    by_source = {p.source.name: p for p in found.jobs}
    assert by_source["A.mkv"].encode.name == "A_out.mkv"
    assert by_source["B.mkv"].encode.name == "B_out.mkv"
    assert [p.name for p in by_source["A.mkv"].subtitles] == ["A.en.forced.srt", "A.en.srt"]
    assert [p.name for p in found.unmatched.encodes] == ["C_out.mkv"]


def test_single_pair_matches_regardless_of_name(tmp_path):
    for n in ("Source.Remux.mkv", "Movie.2020.1080p.BluRay.x264-GROUP.mkv"):
        (tmp_path / n).write_bytes(b"")
    files = sorted(tmp_path.glob("*.mkv"))
    found = match(files, ["_out"], has_audio=lambda p: "Remux" in p.name)
    assert found.jobs == [JobInputs(tmp_path / "Source.Remux.mkv", tmp_path / "Movie.2020.1080p.BluRay.x264-GROUP.mkv")]
