"""Templates: what applying one does to a job's settings."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from conftest import audio, sub

from videoforge.core.execute.mux import MuxSettings
from videoforge.core.job import JobSpec
from videoforge.core.models import (
    AudioAction,
    AudioCodec,
    AudioMatch,
    AudioRule,
    AudioSlot,
    JobInputs,
    Layout,
    OtherTracks,
    Overrides,
    SubFormat,
    SubRule,
    TemplateAudio,
    TemplateSubs,
    TrackOverride,
)
from videoforge.core.plan_io import from_json, to_json
from videoforge.core.template import (
    CropMode,
    Template,
    apply_audio,
    apply_subs,
    audio_matches,
    fit_audio,
    sub_matches,
)
from videoforge.core.video.settings import Crop, EncoderSettings, FilterCategory, FilterStep, VideoSettings


def spec(encode: Path | None = None) -> JobSpec:
    return JobSpec(
        JobInputs(Path("Show.S01E01.mkv"), encode=encode), "manual", video=VideoSettings(crop=Crop(0, 140, 0, 140))
    )


def test_pgs_compression_persists_in_templates_and_jobs():
    legacy = from_json(Template, {"mux": {"container": "mkv", "extra": ""}})
    assert legacy.mux.pgs_zlib is False
    template = Template(mux=MuxSettings(pgs_zlib=True))
    restored = from_json(Template, to_json(template))
    job = spec()
    restored.apply(job)
    assert from_json(JobSpec, to_json(job)).mux.pgs_zlib is True
    assert job.mux is not restored.mux


def test_keep_fixed_and_auto_crop():
    t = Template(
        VideoSettings(filters=[FilterStep(FilterCategory.CUSTOM, "Custom", "clip = clip")], crop=Crop(8, 0, 8, 0)),
        EncoderSettings(crf=16),
        MuxSettings("mp4", "-x"),
        qpf=False,
    )
    s = spec()
    t.apply(s)
    assert s.video.crop == Crop(0, 140, 0, 140) and s.video.filters[-1].script == "clip = clip" and not s.autocrop
    assert s.encoder.crf == 16 and s.mux == MuxSettings("mp4", "-x") and not s.qpf
    assert s.video is not t.video and s.encoder is not t.encoder and s.mux is not t.mux  # copies

    t.crop_mode = CropMode.FIXED
    t.apply(s)
    assert s.video.crop == Crop(8, 0, 8, 0) and s.video.crop is not t.video.crop

    t.crop_mode = CropMode.AUTO
    t.apply(s)
    assert s.autocrop
    reuses = spec(encode=Path("Show.S01E01.264"))
    t.apply(reuses)
    assert not reuses.autocrop  # nothing to crop: the video isn't encoded here


def test_audio_slots_go_to_the_source_tracks_by_position():
    tracks = [
        audio(AudioCodec.TRUEHD, "7.1", "en", index=0),
        audio(AudioCodec.AC3, "5.1", "en", index=1),
        audio(AudioCodec.AAC, "2.0", "en", index=2, commentary=True),
    ]
    ddp = TrackOverride(action=AudioAction.DDP, layout=Layout.parse("5.1"), bitrate_kbps=640, language="fr")
    slots = TemplateAudio(
        slots=[AudioSlot(TrackOverride(title="TrueHD 7.1"), [ddp]), AudioSlot(TrackOverride(exclude=True))]
    )
    before = Overrides(
        tracks={
            "id:1": TrackOverride(bitrate_kbps=9),
            "id:1+1": TrackOverride(),
            "id:10": TrackOverride(title="Subs"),
            "ext:extra.ac3": TrackOverride(title="Mine"),
        },
        copies=["id:1+1", "id:1+2"],
        order=["id:2", "id:10", "id:1"],
        audio_track_ids=[1],
    )

    out = apply_audio(before, slots, tracks)
    assert out.tracks["id:1"] == TrackOverride(title="TrueHD 7.1")  # the job's earlier choice is replaced
    assert out.copies == ["id:1+1"] and out.tracks["id:1+1"].action is AudioAction.DDP
    assert (
        out.tracks["id:1+1"].language is None and ddp.language == "fr"
    )  # language is per source; the slot is untouched
    assert out.tracks["id:2"].exclude and "id:3" not in out.tracks  # a track past the slots: as the profile decides
    assert out.tracks["id:10"].title == "Subs" and out.tracks["ext:extra.ac3"].title == "Mine"  # subs, added files kept
    assert out.order == ["id:10"] and out.audio_track_ids is None

    slots.others = OtherTracks.EXCLUDE
    assert apply_audio(Overrides(), slots, tracks).tracks["id:3"] == TrackOverride(exclude=True)
    many = TemplateAudio(slots=[AudioSlot(TrackOverride(title=str(n))) for n in range(5)])
    assert sorted(apply_audio(Overrides(), many, tracks[:1]).tracks) == ["id:1"]  # extra slots are ignored


def test_audio_slots_fit_each_track():
    """A slot asks for at most what its track has: no upmix, Atmos only from Atmos, a bitrate the encode
    takes for the layout. A lowered layout takes the default bitrate with it."""
    stereo, surround = audio(AudioCodec.AC3, "2.0"), audio(AudioCodec.DTS_HD_MA, "5.0")
    atmos, truehd = audio(AudioCodec.TRUEHD, "7.1", atmos=True), audio(AudioCodec.TRUEHD, "7.1")
    ddp51 = TrackOverride(action=AudioAction.DDP, layout=Layout.parse("5.1"), bitrate_kbps=640, title="DDP")

    assert fit_audio(ddp51, stereo) == TrackOverride(action=AudioAction.DDP, title="DDP")  # the default 2.0, 256
    assert fit_audio(ddp51, surround) == ddp51  # DDP makes 5.1 from 5.0
    assert fit_audio(ddp51, truehd) == ddp51 and fit_audio(ddp51, truehd) is not ddp51

    to_atmos = TrackOverride(action=AudioAction.ATMOS, bitrate_kbps=1024, options={"atmos_mode": "bluray"})
    assert fit_audio(to_atmos, atmos) == to_atmos
    assert fit_audio(to_atmos, truehd) == TrackOverride(action=AudioAction.DDP, options={"atmos_mode": "bluray"})

    opus = TrackOverride(action=AudioAction.OPUS, bitrate_kbps=600)
    assert fit_audio(opus, stereo).bitrate_kbps is None  # over 256 per channel
    assert fit_audio(opus, truehd).bitrate_kbps == 600
    copied = TrackOverride(layout=Layout.parse("7.1"), title="Copy")
    assert fit_audio(copied, stereo) == copied  # nothing to fit on a copy


def test_sub_rules_match_language_format_and_traits():
    forced_by_title = sub(SubFormat.PGS, "en", "English (Forced)")
    sdh = sub(SubFormat.SRT, "en-US", "English SDH", index=1)
    latam = sub(SubFormat.SRT, "es-419", index=2)
    assert sub_matches(SubRule(languages=["eng"], forced=True), forced_by_title)  # "eng" is "en"; forced by its title
    assert not sub_matches(SubRule(languages=["en"], forced=False), forced_by_title)
    assert sub_matches(SubRule(languages=["English"], hearing_impaired=True), sdh)  # "en" matches en-US
    assert not sub_matches(SubRule(formats=[SubFormat.PGS]), sdh)
    assert sub_matches(SubRule(languages=["es"]), latam) and sub_matches(SubRule(languages=["es-419"]), latam)
    assert not sub_matches(SubRule(languages=["es-ES"]), latam)  # a region matches only itself
    assert sub_matches(SubRule(), latam)  # an empty rule matches anything


def test_sub_rules_keep_order_and_flag_the_tracks():
    """Forced English first and default, then full English (SDH left out), nothing else; an added file
    is matched like a source track."""
    full, sdh = sub(SubFormat.PGS, "en", index=0), sub(SubFormat.PGS, "en", "SDH", index=1)
    french, forced = sub(SubFormat.PGS, "fr", index=2), sub(SubFormat.PGS, "en", index=3, forced=True)
    added = sub(SubFormat.SRT, "en", external="Show.en.forced.srt", forced=True, tags=frozenset({"forced"}))
    rules = TemplateSubs(
        [
            SubRule(
                languages=["en"],
                forced=True,
                track=TrackOverride(flags={"default": True}, title="Forced", language="de"),
            ),
            SubRule(languages=["en"], hearing_impaired=True, track=TrackOverride(exclude=True)),
            SubRule(languages=["en"]),
        ]
    )
    before = Overrides(
        tracks={"id:10": TrackOverride(title="old"), "id:1": TrackOverride(title="audio")},
        order=["id:2", "id:13", "id:1"],
    )

    out = apply_subs(before, rules, [full, sdh, french, forced, added])
    assert out.tracks["id:13"] == TrackOverride(title="Forced", flags={"default": True})  # no language: per source
    assert out.tracks["ext:Show.en.forced.srt"] == TrackOverride(
        title="Forced", flags={"default": False}
    )  # one default
    assert out.tracks["id:11"].exclude and out.tracks["id:12"].exclude  # SDH by rule; French by `others`
    assert out.tracks["id:10"] == TrackOverride(flags={"default": False})  # the earlier title is replaced
    assert out.tracks["id:1"].title == "audio"  # audio is kept
    assert out.order == ["id:2", "id:1", "id:13", "ext:Show.en.forced.srt", "id:10"]  # audio's order, then by rule

    rules.others = OtherTracks.KEEP
    rules.rules[0].track.flags = {}
    out = apply_subs(Overrides(), rules, [full, sdh, french, forced])
    assert "id:12" not in out.tracks and "id:10" not in out.tracks  # kept as they are; no default set, none cleared
    assert out.order == ["id:13", "id:10", "id:12"]


def test_template_carries_its_subs_to_the_job():
    t = Template(subs=TemplateSubs([SubRule(languages=["en"])]))
    s = spec()
    t.apply(s)
    assert s.subs_template == t.subs and s.subs_template is not t.subs
    Template().apply(s)
    assert s.subs_template == t.subs  # a template without subs leaves the pending ones


def rules(*r: AudioRule, others: OtherTracks = OtherTracks.EXCLUDE) -> TemplateAudio:
    return TemplateAudio(AudioMatch.RULES, rules=list(r), others=others)


def test_audio_rules_match_language_codec_channels_and_traits():
    truehd = audio(AudioCodec.TRUEHD, "7.1", "en-US")
    stereo = audio(AudioCodec.AAC, "2.0", "en", title="Director's Commentary", index=1)
    ad = audio(AudioCodec.AC3, "2.0", "en", title="English AD", index=2)
    ja = audio(AudioCodec.FLAC, "2.0", "ja", index=3)
    assert audio_matches(AudioRule(languages=["English"]), truehd)  # a name; "en" matches en-US
    assert audio_matches(AudioRule(codecs=[AudioCodec.TRUEHD, AudioCodec.FLAC], min_channels=6), truehd)
    assert not audio_matches(AudioRule(min_channels=6), stereo) and audio_matches(AudioRule(max_channels=2), stereo)
    assert not audio_matches(AudioRule(max_channels=6), truehd)
    assert audio_matches(AudioRule(commentary=True), stereo) and not audio_matches(AudioRule(commentary=True), ad)
    assert audio_matches(AudioRule(visual_impaired=True), ad)  # "AD" in the title
    assert not audio_matches(AudioRule(visual_impaired=True), audio(AudioCodec.AC3, "2.0", title="Headroom"))
    assert audio_matches(AudioRule(original=True), ja, "ja") and not audio_matches(
        AudioRule(original=True), truehd, "ja"
    )
    assert audio_matches(AudioRule(original=False), truehd, "ja")
    assert not audio_matches(AudioRule(original=True), ja, None)  # no original known: nothing is it
    assert audio_matches(AudioRule(), ja)  # an empty rule matches anything


def test_audio_rules_pick_tracks_whatever_their_order():
    """The first English track is copied and default, Japanese goes to FLAC, commentary is left out,
    nothing else: two sources with the tracks in another order give the same output."""
    template = rules(
        AudioRule(commentary=True, track=TrackOverride(exclude=True)),
        AudioRule(languages=["en"], first_only=True, track=TrackOverride(title="English", flags={"default": True})),
        AudioRule(languages=["ja"], track=TrackOverride(action=AudioAction.FLAC, flags={"default": True})),
    )
    a = [
        audio(AudioCodec.TRUEHD, "7.1", "en", index=0),
        audio(AudioCodec.AC3, "5.1", "en", index=1),
        audio(AudioCodec.AAC, "2.0", "en", title="Commentary", index=2),
        audio(AudioCodec.FLAC, "2.0", "ja", index=3),
    ]
    out = apply_audio(Overrides(), template, a)
    assert out.tracks["id:1"] == TrackOverride(title="English", flags={"default": True})
    assert out.tracks["id:2"].exclude and out.tracks["id:3"].exclude  # the 2nd English: no rule left; commentary
    assert out.tracks["id:4"] == TrackOverride(action=AudioAction.FLAC, flags={"default": False})  # one default
    assert out.order == ["id:1", "id:4"]

    b = [
        replace(a[3], id=1, index=0),
        replace(a[2], id=2, index=1),
        replace(a[0], id=3, index=2),
        replace(a[1], id=4, index=3),
    ]
    out = apply_audio(Overrides(), template, b)
    assert out.order == ["id:3", "id:1"] and out.tracks["id:3"].title == "English" and out.tracks["id:4"].exclude


def test_audio_rules_extras_others_and_earlier_choices():
    template = rules(
        AudioRule(
            languages=["en"],
            track=TrackOverride(title="Main"),
            extra=[
                TrackOverride(
                    action=AudioAction.DDP, layout=Layout.parse("5.1"), bitrate_kbps=640, flags={"default": True}
                )
            ],
        ),
        others=OtherTracks.KEEP,
    )
    a = [
        audio(AudioCodec.FLAC, "2.0", "fr", index=0, default=True),
        audio(AudioCodec.TRUEHD, "7.1", "en", index=1),
        audio(AudioCodec.AC3, "2.0", "en", index=2),
    ]
    before = Overrides(
        tracks={"id:1": TrackOverride(title="old"), "id:2+1": TrackOverride(), "id:10": TrackOverride(title="Subs")},
        copies=["id:2+1", "id:2+2"],
        order=["id:10", "id:3", "id:1"],
        audio_track_ids=[1],
    )
    out = apply_audio(before, template, a)
    assert out.copies == ["id:2+1", "id:3+1"]  # every match gets the rule (no first_only), each with its extra
    assert out.tracks["id:2+1"].layout == Layout.parse("5.1") and out.tracks["id:2+1"].bitrate_kbps == 640
    assert out.tracks["id:3+1"] == TrackOverride(action=AudioAction.DDP, flags={"default": False})  # fitted to 2.0
    assert out.tracks["id:2+1"].flags == {"default": True}  # the first output a rule gives default keeps it
    assert out.tracks["id:1"] == TrackOverride(flags={"default": False})  # unmatched, kept last; its old title replaced
    assert out.tracks["id:10"].title == "Subs" and out.audio_track_ids is None
    assert out.order == ["id:10", "id:2", "id:2+1", "id:3", "id:3+1", "id:1"]


def test_template_audio_dispatches_on_its_mode():
    a = [audio(AudioCodec.AC3, "5.1", "en", index=0), audio(AudioCodec.AC3, "5.1", "ja", index=1)]
    both = TemplateAudio(
        AudioMatch.POSITION,
        slots=[AudioSlot(TrackOverride(title="slot"))],
        rules=[AudioRule(languages=["ja"], track=TrackOverride(title="rule"))],
    )
    assert apply_audio(Overrides(), both, a).tracks == {"id:1": TrackOverride(title="slot")}
    both.mode, both.others = AudioMatch.RULES, OtherTracks.EXCLUDE
    assert apply_audio(Overrides(), both, a).tracks == {
        "id:1": TrackOverride(exclude=True),
        "id:2": TrackOverride(title="rule"),
    }
