"""Templates: what applying one does to a job's settings."""

from __future__ import annotations

from pathlib import Path

from conftest import audio

from videoforge.core.execute.mux import MuxSettings
from videoforge.core.job import JobSpec
from videoforge.core.models import (
    AudioAction,
    AudioCodec,
    AudioSlot,
    JobInputs,
    Layout,
    OtherAudio,
    Overrides,
    TemplateAudio,
    TrackOverride,
)
from videoforge.core.template import CropMode, Template, apply_audio, fit_audio
from videoforge.core.video.settings import Crop, EncoderSettings, VideoSettings


def spec(encode: Path | None = None) -> JobSpec:
    return JobSpec(JobInputs(Path("Show.S01E01.mkv"), encode=encode), "manual",
                   video=VideoSettings(crop=Crop(0, 140, 0, 140)))


def test_keep_fixed_and_auto_crop():
    t = Template(VideoSettings(filters="clip = clip", crop=Crop(8, 0, 8, 0)), EncoderSettings(crf=16),
                 MuxSettings("mp4", "-x"), qpf=False)
    s = spec()
    t.apply(s)
    assert s.video.crop == Crop(0, 140, 0, 140) and s.video.filters == "clip = clip" and not s.autocrop
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
    tracks = [audio(AudioCodec.TRUEHD, "7.1", "en", index=0), audio(AudioCodec.AC3, "5.1", "en", index=1),
              audio(AudioCodec.AAC, "2.0", "en", index=2, commentary=True)]
    ddp = TrackOverride(action=AudioAction.DDP, layout=Layout.parse("5.1"), bitrate_kbps=640, language="fr")
    slots = TemplateAudio([AudioSlot(TrackOverride(title="TrueHD 7.1"), [ddp]), AudioSlot(TrackOverride(exclude=True))])
    before = Overrides(tracks={"id:1": TrackOverride(bitrate_kbps=9), "id:1+1": TrackOverride(), "id:10": TrackOverride(title="Subs"),
                               "ext:extra.ac3": TrackOverride(title="Mine")},
                       copies=["id:1+1", "id:1+2"], order=["id:2", "id:10", "id:1"], audio_track_ids=[1])

    out = apply_audio(before, slots, tracks)
    assert out.tracks["id:1"] == TrackOverride(title="TrueHD 7.1")  # the job's earlier choice is replaced
    assert out.copies == ["id:1+1"] and out.tracks["id:1+1"].action is AudioAction.DDP
    assert out.tracks["id:1+1"].language is None and ddp.language == "fr"  # language is per source; the slot is untouched
    assert out.tracks["id:2"].exclude and "id:3" not in out.tracks  # a track past the slots: as the profile decides
    assert out.tracks["id:10"].title == "Subs" and out.tracks["ext:extra.ac3"].title == "Mine"  # subs, added files kept
    assert out.order == ["id:10"] and out.audio_track_ids is None

    slots.others = OtherAudio.EXCLUDE
    assert apply_audio(Overrides(), slots, tracks).tracks["id:3"] == TrackOverride(exclude=True)
    many = TemplateAudio([AudioSlot(TrackOverride(title=str(n))) for n in range(5)])
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
