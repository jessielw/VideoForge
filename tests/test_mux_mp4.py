"""MP4 output: the MP4Box command, what an MP4 can't hold, chapters for it, and the output check."""

from __future__ import annotations

from pathlib import Path

from conftest import audio, plan_for, simulate_output, source, sub

from videoforge.core.execute import chapters as ogm
from videoforge.core.execute.mux import MUXERS, MuxSettings, mp4box_command, mux_issues, muxer_for, split_args
from videoforge.core.job import JobSpec
from videoforge.core.models import (
    AudioAction,
    AudioCodec as C,
    JobInputs,
    Layout,
    Overrides,
    Severity,
    SubFormat as F,
    TrackOverride,
    VideoInfo,
)
from videoforge.core.pipeline.build import output_path
from videoforge.profiles.manual import ManualProfile, output_matches_plan

RAW = (".h264", ".hevc")


def mp4_plan(subs=None, overrides=None):
    src = source(
        [
            audio(C.AC3, "5.1", "en", index=0, default=True, title="Main: 5.1"),
            audio(C.FLAC, "2.0", "ja", index=1, commentary=True),
        ],
        subs if subs is not None else [sub(F.SRT, "en", "English", index=0, forced=True)],
        name="Movie.mkv",
    )
    src.video = VideoInfo(1920, 1080, start_ms=40, default_duration_ns=41708333, language="en-US")
    src.audio[1].delay_ms = 25
    src.audio[0].original = True  # as most releases flag their tracks
    plan = plan_for(src, source(name="enc.h264"), overrides)
    plan.encode_path = Path("enc.h264")
    return plan


def adds(argv):
    return [argv[i + 1] for i, a in enumerate(argv) if a == "-add"]


def test_mp4box_command():
    ov = Overrides(tracks={"id:2": TrackOverride(action=AudioAction.AAC_FFMPEG, layout=Layout(2, 0))})
    plan = mp4_plan(overrides=ov)
    plan.chapters_path = Path("work/chapters_chapters.txt")
    argv = mp4box_command(
        plan, {1: Path("tmp/audio1_ja.m4a")}, Path("out.mp4.partial"), "MP4Box", RAW, split_args('-tmp "D:\\tmp dir"')
    )
    assert argv[:2] == ["MP4Box", "-noprog"]
    assert adds(argv) == [
        "enc.h264:fps=24000/1001:lang=en-US:name=",  # the source's exact rate and language; no GPAC handler name
        # copied from the source: mkvmerge id + 1, shifted by the source's start; ':' can't be in a name
        "Movie.mkv#trackID=2:lang=en:group=1:name=Main - 5.1:delay=-40",
        # encoded: ffmpeg's AAC doesn't keep the delay, so the mux applies it
        f"{Path('tmp/audio1_ja.m4a')}:lang=ja:group=1:disable:delay=25",
        "Movie.mkv#trackID=11:lang=en:group=2:name=English:disable:delay=-40:txtflags=C0000000",
    ]
    assert argv[argv.index("-chap") + 1] == str(Path("work/chapters_chapters.txt"))
    assert argv[-4:] == ["-tmp", '"D:\\tmp dir"', "-new", "out.mp4.partial"]


def test_mp4_issues():
    plan = mp4_plan([sub(F.PGS, "en", index=0), sub(F.SRT, "en", "Signs", index=1, forced=True, hi=True)])
    issues = mux_issues(plan, "mp4")
    blocks = [i.message for i in issues if i.severity is Severity.BLOCK]
    warns = [i.message for i in issues if i.severity is Severity.WARN]
    assert blocks == ["Subtitle 1 (pgs) can't go into MP4 (SRT and VobSub can): leave it out or use MKV"]
    assert "Audio 2: MP4 has no commentary flag; left out" in warns
    assert "Subtitle 2: MP4 has no hearing impaired flag; left out" in warns  # forced is carried on an SRT
    assert any("written as 'Main - 5.1'" in w for w in warns)
    assert plan.audio[0].original and not any("original" in w for w in warns)  # the source's own flag: no warning
    assert mux_issues(plan, "mkv") == []

    plan = mp4_plan(overrides=Overrides(tracks={"id:1": TrackOverride(flags={"original": True})}))
    assert "Audio 1: MP4 has no original flag; left out" in [i.message for i in mux_issues(plan, "mp4")]  # set by hand


def test_job_container_and_output_name():
    profile = ManualProfile()
    spec = JobSpec(inputs=JobInputs(Path("Movie.mkv")), profile="manual")
    plan = mp4_plan()
    assert spec.container(profile) == "mkv"
    spec.mux = MuxSettings(container="mp4")
    assert spec.container(profile) == "mp4"
    assert output_path(plan, Path("out"), profile, spec.container(profile)) == Path("out/Movie.mp4")
    spec.mux = MuxSettings(container="avi")  # not offered: the profile's
    assert spec.container(profile) == "mkv"
    assert muxer_for(Path("x.MP4")) is MUXERS["mp4"] and muxer_for(Path("x.mkv")) is MUXERS["mkv"]


def test_mp4_output_check():
    plan = mp4_plan()
    out = simulate_output(plan, "Movie.mp4")
    for t in [*out.audio, *out.subs]:  # what mkvmerge reads back from an MP4
        t.title, t.commentary, t.forced = "", False, False
    for s in out.subs:
        s.format = F.TX3G
    assert output_matches_plan(plan, out) == []
    out.audio[0].default = False  # the enabled flag is read back
    assert [i.code for i in output_matches_plan(plan, out)] == ["plan.audio"]


def test_chapters_as_ogm(tmp_path):
    xml = tmp_path / "ch.xml"
    xml.write_text(
        "<?xml version='1.0'?><Chapters><EditionEntry>"
        "<ChapterAtom><ChapterTimeStart>00:00:00.000000000</ChapterTimeStart>"
        "<ChapterDisplay><ChapterString>Opening</ChapterString></ChapterDisplay></ChapterAtom>"
        "<ChapterAtom><ChapterFlagHidden>1</ChapterFlagHidden><ChapterTimeStart>00:01:00.000</ChapterTimeStart></ChapterAtom>"
        "<ChapterAtom><ChapterTimeStart>01:02:03.456789</ChapterTimeStart></ChapterAtom>"
        "</EditionEntry></Chapters>",
        encoding="utf-8",
    )
    found = ogm.from_xml(xml)
    assert found == [(0, "Opening"), (3723457, "")]
    assert ogm.ogm_text(found) == (
        "CHAPTER01=00:00:00.000\nCHAPTER01NAME=Opening\nCHAPTER02=01:02:03.457\nCHAPTER02NAME=Chapter 02\n"
    )
