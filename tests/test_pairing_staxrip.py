"""Pairing against the real StaxRip layout (raw _job.h264 encodes, subs/ folder, temp dir)."""

from __future__ import annotations

from pathlib import Path

from conftest import source, sub

from videoforge.core.jobs import external_tracks
from videoforge.core.models import EncodeState, SubFormat as F
from videoforge.core.pairing import (
    FileSets,
    MatchRules,
    discover,
    external_sub_track,
    match_files,
    match_reason,
    rank_sources,
    slot_files,
    subtitle_label,
)

EXTS = (".h264", ".hevc")
RULES = MatchRules(encode_suffixes=("_job",), encode_extensions=EXTS)
NF = "Show.S01E01.Some.Title.Part.1.NF.WEB-DL-GNOME_USA_23.976fps.en.synced.srt"
EXTRACT = "Show.S01E01.Long.Remux.Name.1080p.FLAC.2.0.AVC.REMUX-RLSGRP_track7_[eng].srt"


def make_batch(tmp_path: Path) -> tuple[Path, Path]:
    src_dir = tmp_path / "downloads" / "Show.S01"
    work = tmp_path / "working"
    (src_dir / "subs").mkdir(parents=True)
    work.mkdir()
    for ep in ("01", "02", "03"):
        (src_dir / f"Show.S01E{ep}.mkv").write_bytes(b"")
    (work / "Show.S01E01_job.h264").write_bytes(b"")
    (work / "Show.S01E02_job.h264").write_bytes(b"")

    temp1 = src_dir / "Show.S01E01.mkv_temp"
    (temp1 / "a_qpf").mkdir(parents=True)
    (temp1 / "Show.S01E01_job_staxrip.log").write_text("...\n---- Job Complete ----\n", encoding="utf-8")
    (temp1 / "a_qpf" / "qpf_chapters.txt").write_text("CHAPTER01=00:00:00.000\nCHAPTER01NAME=Chapter 01\n")
    temp2 = src_dir / "Show.S01E02.mkv_temp"
    temp2.mkdir()
    (temp2 / "Show.S01E02_job_staxrip.log").write_text("encoding...\n", encoding="utf-8")

    (src_dir / "subs" / NF).write_text("1\n00:00:01,000 --> 00:00:02,000\nHi\n" * 300, encoding="utf-8")
    (src_dir / "subs" / EXTRACT).write_text("1\n00:00:01,000 --> 00:00:02,000\nLa\n" * 30, encoding="utf-8")
    (src_dir / "subs" / "Show.S01E02.Other.en.synced.srt").write_text("")
    return src_dir, work


def test_staxrip_batch_pairs(tmp_path):
    src_dir, work = make_batch(tmp_path)
    files = sorted(src_dir.glob("*.mkv")) + sorted(work.glob("*.h264"))
    found = discover(files, RULES, has_audio=lambda p: p.suffix == ".mkv")
    by = {p.source.name: p for p in found.jobs}
    assert found.unmatched == FileSets()

    e1 = by["Show.S01E01.mkv"]
    assert e1.encode.name == "Show.S01E01_job.h264"
    assert e1.encode_state is EncodeState.DONE
    assert e1.chapters.name == "qpf_chapters.txt"
    assert sorted(p.name for p in e1.subtitles) == sorted([NF, EXTRACT])

    e2 = by["Show.S01E02.mkv"]
    assert e2.encode_state is EncodeState.IN_PROGRESS
    assert e2.chapters is None
    assert [p.name for p in e2.subtitles] == ["Show.S01E02.Other.en.synced.srt"]

    assert by["Show.S01E03.mkv"].encode is None


def test_episode_token_matches_differently_named_encode(tmp_path):
    a = tmp_path / "Show.S02E05.Remux.mkv"
    b = tmp_path / "Show.2013.S02E05.1080p.BluRay.x264-GROUP.h264"
    c = tmp_path / "Show.S02E06.Remux.mkv"
    for p in (a, b, c):
        p.write_bytes(b"")
    found = match_files(FileSets(sources=[a, c], encodes=[b]), RULES)
    by = {p.source.name: p for p in found.jobs}
    assert by[a.name].encode == b
    assert by[c.name].encode is None


def test_external_names_from_real_workflow(tmp_path):
    nf = external_sub_track(tmp_path / NF, "Show.S01E01", 0)
    assert nf is not None and nf.language == "en" and nf.tags == frozenset()
    ex = external_sub_track(tmp_path / EXTRACT, "Show.S01E01", 1)
    assert ex is not None and ex.language == "en" and ex.extracted_from == 7


def test_extracted_srt_inherits_source_track_traits(tmp_path):
    path = tmp_path / EXTRACT
    path.write_text("1\n00:00:01,000 --> 00:00:02,000\nLa\n" * 30, encoding="utf-8")
    foreign = sub(F.ASS, "en", "English (ASS Foreign)", index=2, forced=True)
    foreign.number = 7
    info = source(subs=[sub(F.PGS, "en", "English", index=0), foreign])
    (track,), issues = external_tracks(info, [path])
    assert not issues
    assert track.forced and track.title == "English (ASS Foreign)" and track.element_count == 30
    assert track.title_from == foreign.id  # marked inferred: the editor says where the title came from


def test_unmatched_external_title_is_not_inferred(tmp_path):
    path = tmp_path / EXTRACT
    path.write_text("", encoding="utf-8")
    (track,), _ = external_tracks(source(subs=[sub(F.PGS, "en", "English", index=0)]), [path])
    assert track.title == "" and track.title_from is None


def test_subtitle_and_chapter_folders_match_by_episode(tmp_path):
    """Slots filled from separate folders: subs and chapters go to their episode."""
    src_dir, work = make_batch(tmp_path)
    extra = tmp_path / "more_subs"
    extra.mkdir()
    (extra / "Show.S01E03.Whatever.en.srt").write_text("", encoding="utf-8")
    (extra / "Show.S01E09.en.srt").write_text("", encoding="utf-8")
    (extra / "Show.S01E03.chapters.txt").write_text("CHAPTER01=00:00:00.000\n", encoding="utf-8")
    found = discover([src_dir, work, extra], RULES, has_audio=lambda p: p.suffix == ".mkv")
    e3 = next(j for j in found.jobs if j.source.name == "Show.S01E03.mkv")
    assert [p.name for p in e3.subtitles] == ["Show.S01E03.Whatever.en.srt"]
    assert e3.chapters.name == "Show.S01E03.chapters.txt"
    assert [p.name for p in found.unmatched.subtitles] == ["Show.S01E09.en.srt"]


def test_every_subtitle_format_pairs_and_vobsub_by_its_idx(tmp_path):
    src = tmp_path / "Show.S01E01.mkv"
    names = ["Show.S01E01.en.srt", "Show.S01E01.en.ass", "Show.S01E01.fr.ssa", "Show.S01E01.de.sup"]
    for p in (src, *(tmp_path / n for n in names), tmp_path / "S01E01.es.idx", tmp_path / "S01E01.es.sub"):
        p.write_bytes(b"")
    (job,) = discover([src], RULES, has_audio=lambda p: p.suffix == ".mkv").jobs
    assert sorted(p.name for p in job.subtitles) == sorted([*names, "S01E01.es.idx"])
    assert [p.name for p in slot_files([], [], [tmp_path], [], RULES).subtitles] == sorted([*names, "S01E01.es.idx"])


def test_lone_source_takes_every_added_subtitle(tmp_path):
    src, enc = tmp_path / "Movie.Remux.mkv", tmp_path / "out.hevc"
    subs = [tmp_path / "Some.Other.Name.en.srt", tmp_path / "forced.en.forced.srt"]
    for p in (src, enc, *subs):
        p.write_bytes(b"")
    rules = MatchRules(encode_extensions=EXTS, scan_source_folder=False)
    (job,) = match_files(FileSets([src], [enc], subs), rules).jobs
    assert job.encode == enc and sorted(job.subtitles) == sorted(subs)


def test_added_subtitles_replace_the_ones_near_the_source(tmp_path):
    """A subs folder added for some episodes: those take only it; the others still scan the source folder."""
    (tmp_path / "extracted").mkdir()
    synced = tmp_path / "subs-synced"
    synced.mkdir()
    e1, e2 = tmp_path / "Show.S01E01.mkv", tmp_path / "Show.S01E02.mkv"
    near = [tmp_path / "extracted" / f"Show.S01E0{n}.Title.REMUX_track7_[eng].srt" for n in (1, 2)]
    mine = synced / "Show.S01E01.Part.1.WEB-DL.en.synced.srt"
    for p in (e1, e2, *near, mine):
        p.write_bytes(b"")
    first, second = match_files(FileSets([e1, e2], [], [mine]), RULES).jobs
    assert first.subtitles == [mine]
    assert second.subtitles == [near[1]]


def test_sources_match_in_episode_order(tmp_path):
    names = ["Show.E10.mkv", "Show.E2.mkv", "Show.E1.mkv"]
    for n in names:
        (tmp_path / n).write_bytes(b"")
    found = match_files(FileSets([tmp_path / n for n in names]), MatchRules(scan_source_folder=False))
    assert [j.source.name for j in found.jobs] == ["Show.E1.mkv", "Show.E2.mkv", "Show.E10.mkv"]


def test_subtitle_label_reads_the_name():
    synced = subtitle_label(Path("Show.S01E01.Part.1.NF.WEB-DL-GNOME_USA_23.976fps.en.synced.srt"))
    assert synced["language"] == "en" and synced["format"] == "srt" and synced["tags"] == ["synced"]
    assert synced["track"] is None and synced["language_name"] == "English"
    extracted = subtitle_label(Path("Show.S01E01.1080p.REMUX-FraMeSToR_track7_[eng].forced.ass"))
    assert extracted["format"] == "ass" and extracted["track"] == 7 and extracted["tags"] == ["forced"]
    assert subtitle_label(Path("Show.S01E01.srt"))["language"] == "und"
    assert subtitle_label(Path("Show.S01E01.srt"))["match"] is None  # no source given


def test_match_reason_says_how_sure_the_match_is():
    source = Path("Show.S01E01.1080p.REMUX.mkv")
    assert match_reason(Path("Show.S01E01.1080p.REMUX.en.srt"), source) == "name"
    assert match_reason(Path("Show.S01E01.NF.WEB-DL.en.synced.srt"), source) == "episode"
    assert match_reason(Path("English.srt"), source) == "only_source"
    assert match_reason(Path("Show.S01E02.en.srt"), source) == "other_episode"
    assert match_reason(Path("Movie.en.srt"), Path("Movie.2001.mkv")) == "only_source"
    assert match_reason(Path("Show.S01E02.en.srt"), Path("Movie.2001.mkv")) == "only_source"  # nothing to compare
    assert subtitle_label(Path("Show.S01E02.en.srt"), source)["match"] == "other_episode"


def test_without_staxrip_temp(tmp_path):
    """No log and no qpf lookup: chapters only from added files, state from the file lock."""
    src_dir, work = make_batch(tmp_path)
    rules = MatchRules(encode_suffixes=("_job",), encode_extensions=EXTS, staxrip_temp=False)
    found = discover([src_dir, work], rules, has_audio=lambda p: p.suffix == ".mkv")
    e1, e2 = found.jobs[0], found.jobs[1]
    assert e1.chapters is None
    assert e1.encode_state is EncodeState.UNKNOWN and e2.encode_state is EncodeState.UNKNOWN


def test_slot_files_from_setup_panel(tmp_path):
    """The GUI's job setup: one folder per slot, matched as a batch."""
    src_dir, work = make_batch(tmp_path)
    chapters = tmp_path / "chapters"
    chapters.mkdir()
    (chapters / "S01E02.txt").write_text("", encoding="utf-8")
    sets = slot_files([src_dir], [work], [src_dir / "subs"], [chapters], RULES)
    assert [p.name for p in sets.sources] == ["Show.S01E01.mkv", "Show.S01E02.mkv", "Show.S01E03.mkv"]
    assert [p.name for p in sets.encodes] == ["Show.S01E01_job.h264", "Show.S01E02_job.h264"]
    assert len(sets.subtitles) == 3 and [p.name for p in sets.chapters] == ["S01E02.txt"]
    found = match_files(sets, RULES)
    e2 = found.jobs[1]
    assert e2.encode.name == "Show.S01E02_job.h264" and e2.chapters.name == "S01E02.txt"


def test_raw_encode_in_source_folder_needs_no_encode_slot(tmp_path):
    (tmp_path / "Movie.mkv").write_bytes(b"")
    (tmp_path / "Movie_job.hevc").write_bytes(b"")
    sets = slot_files([tmp_path], [], [], [], RULES)
    (job,) = match_files(sets, RULES).jobs
    assert job.encode == tmp_path / "Movie_job.hevc"


def test_matching_never_resolves_a_path(tmp_path, monkeypatch):
    """On a network share each resolve() is a round trip; matching a season compares paths as text."""
    src_dir, work = make_batch(tmp_path)

    def no_resolve(self, strict=False):
        raise AssertionError(f"resolved {self}")

    monkeypatch.setattr(Path, "resolve", no_resolve)
    sets = slot_files([src_dir, src_dir / "Show.S01E01.mkv"], [work], [src_dir / "subs"], [], RULES)
    assert [p.name for p in sets.sources] == ["Show.S01E01.mkv", "Show.S01E02.mkv", "Show.S01E03.mkv"]  # no twin
    assert len(match_files(sets, RULES).jobs) == 3


def test_extracted_subtitle_named_after_its_source_with_an_underscore(tmp_path):
    # gMKVExtract: "<source>_track7_[eng].forced.srt"; "_" right after SxxEyy used to hide the episode.
    sources = [tmp_path / f"Show.S01E0{n}.mkv" for n in (1, 2)]
    subs = [tmp_path / "forced" / f"Show.S01E0{n}_track7_[eng].forced.srt" for n in (2, 1)]
    found = match_files(FileSets(sources, [], subs), MatchRules(scan_source_folder=False))
    assert [[p.name for p in j.subtitles] for j in found.jobs] == [
        ["Show.S01E01_track7_[eng].forced.srt"],
        ["Show.S01E02_track7_[eng].forced.srt"],
    ]
    assert found.unmatched.subtitles == []
    assert match_reason(subs[1], sources[0]) == "name"
    assert match_reason(Path("Other_S01E01_x.srt"), sources[0]) == "episode"


def test_subtitle_goes_to_the_source_its_name_is_closest_to(tmp_path):
    a, b = tmp_path / "Movie.One.2001.1080p.BluRay.mkv", tmp_path / "Other.Film.1999.1080p.BluRay.mkv"
    close, unclear = tmp_path / "movie one 2001 en.srt", tmp_path / "1080p.en.srt"
    found = match_files(FileSets([a, b], [], [close, unclear]), MatchRules(scan_source_folder=False))
    first = next(j for j in found.jobs if j.source == a)
    assert first.subtitles == [close]
    assert found.how == {close: "similar"}
    assert found.unmatched.subtitles == [unclear]  # only words every source has: no guess
    assert subtitle_label(close, a, found.how.get(close))["match"] == "similar"


def test_files_matched_by_hand_win_over_names(tmp_path):
    a, b = tmp_path / "Show.S01E01.mkv", tmp_path / "Show.S01E02.mkv"
    stray, named = tmp_path / "English.srt", tmp_path / "Show.S01E01.en.srt"
    chapters, encode = tmp_path / "chapters.txt", tmp_path / "Show.S01E01_job.h264"
    assign = {stray: b, named: b, chapters: a, encode: b, tmp_path / "x.srt": tmp_path / "Not.In.Batch.mkv"}
    found = match_files(FileSets([a, b], [encode], [stray, named], [chapters]), RULES, assign)
    first, second = found.jobs
    assert (first.encode, first.subtitles, first.chapters) == (None, [], chapters)
    assert (second.encode, second.subtitles) == (encode, [stray, named])
    assert found.how == dict.fromkeys([encode, stray, named, chapters], "manual")
    assert found.unmatched == FileSets()


def test_rank_sources_skips_another_episode():
    sources = [Path("Show.S01E01.mkv"), Path("Show.S01E02.mkv"), Path("Show.S01E03.mkv")]
    assert rank_sources(Path("Show.S01E02.en.srt"), sources) == [(sources[1], 1.0)]
    assert rank_sources(Path("English.srt"), sources) == []


def test_episode_number_alone_points_to_its_source(tmp_path):
    sources = [tmp_path / f"Show.S01E{n:02d}.1080p.mkv" for n in (1, 2, 12)]
    anime, word = tmp_path / "[Group] Show - 12 [ABCD1234].ass", tmp_path / "Show Episode 2.srt"
    found = match_files(FileSets(sources, [], [anime, word]), MatchRules(scan_source_folder=False))
    assert found.jobs[1].subtitles == [word] and found.jobs[2].subtitles == [anime]
    assert found.how == {anime: "episode", word: "episode"}
    assert rank_sources(Path("Show - 2.ass"), sources)[0][0] == sources[1]


def test_episode_number_alone_is_not_enough_across_seasons(tmp_path):
    sources = [tmp_path / "Show.S01E01.mkv", tmp_path / "Show.S02E01.mkv"]
    found = match_files(FileSets(sources, [], [tmp_path / "Show - 01.ass"]), MatchRules(scan_source_folder=False))
    assert [p.name for p in found.unmatched.subtitles] == ["Show - 01.ass"]


def test_a_numbered_set_lines_up_with_the_sources(tmp_path):
    # Nothing in these names says "episode": the number that changes from file to file lines up with the
    # sources' episodes. The track number changes too, but only between two values.
    sources = [tmp_path / f"Show.S01E{n:02d}.mkv" for n in (1, 2, 3)]
    subs = [tmp_path / f"disc1_title{n:02d}_track{t}.srt" for n, t in ((1, 3), (2, 4), (3, 3))]
    found = match_files(FileSets(sources, [], subs), MatchRules(scan_source_folder=False))
    assert [j.subtitles for j in found.jobs] == [[s] for s in subs]
    assert set(found.how.values()) == {"number"}


def test_one_file_matched_by_hand_suggests_the_rest_of_its_set(tmp_path):
    # Two numbers change in step (1-3 and 2-4), both could be episodes: the user matches one file, and the
    # rest of its set is offered the same way (the second number is the episode).
    sources = [tmp_path / f"Show.S01E{n:02d}.mkv" for n in (1, 2, 3, 4)]
    subs = [tmp_path / f"t{n}_c{n + 1}.srt" for n in (1, 2, 3)]
    rules = MatchRules(scan_source_folder=False)
    found = match_files(FileSets(sources, [], subs), rules)
    assert found.unmatched.subtitles == subs
    found = match_files(FileSets(sources, [], subs), rules, {subs[0]: sources[1]})
    assert found.jobs[1].subtitles == [subs[0]]
    assert {p: offer[0] for p, offer in found.suggestions.items()} == {
        subs[1]: (sources[2], "pattern"),
        subs[2]: (sources[3], "pattern"),
    }


def test_a_file_set_to_no_source_stays_unmatched_and_a_found_one_can_move(tmp_path):
    a, b = tmp_path / "Show.S01E01.mkv", tmp_path / "Show.S01E02.mkv"
    for f in (a, b, tmp_path / "Show.S01E01.en.srt", tmp_path / "Show.S01E02.en.srt"):
        f.write_bytes(b"x")
    found_a, found_b = tmp_path / "Show.S01E01.en.srt", tmp_path / "Show.S01E02.en.srt"
    chapters = tmp_path / "Show.S01E01.chapters.txt"
    found = match_files(FileSets([a, b], [], [], [chapters]), MatchRules(), {found_a: b, chapters: None})
    first, second = found.jobs
    assert first.subtitles == [] and first.chapters is None
    assert second.subtitles == [found_a, found_b]  # moved here, beside its own
    assert found.how == {found_a: "manual", chapters: "manual"}
    assert found.unmatched.chapters == [chapters]


def test_names_read_episodes_however_they_are_spelled():
    from videoforge.core.match_names import episode_of, episode_token, numbering

    assert [episode_token(n) for n in ("Show.S1E2", "Show.S01.E02", "Show 1x02", "Show_S01E02_x")] == ["S01E02"] * 4
    assert episode_token("Movie.1920x1080") is None and episode_token("DD5.1x264") is None
    assert episode_of("Show - 07v2 [1080p]") == (None, 7) and episode_of("Show.Ep.07") == (None, 7)
    assert episode_of("Show.E-AC3.mkv") is None
    assert numbering(["[G] Show - 01 [AB12]", "[G] Show - 02 [AB12]"]) == [1, 2]
    assert numbering(["Movie.One.2001", "Other.1999"]) is None
