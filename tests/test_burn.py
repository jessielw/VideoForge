"""A subtitle track burned into the video (core/video/burn.py): the plan, the script, the extract, a template's rule."""

from __future__ import annotations

from pathlib import Path

from conftest import source, sub

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
