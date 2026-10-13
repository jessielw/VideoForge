"""The built-in manual profile: every track in source order, shaped only by the user's overrides."""

from __future__ import annotations

from conftest import audio, plan_for, simulate_output, source, sub

from videoforge.core.models import AudioAction, Overrides, Severity, TrackOverride
from videoforge.core.models import AudioCodec as C
from videoforge.core.models import SubFormat as F
from videoforge.profiles import default_profile_id, get_profile, profile_ids
from videoforge.profiles.manual import ManualProfile


def movie():
    return source(
        [audio(C.TRUEHD, "7.1", "en", index=0, default=True), audio(C.AC3, "2.0", "en", index=1, commentary=True)],
        [sub(F.PGS, "en", "English", index=0), sub(F.PGS, "fr", "French", index=1, forced=True)],
    )


def test_builtin_is_registered_and_the_default():
    assert profile_ids()[0] == "manual"
    assert isinstance(get_profile("manual"), ManualProfile)
    assert default_profile_id(None) == "manual"
    assert default_profile_id("not-installed") == "manual"


def test_keeps_every_track_in_source_order_unchanged():
    ext = sub(F.SRT, "de", external="Movie.de.srt")
    plan = plan_for(movie(), source(name="Movie_job.mkv"), external_subs=[ext])
    assert not plan.issues
    assert [(a.action, a.out_codec, str(a.out_layout)) for a in plan.audio] == [
        (AudioAction.COPY, C.TRUEHD, "7.1"), (AudioAction.COPY, C.AC3, "2.0"),
    ]  # fmt: skip
    assert [(a.default, a.commentary) for a in plan.audio] == [(True, False), (False, True)]
    assert [(s.language, s.title, s.forced) for s in plan.subs] == [
        ("en", "English", False), ("fr", "French", True), ("de", "", False),
    ]  # fmt: skip
    assert plan.resolution == "1920x1080" and plan.original_language == "en"


def test_overrides_exclude_reorder_and_edit():
    ov = Overrides(
        tracks={
            "id:1": TrackOverride(exclude=True),
            "id:11": TrackOverride(language="fr-CA", title="French (Canada)", flags={"forced": False, "default": True}),
        },
        order=["id:11", "id:2"],
    )
    plan = plan_for(movie(), source(name="Movie_job.mkv"), ov)
    assert [a.source.id for a in plan.audio] == [2]
    assert [s.source.id for s in plan.subs] == [11, 10]  # listed first, the rest in source order
    fr = plan.subs[0]
    assert (fr.language, fr.title, fr.forced, fr.default) == ("fr-CA", "French (Canada)", False, True)


def test_audio_track_ids_pick_and_order_audio():
    plan = plan_for(movie(), source(name="Movie_job.mkv"), Overrides(audio_track_ids=[2, 1]))
    assert [a.source.id for a in plan.audio] == [2, 1]


def test_only_missing_inputs_block():
    plan = plan_for(movie(), None)
    assert plan.blocked and [i.code for i in plan.issues] == ["input.no_video"]
    none = plan_for(movie(), source(name="Movie_job.mkv"), Overrides(audio_track_ids=[]))
    assert not none.blocked and [(i.severity, i.code) for i in none.issues] == [(Severity.WARN, "audio.none")]


def test_output_is_checked_against_the_plan():
    plan = plan_for(movie(), source(name="Movie_job.mkv"))
    profile = ManualProfile()
    assert profile.validate_output(plan, simulate_output(plan)) == []

    out = simulate_output(plan)
    out.audio[1].commentary = False
    out.subs[1].title = "Francais"
    out.subs.pop(0)
    codes = [i.code for i in profile.validate_output(plan, out)]
    assert "plan.audio" in codes and "plan.subs_count" in codes and "plan.subs" in codes
    assert profile.validate_release(out) == []  # no group rules
