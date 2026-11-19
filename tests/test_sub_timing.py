from videoforge.core import sub_timing
from videoforge.core.sub_timing import last_cue_ms, verdict

MIN = 60_000


def test_last_cue_of_srt_ass_and_utf16(tmp_path):
    srt = tmp_path / "a.srt"
    srt.write_text(
        "1\n00:00:01,000 --> 00:00:02,500\nHi\n\n2\n00:23:10,120 --> 00:23:12.4\nBye\n\n"
        "3\n00:05:00,000 --> 00:05:01,000\nOut of order\n",
        encoding="utf-8-sig",
    )
    assert last_cue_ms(srt) == 23 * MIN + 12_400
    ass = tmp_path / "a.ass"
    ass.write_text(
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Hi\n"
        "Comment: 0,0:59:00.00,0:59:01.00,Default,,0,0,0,,not shown\n"
        "Dialogue: 0,0:21:03.50,0:21:04.25,Default,,0,0,0,,Bye\n",
        encoding="utf-8",
    )
    assert last_cue_ms(ass) == 21 * MIN + 4_250
    wide = tmp_path / "w.srt"
    wide.write_bytes("1\n00:00:01,000 --> 00:10:00,000\nx\n".encode("utf-16"))
    assert last_cue_ms(wide) == 10 * MIN


def test_no_cue_for_image_empty_or_missing_files(tmp_path):
    (tmp_path / "a.sup").write_bytes(b"PG")
    (tmp_path / "e.srt").write_text("", encoding="utf-8")
    assert last_cue_ms(tmp_path / "a.sup") is None
    assert last_cue_ms(tmp_path / "e.srt") is None
    assert last_cue_ms(tmp_path / "gone.srt") is None


def test_verdict_flags_only_big_gaps():
    episode = 24 * MIN
    assert verdict(episode - 90_000, episode) is None  # credits
    assert verdict(episode + 59_000, episode) is None
    assert verdict(episode + 61_000, episode) == "late"
    assert verdict(episode - 5 * MIN - 1, episode) == "early"  # 5 min beats 15% (3.6 min) here
    assert verdict(episode - 4 * MIN, episode) is None
    film = 120 * MIN
    assert verdict(film - 17 * MIN, film) is None  # 15% (18 min) beats 5 min here
    assert verdict(film - 19 * MIN, film) == "early"
    assert verdict(3 * MIN, episode, forced=True) is None  # a forced sub's few cues can end anywhere
    assert verdict(episode + 2 * MIN, episode, forced=True) == "late"


def test_source_length_falls_back_when_mkvmerge_is_missing(tmp_path):
    src = tmp_path / "x.mkv"
    src.write_bytes(b"not a video")
    assert sub_timing.source_length_ms(src, str(tmp_path / "no-mkvmerge.exe")) is None
    assert sub_timing.source_length_ms(tmp_path / "gone.mkv", "mkvmerge") is None
