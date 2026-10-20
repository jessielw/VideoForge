"""MP4 output: the MP4Box command, what an MP4 can't hold, chapters for it, and the output check."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

from conftest import audio, plan_for, simulate_output, source, sub
import pytest

from videoforge.core.config import load_app_config
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
from videoforge.core.pipeline.build import build_steps, mp4_subtitle_steps, output_path
from videoforge.core.video.color import ContainerColor
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
    src.audio[0].delay_ms = -40  # it starts with the container, the video 40 ms later
    src.audio[1].delay_ms = 25
    src.audio[0].original = True  # as most releases flag their tracks
    plan = plan_for(src, source(name="enc.h264"), overrides)
    plan.encode_path = Path("enc.h264")
    return plan


def adds(argv):
    return [argv[i + 1] for i, a in enumerate(argv) if a == "-add"]


def test_mp4box_raw_encode_takes_the_scripts_frame_rate():
    plan = mp4_plan()
    argv = mp4box_command(plan, {}, Path("out.mp4.partial"), "MP4Box", RAW, fps=Fraction(24000, 1001))
    assert adds(argv)[0] == "enc.h264:fps=24000/1001:hdr=none:lang=en-US:name="
    plan.source.video.default_duration_ns = 33366667  # a 29.97 source an IVTC made 23.976
    argv = mp4box_command(plan, {}, Path("out.mp4.partial"), "MP4Box", RAW, fps=Fraction(24000, 1001))
    assert adds(argv)[0].startswith("enc.h264:fps=24000/1001:")
    argv = mp4box_command(plan, {}, Path("out.mp4.partial"), "MP4Box", RAW)
    assert adds(argv)[0].startswith("enc.h264:fps=30000/1001:")


def test_mp4box_vpx_encode_is_tagged():
    """A VP8 / VP9 IVF is taken as it is (#video: it times itself), with its pixel aspect and a colr box (all four
    values: 2 where the source gives none)."""
    plan = mp4_plan()
    plan.encode_path = Path("video.ivf")
    color = ContainerColor(primaries=9, transfer=16, matrix=None, full_range=None)
    argv = mp4box_command(plan, {}, Path("out.mp4.partial"), "MP4Box", RAW, sar=Fraction(4, 3), color=color)
    assert adds(argv)[0] == "video.ivf#video:par=4:3:colr=nclx,9,16,2,0:hdr=none:lang=en-US:name="
    argv = mp4box_command(plan, {}, Path("out.mp4.partial"), "MP4Box", RAW, sar=Fraction(1))
    assert adds(argv)[0] == "video.ivf#video:hdr=none:lang=en-US:name="
    # an AV1 encode's HDR10: MP4Box writes its mdcv / clli boxes from the stream, which hdr=none would drop
    av1 = ContainerColor(9, 16, 9, False, max_cll=1000, max_fall=400)
    argv = mp4box_command(plan, {}, Path("out.mp4.partial"), "MP4Box", RAW, color=av1)
    assert adds(argv)[0] == "video.ivf#video:colr=nclx,9,16,9,0:lang=en-US:name="


def test_mp4box_command():
    ov = Overrides(tracks={"id:2": TrackOverride(action=AudioAction.AAC_FFMPEG, layout=Layout(2, 0))})
    plan = mp4_plan(overrides=ov)
    plan.chapters_path = Path("work/chapters_chapters.txt")
    argv = mp4box_command(
        plan, {1: Path("tmp/audio1_ja.m4a")}, Path("out.mp4.partial"), "MP4Box", RAW, split_args('-tmp "D:\\tmp dir"')
    )
    assert argv[:2] == ["MP4Box", "-noprog"]
    assert adds(argv) == [
        # the source's exact rate and language; no GPAC handler name; no HDR boxes (the stream carries them)
        "enc.h264:fps=24000/1001:hdr=none:lang=en-US:name=",
        # copied from the source: mkvmerge id + 1, its delay to the video (MP4Box starts it at 0); no ':' in a name
        "Movie.mkv#trackID=2:lang=en:group=1:name=Main - 5.1:delay=-40",
        # encoded: ffmpeg's AAC doesn't keep the delay, so the mux applies it
        f"{Path('tmp/audio1_ja.m4a')}:lang=ja:group=1:disable:delay=25",
        "Movie.mkv#trackID=11:lang=en:group=2:name=English:disable:delay=-40:txtflags=C0000000",
    ]
    assert argv[argv.index("-chap") + 1] == str(Path("work/chapters_chapters.txt"))
    assert argv[-4:] == ["-tmp", "D:\\tmp dir", "-new", "out.mp4.partial"]


@pytest.mark.parametrize("start_ms", [0, 500])
def test_mp4_pipeline_extracts_source_srt_with_one_timing_shift(tmp_path, start_ms):
    plan = mp4_plan()
    plan.source.video.start_ms = start_ms
    original_sub = plan.subs[0]
    app = load_app_config()
    steps, prepared = mp4_subtitle_steps(plan, tmp_path, app)
    assert len(steps) == (2 if start_ms else 1)
    if start_ms:
        argv = steps[0].argvs[0]
        assert argv[argv.index("--sync") + 1] == f"{original_sub.source.id}:-500"
        assert steps[1].inputs == steps[0].outputs
    else:
        assert steps[0].inputs == (plan.source.path,)
    extracted = tmp_path / "subtitle.1.srt"
    assert steps[-1].outputs == (extracted,)
    assert prepared.subs[0].source.external_path == extracted
    assert not plan.subs[0].source.is_external  # the UI/validation plan keeps the original source identity
    assert prepared.subs[0].title == original_sub.title
    assert prepared.subs[0].forced == original_sub.forced
    spec = JobSpec(
        inputs=JobInputs(plan.source.path, encode=plan.encode_path), profile="manual", mux=MuxSettings(container="mp4")
    )
    job = build_steps(spec, plan, ManualProfile(), app, tmp_path / "out.mp4")
    assert "subs.1.extract" in [step.id for step in job.steps]
    mux = job.steps[-1]
    expected = spec.work_dir / "subtitle.1.srt"
    assert expected in mux.inputs
    sub_arg = adds(mux.argvs[0])[-1]
    assert sub_arg == f"{expected}:lang=en:group=2:name=English:disable:txtflags=C0000000"
    spec.mux.container = "mkv"
    mkv = build_steps(spec, plan, ManualProfile(), app, tmp_path / "out.mkv")
    assert not any(s.id.startswith("subs.") for s in mkv.steps)


def test_mp4_leaves_external_srt_and_native_timed_text_inputs(tmp_path):
    plan = mp4_plan([sub(F.TX3G, "en")])
    plan.subs[0].source.format = F.TX3G
    steps, prepared = mp4_subtitle_steps(plan, tmp_path, load_app_config())
    assert steps == [] and prepared.subs == plan.subs
    plan.subs[0].source.format = F.SRT
    plan.subs[0].source.external_path = tmp_path / "external.srt"
    steps, prepared = mp4_subtitle_steps(plan, tmp_path, load_app_config())
    assert steps == [] and prepared.subs == plan.subs


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


def test_a_vfr_source_into_mp4_warns():
    """MP4Box takes no timestamps file: a VFR source's MP4 is muxed at a constant rate (MKV keeps them)."""
    plan = mp4_plan()
    assert not [i for i in mux_issues(plan, "mp4") if i.code == "mux.mp4_vfr"]
    plan.source.video.vfr = True
    assert [(i.severity, i.code) for i in mux_issues(plan, "mp4") if i.code == "mux.mp4_vfr"] == [
        (Severity.WARN, "mux.mp4_vfr")
    ]
    assert mux_issues(plan, "mkv") == []


def test_job_container_and_output_name():
    profile = ManualProfile()
    spec = JobSpec(inputs=JobInputs(Path("Movie.mkv")), profile="manual")
    plan = mp4_plan()
    assert spec.container(profile) == "mkv"
    spec.mux = MuxSettings(container="mp4")
    assert spec.container(profile) == "mp4"
    assert output_path(spec, plan, profile, Path("out")) == Path("out/Movie.mp4")
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


def test_mp4_languages_are_3_letter_codes():
    """MP4Box writes ISO 639-2 (StaxRip too): a region or script is left out (a warning), and the output check
    compares the language alone. A Fallout sample read back es-419 as es, eu as baq, nb as no."""
    tags = ["es-419", "eu", "nb", "zh-Hant", "en"]
    plan = mp4_plan([sub(F.SRT, t, index=n) for n, t in enumerate(tags)])
    warns = [i.message for i in mux_issues(plan, "mp4") if i.code == "mux.mp4_language"]
    assert warns == [
        "Subtitle 1: MP4 holds a 3-letter language code; es-419 is written as es",
        "Subtitle 3: MP4 holds a 3-letter language code; nb is written as no",
        "Subtitle 4: MP4 holds a 3-letter language code; zh-Hant is written as zh",
    ]
    out = simulate_output(plan, "Movie.mp4")
    for t in [*out.audio, *out.subs]:
        t.title, t.commentary, t.forced = "", False, False
    for s, back in zip(out.subs, ["es", "baq", "no", "zh", "eng"], strict=True):
        s.format, s.language = F.TX3G, back
    assert output_matches_plan(plan, out) == []
    out.subs[0].language = "fr"
    assert [i.code for i in output_matches_plan(plan, out)] == ["plan.subs"]


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
