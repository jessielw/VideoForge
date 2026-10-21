"""Sources other than MKV (MP4, M2TS / TS): pairing them, probing them, copying their tracks into an MP4."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from conftest import audio, plan_for, source

from videoforge.core import probe as probe_mod
from videoforge.core.execute.mux import mp4box_command, mux_command, mux_issues
from videoforge.core.models import AudioCodec as C, Overrides, Severity, VideoInfo
from videoforge.core.pairing import MatchRules, discover, slot_files, sort_files

RULES = MatchRules(encode_suffixes=("_job",), encode_extensions=(".h264", ".hevc"))


def test_mp4_and_m2ts_files_are_sources(tmp_path):
    for name in ("Movie.mp4", "00005.m2ts", "Clip.ts", "Show.S01E01.mkv", "Show.S01E01_job.h264", "notes.nfo"):
        (tmp_path / name).write_bytes(b"")
    sets = slot_files([tmp_path], [], [], [], RULES)
    assert [p.name for p in sets.sources] == ["00005.m2ts", "Clip.ts", "Movie.mp4", "Show.S01E01.mkv"]
    assert [p.name for p in sets.encodes] == ["Show.S01E01_job.h264"]
    found = discover([tmp_path], RULES, lambda _p: True)
    assert sorted(j.source.name for j in found.jobs) == ["00005.m2ts", "Clip.ts", "Movie.mp4", "Show.S01E01.mkv"]
    # A dropped MP4 without audio is an encode, as an MKV is.
    sets = sort_files([tmp_path / "Movie.mp4", tmp_path / "00005.m2ts"], RULES, lambda p: p.suffix == ".m2ts")
    assert [p.name for p in sets.sources] == ["00005.m2ts"] and [p.name for p in sets.encodes] == ["Movie.mp4"]


class _Track:
    """A pymediainfo track: a field it doesn't have reads None."""

    def __init__(self, **fields: Any):
        self.__dict__.update(fields)

    def __getattr__(self, _name: str) -> None:
        return None


def test_an_m2ts_probe_times_its_video_and_splits_the_truehd_core(monkeypatch, tmp_path):
    """mkvmerge has no frame duration for a TS (or an MP4): MediaInfo's 23.976 is taken as 24000/1001. A Blu-ray
    TrueHD PID's AC-3 core is a track of its own in mkvmerge, under the PID; MediaInfo's one track is the TrueHD's."""
    ident = {
        "container": {"recognized": True},
        "tracks": [
            {
                "id": 0,
                "type": "video",
                "codec": "VC-1",
                "properties": {"number": 4113, "pixel_dimensions": "1920x1080"},
            },
            {
                "id": 1,
                "type": "audio",
                "codec": "TrueHD",
                "properties": {"number": 4352, "language": "eng", "multiplexed_tracks": [1, 2], "audio_channels": 6},
            },
            {
                "id": 2,
                "type": "audio",
                "codec": "AC-3",
                "properties": {
                    "number": 4352,
                    "language": "eng",
                    "multiplexed_tracks": [1, 2],
                    "audio_channels": 6,
                    "audio_sampling_frequency": 48000,
                },
            },
            {"id": 3, "type": "audio", "codec": "AC-3", "properties": {"number": 4353, "language": "eng"}},
        ],
    }
    tracks = [
        _Track(
            track_type="Video",
            track_id=4113,
            format="VC-1",
            frame_rate="23.976",
            frame_count="31612",
            scan_type="Interlaced",
            scan_order="TFF",
        ),
        _Track(
            track_type="Audio",
            track_id=4352,
            format="MLP FBA",
            commercial_name="Dolby TrueHD",
            channel_s=6,
            stream_size=73835104,
            delay_relative_to_video=-12,
        ),
        _Track(track_type="Audio", track_id=4353, format="AC-3", channel_s=2, delay_relative_to_video=0),
    ]
    monkeypatch.setattr(probe_mod, "mkvmerge_identify", lambda *_: ident)
    monkeypatch.setattr(probe_mod.MediaInfo, "parse", lambda *_: _Track(tracks=tracks))
    info = probe_mod.probe(tmp_path / "00005.m2ts", "mkvmerge")
    assert info.video is not None and info.video.default_duration_ns == 41708333 and info.video.frames == 31612
    assert (info.video.scan_type, info.video.scan_order, info.video.interlaced) == ("Interlaced", "TFF", True)
    truehd, core, ac3 = info.audio
    assert (truehd.codec, truehd.number, truehd.core, truehd.size_bytes) == (C.TRUEHD, 4352, False, 73835104)
    assert (core.codec, core.number, core.core, core.size_bytes) == (C.AC3, 4352, True, None)
    assert (core.layout.channels, core.sample_rate, core.delay_ms) == (6, 48000, -12)  # the PID's delay
    assert (ac3.codec, ac3.number, ac3.core) == (C.AC3, 4353, False)


def test_ffprobe_times_a_ts_and_pairs_the_core_by_order(monkeypatch, tmp_path):
    """ffprobe's start times give the delay (here the TrueHD PID 12 ms ahead of the video) and its average rate the
    frame duration, over MediaInfo's; its streams pair by id, and two under one PID (a TrueHD, its core) by order."""
    ident = {
        "container": {"recognized": True, "type": "MPEG transport stream"},
        "tracks": [
            {"id": 0, "type": "video", "codec": "AVC", "properties": {"number": 4113, "pixel_dimensions": "1920x1080"}},
            {"id": 1, "type": "audio", "codec": "TrueHD", "properties": {"number": 4352, "multiplexed_tracks": [1, 2]}},
            {"id": 2, "type": "audio", "codec": "AC-3", "properties": {"number": 4352, "multiplexed_tracks": [1, 2]}},
            {"id": 3, "type": "audio", "codec": "AC-3", "properties": {"number": 4353}},
        ],
    }
    streams = [
        {"id": "0x1011", "codec_type": "video", "start_time": "11.650667", "avg_frame_rate": "24000/1001"},
        {"id": "0x1100", "codec_type": "audio", "start_time": "11.638667", "avg_frame_rate": "0/0"},
        {"id": "0x1100", "codec_type": "audio", "start_time": "11.640667", "avg_frame_rate": "0/0"},
        {"id": "0x1101", "codec_type": "audio", "start_time": "12.150667", "avg_frame_rate": "0/0"},
    ]
    tracks = [_Track(track_type="Video", track_id=4113, frame_rate_mode="VFR")]  # an x264 TS: no rate
    monkeypatch.setattr(probe_mod, "mkvmerge_identify", lambda *_: ident)
    monkeypatch.setattr(probe_mod.MediaInfo, "parse", lambda *_: _Track(tracks=tracks))
    calls = []
    monkeypatch.setattr(probe_mod, "ffprobe_streams", lambda path, ffprobe: calls.append(path) or streams)
    info = probe_mod.probe(tmp_path / "Clip.ts", "mkvmerge", "ffprobe")
    assert info.video is not None and info.video.default_duration_ns == 41708333
    assert info.video.start_ms == 12 and info.container == "MPEG transport stream"  # the TrueHD's 12 ms first
    assert [a.delay_ms for a in info.audio] == [-12, -10, 500]
    # Without ffprobe (or for an MKV, which mkvmerge and MediaInfo time), MediaInfo's.
    info = probe_mod.probe(tmp_path / "Clip.ts", "mkvmerge")
    assert (
        info.video is not None
        and info.video.default_duration_ns is None
        and [a.delay_ms for a in info.audio] == [0] * 3
    )
    probe_mod.probe(tmp_path / "Clip.mkv", "mkvmerge", "ffprobe")
    assert calls == [tmp_path / "Clip.ts"]


def test_an_mp4_audio_delay_comes_from_its_edit_lists():
    """Without ffprobe, MediaInfo's: no Video_Delay in an MP4, an empty edit (+500) delays the audio; the video's skipped start (-80, its B-frame
    reorder) doesn't move it, nor does an AAC's priming (-21)."""
    video = _Track(source_delay="-80")
    assert probe_mod._delay(_Track(source_delay="500"), video) == 500
    assert probe_mod._delay(_Track(source_delay="-21"), video) == 0
    assert probe_mod._delay(_Track(source_delay="0"), _Track(source_delay="200")) == -200
    assert probe_mod._delay(_Track(delay_relative_to_video=-12, source_delay="500"), video) == -12
    assert probe_mod._delay(_Track(), video) == 0


def test_mp4box_picks_an_m2ts_track_by_its_pid(tmp_path):
    """MP4Box numbers a TS's tracks by PID and an MP4's by track ID (the number mkvmerge read); an MKV's by id + 1.
    A TrueHD's AC-3 core can't be copied apart from it into an MP4."""
    src = source([audio(C.AC3, "2.0", "en", index=0, default=True)], name="00005.m2ts")
    src.path = tmp_path / "00005.m2ts"
    src.video = VideoInfo(1920, 1080, default_duration_ns=41708333)
    src.audio[0].number = 4353
    plan = plan_for(src, source(name="enc.h264"))
    plan.encode_path = Path("enc.h264")
    argv = mp4box_command(plan, {}, Path("out.mp4.partial"), "MP4Box", (".h264",))
    assert argv[argv.index("-add", 3) + 1].startswith(f"{src.path}#trackID=4353:")
    src.path = tmp_path / "Movie.mkv"
    argv = mp4box_command(plan, {}, Path("out.mp4.partial"), "MP4Box", (".h264",))
    assert argv[argv.index("-add", 3) + 1].startswith(f"{src.path}#trackID=2:")  # id 1 + 1

    assert not [i for i in mux_issues(plan, "mp4") if i.code == "mux.mp4_core"]
    plan.audio[0].source.core = True
    assert [(i.severity, i.code) for i in mux_issues(plan, "mp4") if i.code == "mux.mp4_core"] == [
        (Severity.BLOCK, "mux.mp4_core")
    ]
    assert not [i for i in mux_issues(plan, "mkv") if i.code == "mux.mp4_core"]


def test_mkvmerge_lines_up_an_mp4s_copied_tracks_by_their_delay(tmp_path):
    """From an MP4, mkvmerge starts the earliest track it takes at 0: they go back by its delay to the video (here
    0.5 and 0.8 s late). A TS keeps its offset to the earliest stream: its tracks shift by the video's from there."""
    src = source([audio(C.AC3, "2.0", "en", index=0), audio(C.AC3, "2.0", "ja", index=1)], name="Movie.mp4")
    src.path, src.container = tmp_path / "Movie.mp4", "MP4/QuickTime"
    src.video = VideoInfo(1920, 1080, default_duration_ns=41708333)
    src.audio[0].delay_ms, src.audio[1].delay_ms = 500, 800
    plan = plan_for(src, source(name="enc.h264"), Overrides(copies=["id:2+1"]))
    plan.encode_path = Path("enc.h264")

    def syncs(argv: list[str]) -> list[str]:
        return [argv[i + 1] for i, a in enumerate(argv) if a == "--sync"]

    argv = mux_command(plan, {}, Path("out.mkv.partial"), "mkvmerge", (".h264",))
    assert syncs(argv) == ["1:500", "2:500", "2:800"]  # the source's two tracks, then the copy's own input

    src.container, src.video.start_ms = "MPEG transport stream", 12
    argv = mux_command(plan, {}, Path("out.mkv.partial"), "mkvmerge", (".h264",))
    assert syncs(argv) == ["1:-12", "2:-12", "2:-12"]
