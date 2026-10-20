"""A subtitle track burned into the video (core/video/burn.py): the plan, the script, the extract, a template's rule."""

from __future__ import annotations

from pathlib import Path
import subprocess

from conftest import source, sub
import pytest

from videoforge.core.config import AppConfig, Tools
from videoforge.core.job import JobSpec
from videoforge.core.jobs import ProbedInputs, plan_job
from videoforge.core.models import (
    Issue,
    JobInputs,
    Overrides,
    Plan,
    Severity,
    SubFormat as F,
    SubRule,
    TemplateSubs,
    TrackOverride,
    VideoInfo,
)
from videoforge.core.pipeline.build import index_steps, indexed
from videoforge.core.template import apply_subs
from videoforge.core.video import burn
from videoforge.core.video.script import build_script, script_parts
from videoforge.core.video.settings import Crop, VideoSettings
from videoforge.profiles.manual import ManualProfile

BURN = TrackOverride(burn=True)


def probed(*subs, encode: Path | None = None, external=()) -> ProbedInputs:
    src = source(subs=subs)
    return ProbedInputs(JobInputs(src.path or Path(), encode=encode), src, None, list(external))


def subs_issues(plan: Plan) -> list[Issue]:
    return [i for i in plan.issues if i.code.startswith("subs.")]  # a plan with no encode also says so


def test_the_burned_track_leaves_the_mux():
    en, fr = sub(F.SRT, "en", index=0), sub(F.PGS, "fr", index=1)
    plan = plan_job(ManualProfile(), probed(en, fr), overrides=Overrides(tracks={"id:10": BURN}))
    assert plan.burn is en and [s.source.id for s in plan.subs] == [11]
    assert not subs_issues(plan)

    # An added file can be burned; a second marked one warns (the first, in source order, is burned).
    added = sub(F.ASS, "en", external="Movie.en.ass")
    ov = Overrides(tracks={"id:11": BURN, "ext:Movie.en.ass": BURN})
    plan = plan_job(ManualProfile(), probed(en, fr, external=[added]), overrides=ov)
    assert plan.burn is fr and [s.source.id for s in plan.subs] == [10, -1]
    assert [i.code for i in subs_issues(plan)] == ["subs.burn_many"]

    # Only an encode burns: a reused one muxes the track as it is.
    plan = plan_job(
        ManualProfile(), probed(en, fr, encode=Path("enc.mkv")), overrides=Overrides(tracks={"id:10": BURN})
    )
    assert plan.burn is None and len(plan.subs) == 2


def test_a_format_subtext_cant_draw_blocks():
    plan = plan_job(ManualProfile(), probed(sub(F.TX3G, "en")), overrides=Overrides(tracks={"id:10": BURN}))
    assert [(i.severity, i.code) for i in subs_issues(plan)] == [(Severity.BLOCK, "subs.burn_format")]


def test_text_is_drawn_after_the_crop_and_an_image_before_it():
    s, work = VideoSettings(crop=Crop(0, 140, 0, 140)), Path("w")
    body = script_parts(s, Path("a.mkv"), work, burn=sub(F.SRT, index=2))[1]
    assert body == [
        "clip = core.std.Crop(clip, left=0, right=0, top=140, bottom=140)",
        f"clip = core.sub.TextFile(clip, file={str(work / 'burn.12.srt')!r})",
    ]
    body = script_parts(s, Path("a.mkv"), work, burn=sub(F.PGS, index=2))[1]
    assert body[0] == f"clip = core.sub.ImageFile(clip, file={str(work / 'burn.12.sup')!r})"

    # An added VobSub is read by its .idx; a custom body gets it last; auto crop's source stage never.
    vobsub = sub(F.VOBSUB, external="D:/subs/Movie.sub")
    custom = VideoSettings(custom="clip = src[1:]")
    assert script_parts(custom, Path("a.mkv"), work, burn=vobsub)[1] == [
        "clip = src[1:]",
        f"clip = core.sub.ImageFile(clip, file={str(Path('D:/subs/Movie.idx'))!r})",
    ]
    assert "core.sub" not in build_script(s, Path("a.mkv"), work, stage="source", burn=vobsub)


def test_a_source_track_is_extracted_with_the_index(tmp_path):
    src = tmp_path / "Movie.mkv"
    job = JobSpec(inputs=JobInputs(src), profile="manual")
    names = ("mkvmerge", "deezy", "dee", "truehdd", "qaac", "ffmpeg", "mkvextract", "vspipe")
    app = AppConfig(tools=Tools(**{n: n for n in names}))
    track = sub(F.ASS, index=3)
    steps = index_steps(job, app, None, track)
    assert [s.id for s in steps] == ["script", "burn.extract", "index"]
    out = job.work_dir / "burn.13.ass"
    assert steps[1].argvs == (("mkvextract", "--ui-language", "en", "tracks", str(src), f"13:{out}"),)
    assert repr(str(out)) in (steps[0].key or "")  # the script draws the extracted file

    # The preview waits for it like the index; an added file is read where it is.
    (job.work_dir / "Movie.mkv.ffindex").parent.mkdir(parents=True, exist_ok=True)
    (job.work_dir / "Movie.mkv.ffindex").write_bytes(b"index")
    assert indexed(job, None, None) and not indexed(job, None, track)
    out.write_text("[Script Info]", encoding="utf-8")
    assert indexed(job, None, track)
    added = sub(F.SRT, external=str(tmp_path / "Movie.en.srt"))
    assert [s.id for s in index_steps(job, app, None, added)] == ["script", "index"]
    assert burn.file(added, job.work_dir) == tmp_path / "Movie.en.srt"


def test_a_track_of_an_m2ts_is_copied_into_an_mks_for_mkvextract(tmp_path):
    """mkvextract reads Matroska only: from another container, mkvmerge copies the track out first."""
    src = tmp_path / "00005.m2ts"
    job = JobSpec(inputs=JobInputs(src), profile="manual")
    names = ("mkvmerge", "deezy", "dee", "truehdd", "qaac", "ffmpeg", "mkvextract", "vspipe")
    app = AppConfig(tools=Tools(**{n: n for n in names}))
    steps = index_steps(job, app, None, sub(F.PGS, index=4))
    assert [s.id for s in steps] == ["script", "burn.remux", "burn.extract", "index"]
    mks, out = job.work_dir / "burn.14.mks", job.work_dir / "burn.14.sup"
    assert steps[1].argvs == (
        ("mkvmerge", "--ui-language", "en", "--output", str(mks), "--no-video", "--subtitle-tracks", "14",
         "--no-audio", "--no-chapters", "--no-attachments", "--no-global-tags", "--no-track-tags", str(src)),
    )  # fmt: skip
    assert steps[2].argvs == (("mkvextract", "--ui-language", "en", "tracks", str(mks), f"0:{out}"),)
    assert steps[2].inputs == (mks,)


def test_a_templates_burn_rule_takes_the_first_track_it_matches():
    """The first match is burned (and not muxed); later ones go on to the next rule."""
    forced, full = sub(F.PGS, "en", index=0, forced=True), sub(F.PGS, "en", index=1)
    rules = TemplateSubs([SubRule(languages=["en"], track=BURN), SubRule(languages=["en"])])
    out = apply_subs(Overrides(), rules, [forced, full])
    assert out.tracks == {"id:10": BURN}
    assert out.order == ["id:11"]


def test_source_burns_shift_but_standalone_files_do_not(tmp_path):
    from test_pipeline import APP

    job = JobSpec(inputs=JobInputs(tmp_path / "source.mkv"), profile="manual")
    video = VideoInfo(640, 360, start_ms=500)
    for fmt in (F.SRT, F.ASS, F.PGS, F.VOBSUB):
        steps = index_steps(job, APP, video, sub(fmt))
        remux = next(s for s in steps if s.id == "burn.remux")
        assert remux.argvs[0][-3:] == ("--sync", "10:-500", str(job.inputs.source))
    added = sub(F.SRT, external=str(tmp_path / "extracted.srt"))
    assert burn.shift_ms(added, job.inputs.source, video) == 0
    added.extracted_from = 2
    assert burn.file(added, job.work_dir).parent == job.work_dir
    steps = index_steps(job, APP, video, added)
    assert next(s for s in steps if s.id == "burn.remux").argvs[0][-3:] == (
        "--sync",
        "0:-500",
        str(added.external_path),
    )


def test_real_burn_cue_uses_video_origin(tmp_path):
    from videoforge.core.config import load_app_config
    from videoforge.core.probe import probe
    from videoforge.core.video.vs import configure

    app = load_app_config()
    if not Path(app.tools.mkvmerge).is_file():
        pytest.skip("needs MKVToolNix")
    configure(app.tools.vs_plugins)
    import numpy as np
    import vapoursynth as vs

    cue = tmp_path / "cue.srt"
    cue.write_text("1\n00:00:01,200 --> 00:00:02,000\nTiming cue\n", encoding="utf-8")
    src = tmp_path / "source.mkv"
    subprocess.run([app.tools.mkvmerge, "-o", str(src), str(cue)], check=True, capture_output=True)
    track = probe(src, app.tools.mkvmerge).subs[0]
    job = JobSpec(inputs=JobInputs(src), profile="manual")
    job.work_dir.mkdir()
    steps = index_steps(job, app, VideoInfo(640, 360, start_ms=500), track)
    for step in steps:
        if step.id.startswith("burn."):
            for argv in step.argvs:
                subprocess.run(argv, check=True, capture_output=True)
    assert "00:00:00,700 --> 00:00:01,500" in burn.file(track, job.work_dir).read_text(encoding="utf-8")
    plain = vs.core.std.BlankClip(width=640, height=360, length=75, fpsnum=25, format=vs.YUV420P8)
    namespace = {"core": vs.core, "clip": plain}
    exec("\n".join(burn.lines(track, job.work_dir)), namespace)  # noqa: S102 - generated script
    rendered = namespace["clip"]
    for frame, visible in ((17, False), (18, True), (37, True), (38, False)):
        with plain.get_frame(frame) as a, rendered.get_frame(frame) as b:
            assert bool(np.any(np.asarray(a[0]) != np.asarray(b[0]))) is visible


@pytest.mark.parametrize("two_pass", [False, True])
@pytest.mark.parametrize("fmt", [F.SRT, F.VOBSUB])
def test_editing_burn_inputs_invalidates_video_and_preview(tmp_path, two_pass, fmt):
    from test_pipeline import APP, make_plan, video_job

    from videoforge.core.pipeline.build import build_steps
    from videoforge.core.video.settings import RateControl

    plan = make_plan(tmp_path)
    job = video_job(plan, tmp_path)
    if two_pass:
        job.encoder.rate_control = RateControl.TWO_PASS
    added = tmp_path / ("sub.idx" if fmt is F.VOBSUB else "sub.srt")
    added.write_bytes(b"original")
    payload = added.with_suffix(".sub") if fmt is F.VOBSUB else added
    payload.write_bytes(b"subtitle payload")
    plan.burn = sub(fmt, external=str(added))

    def video_steps():
        return [
            s
            for s in build_steps(job, plan, ManualProfile(), APP, tmp_path / "out.mkv").steps
            if s.id == "video" or s.id.startswith("video.")
        ]

    old = [s.fingerprint() for s in video_steps()]
    script = build_script(job.video, job.inputs.source, job.work_dir, burn=plan.burn)
    payload.write_bytes(b"changed subtitle payload")
    assert all(a != b.fingerprint() for a, b in zip(old, video_steps(), strict=True))
    assert script != build_script(job.video, job.inputs.source, job.work_dir, burn=plan.burn)
    assert burn.present(plan.burn, job.work_dir)
    payload.unlink()
    assert not burn.present(plan.burn, job.work_dir)


def test_vobsub_extract_records_both_files(tmp_path):
    from test_pipeline import APP

    job = JobSpec(inputs=JobInputs(tmp_path / "source.mkv"), profile="manual")
    track = sub(F.VOBSUB)
    extract = next(s for s in index_steps(job, APP, None, track) if s.id == "burn.extract")
    assert extract.outputs == (job.work_dir / "burn.10.idx", job.work_dir / "burn.10.sub")
