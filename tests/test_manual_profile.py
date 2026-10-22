"""The built-in manual profile: every track in source order, shaped only by the user's overrides."""

from __future__ import annotations

from pathlib import Path

from conftest import audio, plan_for, simulate_output, source, sub
import pytest

from videoforge.core.jobs import ProbedInputs
from videoforge.core.models import (
    AudioAction,
    AudioCodec as C,
    JobInputs,
    Layout,
    Overrides,
    Severity,
    SubFormat as F,
    TrackOverride,
)
from videoforge.profiles import default_profile_id, get_profile, profile_ids
from videoforge.profiles.manual import ManualProfile

NORMALIZE_OFF = {"normalize": "", "loudnorm_i": "-24", "loudnorm_tp": "-2", "loudnorm_lra": "7"}


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


def test_original_language_guess():
    """The original language: the track flagged original, else the default one (a dub placed first),
    else the first planned track."""
    dub_first = [audio(C.FLAC, "5.1", "ja", index=0), audio(C.EAC3, "5.1", "en", index=1, default=True)]
    assert plan_for(source(dub_first), source(name="enc.mkv")).original_language == "en"
    dub_first[1].default, dub_first[0].original = False, True
    assert plan_for(source(dub_first), source(name="enc.mkv")).original_language == "ja"
    dub_first[0].original = False
    assert plan_for(source(dub_first), source(name="enc.mkv")).original_language == "ja"  # no flags: the first


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


def test_audio_titles_inherit_each_source_and_custom_titles_survive_encoding():
    tracks = [
        audio(C.TRUEHD, "7.1", "en", index=0, title="Original audio"),
        audio(C.AC3, "2.0", "en", index=1, title="Commentary"),
    ]
    original = plan_for(source(tracks), source(name="Movie_job.mkv"))
    assert [a.title for a in original.audio] == ["Original audio", "Commentary"]
    overrides = Overrides(tracks={"id:1": TrackOverride(action=AudioAction.DDP, title="Bob", layout=Layout(5, 1))})
    custom = plan_for(source(tracks), source(name="Movie_job.mkv"), overrides)
    assert [a.title for a in custom.audio] == ["Bob", "Commentary"]
    assert custom.audio[0].action is AudioAction.DDP


def encoded(tracks: list, **overrides: TrackOverride):
    """The plan's audio for these source tracks, with overrides keyed by "id:<n>" as id_<n>."""
    ov = Overrides(tracks={k.replace("_", ":"): v for k, v in overrides.items()})
    return plan_for(source(tracks), source(name="Movie_job.mkv"), ov)


def test_audio_encodes_with_default_layouts_and_bitrates():
    tracks = [
        audio(C.TRUEHD, "7.1", index=0, atmos=True),
        audio(C.DTS_HD_MA, "5.0", index=1),
        audio(C.FLAC, "5.1", index=2),
        audio(C.AC3, "2.0", index=3),
    ]
    plan = encoded(
        tracks,
        id_1=TrackOverride(action=AudioAction.ATMOS),
        id_2=TrackOverride(action=AudioAction.DDP),
        id_3=TrackOverride(action=AudioAction.AAC),
        id_4=TrackOverride(action=AudioAction.AAC, bitrate_kbps=160),
    )
    assert not plan.issues
    got = [(a.action, a.out_codec, str(a.out_layout), a.out_atmos, a.bitrate_kbps, a.upmix_50) for a in plan.audio]
    assert got == [
        (AudioAction.ATMOS, C.EAC3, "5.1", True, 768, False),
        (AudioAction.DDP, C.EAC3, "5.1", False, 640, True),  # 5.0 gets the LFE upmix
        (AudioAction.AAC, C.AAC, "2.0", False, None, False),  # AAC defaults to stereo, quality mode
        (AudioAction.AAC, C.AAC, "2.0", False, 160, False),
    ]


def test_audio_encode_overrides_layout_and_bitrate():
    plan = encoded(
        [audio(C.TRUEHD, "7.1", index=0)],
        id_1=TrackOverride(action=AudioAction.DDP, layout=Layout.parse("2.0"), bitrate_kbps=224),
    )
    a = plan.audio[0]
    assert (str(a.out_layout), a.bitrate_kbps) == ("2.0", 224)
    assert (
        str(encoded([audio(C.TRUEHD, "7.1", index=0)], id_1=TrackOverride(action=AudioAction.DDP)).audio[0].out_layout)
        == "7.1"
    )


def test_ddp_bluray_defaults_and_mode_validation():
    tracks = [audio(C.TRUEHD, "7.1", index=0)]
    plan = encoded(tracks, id_1=TrackOverride(action=AudioAction.DDP, options={"ddp_mode": "bluray"}))
    assert not plan.issues
    assert plan.audio[0].out_layout == Layout(7, 1)
    assert plan.audio[0].bitrate_kbps == 1280
    assert plan.audio[0].options["ddp_mode"] == "bluray"
    standard = encoded(tracks, id_1=TrackOverride(action=AudioAction.DDP))
    assert standard.audio[0].options["ddp_mode"] == "standard"
    assert standard.audio[0].bitrate_kbps == 1024
    bad = encoded(tracks, id_1=TrackOverride(action=AudioAction.DDP, options={"ddp_mode": "auto"}))
    assert bad.blocked and [i.code for i in bad.issues] == ["audio.option"]


@pytest.mark.parametrize("source_layout, output_layout", [("5.0", None), ("5.1", None), ("2.0", None), ("7.1", "5.1")])
def test_ddp_bluray_blocks_incompatible_layouts(source_layout, output_layout):
    plan = encoded(
        [audio(C.TRUEHD, source_layout, index=0)],
        id_1=TrackOverride(
            action=AudioAction.DDP,
            layout=Layout.parse(output_layout) if output_layout else None,
            options={"ddp_mode": "bluray"},
        ),
    )
    assert plan.blocked
    assert any(i.code in {"audio.upmix", "audio.layout"} for i in plan.issues)


def test_impossible_audio_encodes_block():
    stereo = [audio(C.AC3, "2.0", index=0)]
    assert [i.code for i in encoded(stereo, id_1=TrackOverride(action=AudioAction.ATMOS)).issues] == [
        "audio.atmos_source"
    ]
    upmix = encoded(stereo, id_1=TrackOverride(action=AudioAction.DDP, layout=Layout.parse("5.1")))
    assert [i.code for i in upmix.issues] == ["audio.upmix"] and upmix.blocked
    bad = encoded(stereo, id_1=TrackOverride(action=AudioAction.AAC, layout=Layout.parse("7.1")))
    assert [i.code for i in bad.issues] == ["audio.layout"]


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


def test_ffmpeg_encodes_keep_the_layout_they_can_and_pick_bitrates():
    tracks = [
        audio(C.TRUEHD, "7.1", index=0),
        audio(C.DTS_HD_MA, "5.0", index=1),
        audio(C.LPCM, "6.1", index=2),
        audio(C.FLAC, "2.0", index=3),
        audio(C.TRUEHD, "7.1", index=4),
    ]
    plan = encoded(
        tracks,
        id_1=TrackOverride(action=AudioAction.FLAC),
        id_2=TrackOverride(action=AudioAction.OPUS),
        id_3=TrackOverride(action=AudioAction.AC3),
        id_4=TrackOverride(action=AudioAction.AAC_FFMPEG),
        id_5=TrackOverride(action=AudioAction.EAC3),
    )
    assert not plan.issues
    got = [(a.action, a.out_codec, str(a.out_layout), a.bitrate_kbps) for a in plan.audio]
    assert got == [
        (AudioAction.FLAC, C.FLAC, "7.1", None),  # lossless: no bitrate
        (AudioAction.OPUS, C.OPUS, "5.0", 384),  # kept as is; 5 channels take the 5.1 rate
        (AudioAction.AC3, C.AC3, "5.1", 640),  # AC-3 tops out at 5.1
        (AudioAction.AAC_FFMPEG, C.AAC, "2.0", 192),
        (AudioAction.EAC3, C.EAC3, "5.1", 640),
    ]


def test_ffmpeg_encode_bitrates_are_checked():
    stereo = [audio(C.FLAC, "2.0", index=0)]
    ac3 = encoded(stereo, id_1=TrackOverride(action=AudioAction.AC3, bitrate_kbps=700))
    assert [i.code for i in ac3.issues] == ["audio.bitrate"] and ac3.blocked
    opus = encoded(stereo, id_1=TrackOverride(action=AudioAction.OPUS, bitrate_kbps=600))
    assert "256 kb/s per channel" in opus.issues[0].message
    assert not encoded(stereo, id_1=TrackOverride(action=AudioAction.AC3, bitrate_kbps=192)).issues
    flac = encoded(stereo, id_1=TrackOverride(action=AudioAction.FLAC, bitrate_kbps=999))  # ignored
    assert not flac.issues and flac.audio[0].bitrate_kbps is None


def test_added_audio_files_join_the_tracks():
    extra = audio(C.AC3, "2.0", "und", index=0, title="Commentary")
    extra.external_path = Path("Commentary.ac3")
    plan = plan_for(source([audio(C.FLAC, "2.0", "ja", index=0)]), source(name="E.mkv"), external_audio=[extra])
    assert [(a.source.external_path, a.action) for a in plan.audio] == [
        (None, AudioAction.COPY),
        (Path("Commentary.ac3"), AudioAction.COPY),
    ]
    assert [i.code for i in plan.issues] == ["audio.language"]
    ov = Overrides(
        order=["ext:Commentary.ac3", "id:1"],
        tracks={"ext:Commentary.ac3": TrackOverride(language="en", action=AudioAction.OPUS)},
    )
    plan = plan_for(source([audio(C.FLAC, "2.0", "ja", index=0)]), source(name="E.mkv"), ov, external_audio=[extra])
    assert not plan.issues
    assert [(a.language, a.action) for a in plan.audio] == [("en", AudioAction.OPUS), ("ja", AudioAction.COPY)]


def test_encode_options_default_and_are_checked():
    stereo = [audio(C.FLAC, "2.0", index=0)]
    plan = encoded(stereo, id_1=TrackOverride(action=AudioAction.OPUS, options={"vbr": "constrained", "nope": "x"}))
    assert plan.audio[0].options == {
        "vbr": "constrained",
        "application": "audio",
        "complexity": "10",
        **NORMALIZE_OFF,
        "extra": "",
    }
    bad = encoded(stereo, id_1=TrackOverride(action=AudioAction.FLAC, options={"level": "13"}))
    assert [i.code for i in bad.issues] == ["audio.option"] and "0 to 12" in bad.issues[0].message
    assert bad.audio[0].options["level"] == "8"  # the default stands in
    quotes = encoded(stereo, id_1=TrackOverride(action=AudioAction.AC3, options={"extra": '-metadata title="x'}))
    assert [i.code for i in quotes.issues] == ["audio.option"]
    loud = encoded(
        stereo, id_1=TrackOverride(action=AudioAction.FLAC, options={"loudnorm_tp": "-1.5", "loudnorm_i": "3"})
    )
    assert [i.code for i in loud.issues] == ["audio.option"] and "-70 to -5" in loud.issues[0].message
    assert loud.audio[0].options["loudnorm_tp"] == "-1.5" and loud.audio[0].options["loudnorm_i"] == "-24"


def test_encode_options_take_the_profiles_defaults():
    class Bluray(ManualProfile):
        id = "bluray-test"

        def audio_settings(self):
            from videoforge.core.execute.audio import AudioSettings

            return AudioSettings(atmos_mode="bluray", qaac_tvbr=91)

    src = source([audio(C.TRUEHD, "7.1", "en", atmos=True, index=0), audio(C.FLAC, "2.0", "en", index=1)])
    ov = Overrides(
        tracks={
            "id:1": TrackOverride(action=AudioAction.ATMOS),
            "id:2": TrackOverride(action=AudioAction.AAC, options={"quality": "200"}),
        }
    )
    inputs = JobInputs(source=Path(src.name), encode=Path("E.mkv"))
    plan = Bluray().plan(ProbedInputs(inputs, src, source(name="E.mkv"), []), None, ov)
    atmos, aac = plan.audio
    assert atmos.options["atmos_mode"] == "bluray" and atmos.options["drc_line"] == ""
    assert aac.options["quality"] == "91"  # 200 is out of range, so the profile's default stands in
    assert [i.code for i in plan.issues] == ["audio.option"]
