"""mkvmerge command built from a plan."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import audio, plan_for, source, sub

from videoforge.core.execute.mux import MuxError, _frame_rate, mux_command
from videoforge.core.models import AudioAction, Layout, Overrides, TrackOverride, VideoInfo
from videoforge.core.models import AudioCodec as C
from videoforge.core.models import SubFormat as F

RAW = (".h264", ".hevc")
OUT = Path("out.mkv")


def aot_plan(*, encode="Show.S01E01_job.h264", start_ms=0, chapters=True):
    src = source(
        [
            audio(C.FLAC, "2.0", "ja", index=0),
            audio(C.TRUEHD, "5.1", "en", index=1),
        ],
        [
            sub(F.PGS, "en", "English", index=0, elements=600),
            sub(F.ASS, "fr", "French", index=1),
            sub(F.SRT, "en", external="subs/Show.S01E01.NF.en.synced.srt"),
            sub(F.SRT, "en", "English (Foreign)", external="subs/Show_track4_[eng].srt", forced=True),
        ],
        name="Show.S01E01.mkv",
    )
    src.video = VideoInfo(1920, 1080, start_ms=start_ms, default_duration_ns=41708333)
    src.audio[0].delay_ms = -7  # AAC: applied at mux
    src.audio[1].delay_ms = 12  # DDP: applied by DeeZy
    src.subs[3].extracted_from = 4
    external = src.subs[2:]
    src.subs[2:] = []  # external files aren't tracks of the source
    plan = plan_for(src, source(name=encode), external_subs=external,
                    chapters=Path("qpf_chapters.txt") if chapters else None)
    plan.encode_path = Path(encode)
    # Encode both audio tracks: Japanese to AAC, English to DDP.
    a0, a1 = plan.audio
    a0.action, a0.out_codec = AudioAction.AAC, C.AAC
    a1.action, a1.out_codec, a1.bitrate_kbps, a1.out_layout = AudioAction.DDP, C.EAC3, 640, Layout(5, 1)
    return plan


def value(argv, flag, prefix=""):
    return [argv[i + 1] for i, a in enumerate(argv) if a == flag and argv[i + 1].startswith(prefix)]


def test_aot_layout():
    plan = aot_plan()
    encoded = {0: Path("tmp/audio0_ja.m4a"), 1: Path("tmp/audio1_en.ec3")}
    argv = mux_command(plan, encoded, OUT, "mkvmerge", RAW)

    assert argv[:3] == ["mkvmerge", "--output", "out.mkv"]
    assert value(argv, "--default-duration") == ["0:24000/1001p"]
    assert value(argv, "--chapters") == ["qpf_chapters.txt"]
    # Inputs: encode, source, 2 audio, 2 external SRTs
    inputs = [a for a in argv if a.endswith((".h264", ".mkv", ".m4a", ".ec3", ".srt")) and a != "out.mkv"]
    assert inputs == [
        "Show.S01E01_job.h264",
        "Show.S01E01.mkv",
        str(Path("tmp/audio0_ja.m4a")),
        str(Path("tmp/audio1_en.ec3")),
        *[str(s.source.external_path) for s in plan.subs if s.source.is_external],
    ]
    # Source contributes no video/audio, only the internal subs
    assert "--no-video" in argv and "--no-audio" in argv
    internal = [s.source.id for s in plan.subs if not s.source.is_external]
    assert value(argv, "--subtitle-tracks") == [",".join(map(str, internal))]
    # Track order: video, audio in plan order, subs in plan order
    order = value(argv, "--track-order")[0].split(",")
    assert order[:3] == ["0:0", "2:0", "3:0"]
    assert len(order) == 1 + len(plan.audio) + len(plan.subs)
    # Delay once: AAC at mux; DeeZy already baked the DDP delay in
    assert value(argv, "--sync") == ["0:-7"]


def test_titles_and_flags_follow_plan():
    plan = aot_plan()
    argv = mux_command(plan, {0: Path("a.m4a"), 1: Path("b.ec3")}, OUT, "mkvmerge", RAW)
    titles = {n.split(":", 1)[1] for n in value(argv, "--track-name")}
    assert {a.title for a in plan.audio} | {s.title for s in plan.subs} == titles
    forced = value(argv, "--forced-display-flag")
    assert forced.count("0:1") == 1  # the external forced SRT


def test_video_start_shifts_source_and_extracted_srt():
    plan = aot_plan(start_ms=838)
    argv = mux_command(plan, {0: Path("a.m4a"), 1: Path("b.ec3")}, OUT, "mkvmerge", RAW)
    syncs = value(argv, "--sync")
    internal = [s.source.id for s in plan.subs if not s.source.is_external]
    for tid in internal:
        assert f"{tid}:-838" in syncs
    # extracted SRT shifted, NF SRT not; encoded audio keeps only its own delay
    assert syncs.count("0:-838") == 1
    assert "0:-7" in syncs and "0:12" not in syncs


def test_mkv_encode_and_source_chapters():
    plan = aot_plan(encode="Show.S01E01_job.mkv", chapters=False)
    argv = mux_command(plan, {0: Path("a.m4a"), 1: Path("b.ec3")}, OUT, "mkvmerge", RAW)
    assert "--default-duration" not in argv
    assert "--chapters" not in argv
    encode_args = argv[: argv.index("Show.S01E01_job.mkv")]
    assert {"--no-audio", "--no-subtitles", "--no-chapters"} <= set(encode_args)
    source_args = argv[argv.index("Show.S01E01_job.mkv") : argv.index("Show.S01E01.mkv")]
    assert "--no-chapters" not in source_args


def test_copied_audio_keeps_container_delay_without_sync():
    src = source([audio(C.AC3, "5.1", "en", index=0)], name="Movie.mkv")
    src.video = VideoInfo(1920, 1080, default_duration_ns=41708333)
    src.audio[0].delay_ms = 25
    plan = plan_for(src, source(name="Movie_job.h264"), external_subs=[sub(F.SRT, "en", external="Movie.en.srt")])
    plan.encode_path = Path("Movie_job.h264")
    argv = mux_command(plan, {}, OUT, "mkvmerge", RAW)
    assert value(argv, "--audio-tracks") == [str(src.audio[0].id)]
    assert "--sync" not in argv  # mkvmerge carries the copied track's own timestamps


def test_missing_encoded_audio_fails():
    with pytest.raises(MuxError):
        mux_command(aot_plan(), {0: Path("a.m4a")}, OUT, "mkvmerge", RAW)


def test_every_flag_is_written_explicitly():
    src = source(
        [audio(C.AC3, "5.1", "en", index=0, default=True), audio(C.AC3, "2.0", "en", index=1, commentary=True)],
        [sub(F.SRT, "en", index=0, hi=True)],
        name="Movie.mkv",
    )
    ov = Overrides(tracks={"id:1": TrackOverride(flags={"original": True}), "id:10": TrackOverride(title="English SDH")})
    plan = plan_for(src, source(name="Movie_job.mkv"), ov)
    argv = mux_command(plan, {}, OUT, "mkvmerge", RAW)
    assert value(argv, "--default-track-flag", "1:") == ["1:1"]
    assert value(argv, "--original-flag") == ["1:1", "2:0", "10:0"]
    assert value(argv, "--commentary-flag") == ["1:0", "2:1", "10:0"]
    assert value(argv, "--hearing-impaired-flag") == ["1:0", "2:0", "10:1"]
    assert "10:English SDH" in value(argv, "--track-name")
    assert value(argv, "--audio-tracks") == ["1,2"]


@pytest.mark.parametrize(
    ("ns", "rate"),
    [(41708333, "24000/1001p"), (41708334, "24000/1001p"), (40000000, "25p"), (16683333, "60000/1001p"),
     (41666667, "24p"), (12345678, "12345678ns")],
)
def test_frame_rate(ns, rate):
    assert _frame_rate(ns) == rate


def test_added_audio_files_are_their_own_inputs():
    src = source([audio(C.FLAC, "2.0", "ja", index=0)], name="Show.S01E01.mkv")
    src.video = VideoInfo(1920, 1080, start_ms=0, default_duration_ns=41708333)
    commentary = audio(C.AC3, "2.0", "en", index=0, title="Commentary")
    commentary.id, commentary.external_path, commentary.delay_ms = 0, Path("extra/Commentary DELAY 42ms.ac3"), 42
    dub = audio(C.DTS_HD_MA, "5.1", "de", index=1)
    dub.id, dub.external_path, dub.delay_ms = 1, Path("extra/German.mka"), -10
    plan = plan_for(src, source(name="enc.h264"), external_audio=[commentary, dub])
    plan.encode_path = Path("enc.h264")
    plan.audio[2].action, plan.audio[2].out_codec = AudioAction.FLAC, C.FLAC  # the German track gets encoded
    argv = mux_command(plan, {2: Path("tmp/audio2_de.flac")}, OUT, "mkvmerge", RAW)

    i = argv.index(str(Path("extra/Commentary DELAY 42ms.ac3")))
    own = argv[argv.index("--no-video", argv.index("Show.S01E01.mkv")) : i]
    assert value(own, "--audio-tracks") == ["0"] and value(own, "--sync") == ["0:42"]
    assert value(own, "--track-name") == ["0:Commentary"] and "--no-subtitles" in own
    assert value(argv, "--audio-tracks") == ["1", "0"]  # the source's track, then the commentary's
    assert str(Path("extra/German.mka")) not in argv  # encoded: muxed from its encode, its delay applied there
    j = argv.index(str(Path("tmp/audio2_de.flac")))
    assert value(argv[i:j], "--sync") == ["0:-10"]
    assert value(argv, "--track-order") == ["0:0,1:1,2:0,3:0"]


def test_added_audio_keys_and_names():
    from videoforge.core.models import track_key
    from videoforge.core.pairing import name_delay_ms, name_language, name_without_delay

    t = audio(C.AC3, "2.0", index=0)
    t.external_path = Path("x/Show DELAY -42ms.ac3")
    assert track_key(t) == "ext:Show DELAY -42ms.ac3"
    t.index = 2
    assert track_key(t) == "ext:Show DELAY -42ms.ac3#2"
    assert name_delay_ms("Show T2 eng DELAY -42ms") == -42 and name_delay_ms("Show 3 2 1") is None
    assert name_language("Show.Commentary.en") == "en" and name_language("Show 5.1") is None
    assert name_language(name_without_delay("Commentary.en DELAY 100ms")) == "en"
    assert name_language(name_without_delay("Movie T2 eng DELAY -42ms")) == "en"


def test_copies_of_a_track():
    from videoforge.core.models import copy_base, track_key, with_copies

    assert copy_base("id:1+2") == ("id:1", 2) and copy_base("ext:a+b.flac") == ("ext:a+b.flac", 0)
    assert copy_base("ext:a+b.flac+1") == ("ext:a+b.flac", 1) and copy_base("id:1+0") == ("id:1+0", 0)
    src = source([audio(C.TRUEHD, "7.1", "en", index=0, default=True), audio(C.AC3, "2.0", "en", index=1)],
                 name="Movie.mkv")
    src.video = VideoInfo(1920, 1080, start_ms=40, default_duration_ns=41708333)
    copies = with_copies(src.audio, ["id:1+1", "id:1+2", "id:9+1"])  # id:9 isn't there
    assert [track_key(t) for t in copies] == ["id:1", "id:2", "id:1+1", "id:1+2"]
    assert copies[2].default is False and copies[2].id == 1  # the same source track

    # One copy encoded, one copied as is (its own input: mkvmerge takes a track once per input).
    ov = Overrides(copies=["id:1+1", "id:1+2"], order=["id:1+1", "id:1", "id:2", "id:1+2"],
                   tracks={"id:1+1": TrackOverride(action=AudioAction.AAC_FFMPEG, layout=Layout(2, 0))})
    plan = plan_for(src, source(name="enc.h264"), ov)
    plan.encode_path = Path("enc.h264")
    assert [(track_key(a.source), a.action) for a in plan.audio] == [
        ("id:1+1", AudioAction.AAC_FFMPEG), ("id:1", AudioAction.COPY), ("id:2", AudioAction.COPY),
        ("id:1+2", AudioAction.COPY)]
    argv = mux_command(plan, {0: Path("tmp/audio0_en.m4a")}, OUT, "mkvmerge", RAW)
    assert value(argv, "--audio-tracks") == ["1,2", "1"]
    assert argv.count("Movie.mkv") == 2
    second = argv[argv.index("Movie.mkv") + 1 : len(argv) - argv[::-1].index("Movie.mkv")]
    assert value(second, "--sync") == ["1:-40"]  # shifted like the source's other tracks
    assert value(argv, "--track-order") == ["0:0,2:0,1:1,1:2,3:1"]


def test_audio_description_flag():
    src = source([audio(C.AC3, "2.0", "en", index=0), audio(C.AC3, "2.0", "en", index=1, title="Audio Description")],
                 name="Movie.mkv")
    src.audio[1].visual_impaired = True
    plan = plan_for(src, source(name="enc.mkv"), Overrides(tracks={"id:1": TrackOverride(flags={"visual_impaired": True}),
                                                                   "id:2": TrackOverride(flags={"visual_impaired": False})}))
    plan.encode_path = Path("enc.mkv")
    assert [a.visual_impaired for a in plan.audio] == [True, False]  # the user's choice over the file's
    argv = mux_command(plan, {}, OUT, "mkvmerge", RAW)
    assert value(argv, "--visual-impaired-flag") == ["1:1", "2:0"]
