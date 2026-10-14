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
from videoforge.core.template import CropMode, Template, apply_audio
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
