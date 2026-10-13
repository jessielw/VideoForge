"""Pairing against the real StaxRip layout (raw _job.h264 encodes, subs/ folder, temp dir)."""

from __future__ import annotations

from pathlib import Path

from conftest import source, sub

from videoforge.core.jobs import external_tracks
from videoforge.core.models import EncodeState
from videoforge.core.models import SubFormat as F
from videoforge.core.pairing import FileSets, MatchRules, discover, external_sub_track, match_files, slot_files

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


def test_lone_source_takes_every_added_subtitle(tmp_path):
    src, enc = tmp_path / "Movie.Remux.mkv", tmp_path / "out.hevc"
    subs = [tmp_path / "Some.Other.Name.en.srt", tmp_path / "forced.en.forced.srt"]
    for p in (src, enc, *subs):
        p.write_bytes(b"")
    rules = MatchRules(encode_extensions=EXTS, scan_source_folder=False)
    (job,) = match_files(FileSets([src], [enc], subs), rules).jobs
    assert job.encode == enc and sorted(job.subtitles) == sorted(subs)


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
