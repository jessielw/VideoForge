"""Job history: one JSON record per output in app data; working folders next to the source."""

from __future__ import annotations

from conftest import audio, plan_for, simulate_output, source
from test_pipeline import APP, FakeRunner, make_plan

from videoforge.core.history import JobHistory
from videoforge.core.job import JobResult, JobStatus
from videoforge.core.models import AudioCodec as C, TrackOverride
from videoforge.core.pipeline.run import run_plan
from videoforge.core.workdir import remove_work_dir, work_dir


def test_record_round_trips_and_is_keyed_by_output(profile, tmp_path):
    plan = make_plan(tmp_path)
    plan.overrides.tracks["id:3"] = TrackOverride(flags={"forced": True})
    result = run_plan(
        plan, tmp_path / "out", profile, APP, runner=FakeRunner(), prober=lambda *_: simulate_output(plan)
    )
    history = JobHistory(tmp_path / "history")

    history.record(result)
    rec = history.find(tmp_path / "out" / "Show.S01E01.mkv")
    assert rec is not None and rec.status is JobStatus.DONE
    assert rec.output == result.output and rec.work_dir == result.work_dir
    assert rec.encoded_audio == result.encoded_audio  # int keys survive JSON
    assert rec.plan.overrides.tracks["id:3"].flags == {"forced": True}
    assert rec.plan.profile == "manual"

    history.record(result)  # a re-run replaces the record
    assert len(list((tmp_path / "history").glob("*.json"))) == 1
    assert history.find(tmp_path / "out" / "Other.mkv") is None


def test_only_outputs_are_recorded(tmp_path):
    plan = plan_for(source([audio(C.AC3, "5.1")], name="A.mkv"), None)
    history = JobHistory(tmp_path / "history")
    assert history.record(JobResult(plan, JobStatus.FAILED, error="boom")) is None
    assert history.record(JobResult(plan, JobStatus.SKIPPED)) is None
    assert not (tmp_path / "history").exists()


def test_unreadable_record_is_ignored(profile, tmp_path):
    plan = make_plan(tmp_path)
    result = run_plan(
        plan, tmp_path / "out", profile, APP, runner=FakeRunner(), prober=lambda *_: simulate_output(plan)
    )
    history = JobHistory(tmp_path / "history")
    history.record(result)
    (path,) = (tmp_path / "history").glob("*.json")
    path.write_text("{not json", encoding="utf-8")
    assert history.find(result.output) is None


def test_work_dir_is_next_to_the_source_and_separate_from_staxrip(tmp_path):
    src = tmp_path / "Show.S01E01.mkv"
    assert work_dir(src) == tmp_path / "Show.S01E01.mkv_tmp"  # StaxRip's is Show.S01E01.mkv_temp
    assert remove_work_dir(src) is False
    (work_dir(src) / "sub").mkdir(parents=True)
    (work_dir(src) / "sub" / "a.ec3").write_bytes(b"x")
    assert remove_work_dir(src) is True and not work_dir(src).exists()
