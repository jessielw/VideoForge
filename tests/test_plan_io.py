"""plan.json round trips: what the CLI writes, the GUI and `videoforge run` read back unchanged."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import audio, plan_for, source, sub

from videoforge.core.models import AudioCodec as C
from videoforge.core.models import Overrides, TrackOverride, VideoInfo
from videoforge.core.models import SubFormat as F
from videoforge.core.plan_io import PlanFormatError, dump_plans, load_plans, plan_from_dict, plan_to_dict


def aot_plan():
    src = source(
        [audio(C.FLAC, "2.0", "ja", index=0), audio(C.TRUEHD, "5.1", "en", index=1), audio(C.AC3, "5.1", "en", index=2)],
        [
            sub(F.PGS, "en", "English", index=0, elements=604),
            sub(F.ASS, "en", "English (ASS SDH Dub)", index=1),
            sub(F.ASS, "fr", "French", index=2),
            sub(F.SRT, "en", external=r"D:\media\subs\Show.S01E01.NF.en.synced.srt"),
            sub(F.SRT, "en", "English (ASS Foreign)", external=r"D:\media\subs\Show_track3_[eng].srt", forced=True,
                tags=frozenset({"forced", "sdh"})),
        ],
        name="Show.S01E01.mkv",
    )
    src.video = VideoInfo(1920, 1080, start_ms=838, default_duration_ns=41708333)
    external = src.subs[3:]
    src.subs[3:] = []
    overrides = Overrides(
        original_language="ja",
        audio_track_ids=[1, 2],
        tracks={"id:12": TrackOverride(language="fr-CA", title="French (Canada)", flags={"original": False})},
        order=["id:12", "ext:Show_track3_[eng].srt"],
    )
    encode = source(name="Show.S01E01_job.h264")
    return plan_for(src, encode, overrides, external_subs=external, chapters=Path(r"D:\media\qpf_chapters.txt"))


def test_round_trip_is_lossless():
    plan = aot_plan()
    assert plan.audio and plan.subs and plan.issues
    data = json.loads(json.dumps(plan_to_dict(plan)))
    assert plan_from_dict(data) == plan


def test_file_round_trip(tmp_path):
    plans = [aot_plan(), aot_plan()]
    out = tmp_path / "plan.json"
    dump_plans(plans, out)
    assert load_plans(out) == plans
    assert "Show_track3_[eng].srt" in out.read_text(encoding="utf-8")


def test_json_is_readable():
    data = plan_to_dict(aot_plan())
    assert data["audio"][1]["out_layout"] == "5.1"
    assert data["audio"][0]["action"] == "copy"
    assert data["subs"][0]["title"] == "French (Canada)"
    assert data["overrides"]["order"] == ["id:12", "ext:Show_track3_[eng].srt"]
    assert data["source"]["video"]["default_duration_ns"] == 41708333
    assert data["overrides"]["tracks"]["id:12"]["language"] == "fr-CA"


def test_missing_fields_use_defaults():
    data = plan_to_dict(aot_plan())
    del data["overrides"]
    del data["source"]["video"]["default_duration_ns"]
    plan = plan_from_dict(data)
    assert plan.overrides == Overrides()
    assert plan.source.video.default_duration_ns is None


def test_v1_file_is_upgraded(tmp_path):
    """v1: forced/sdh/dub were SubOverride fields under overrides.subs, and profile could be missing."""
    data = plan_to_dict(aot_plan())
    del data["profile"]
    data["overrides"] = {
        "original_language": "ja",
        "audio_track_ids": [1, 2],
        "subs": {"id:11": {"exclude": None, "language": "fr-CA", "forced": False, "sdh": None, "dub": True}},
    }
    out = tmp_path / "plan.json"
    out.write_text(json.dumps({"version": 1, "plans": [data]}), encoding="utf-8")
    (plan,) = load_plans(out)
    assert plan.profile == ""  # v1 had no profile; the caller picks the default
    assert plan.overrides.tracks == {"id:11": TrackOverride(language="fr-CA", flags={"forced": False, "dub": True})}
    assert plan.overrides.audio_track_ids == [1, 2]


def test_wrong_version_rejected(tmp_path):
    out = tmp_path / "plan.json"
    out.write_text('{"version": 99, "plans": []}', encoding="utf-8")
    with pytest.raises(PlanFormatError):
        load_plans(out)
