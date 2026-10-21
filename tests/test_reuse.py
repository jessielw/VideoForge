"""Reusing finished files on a rerun, StaxRip-like: the offers by section, the user's keep, the work folder's
note of finished files (for any job on the source)."""

from __future__ import annotations

import os

from conftest import simulate_output
import pytest
from test_pipeline import APP, FakeRunner, make_plan, tools_called, video_job

from videoforge.core.job import JobState, JobStatus
from videoforge.core.pipeline.reuse import reuse_offers
from videoforge.core.pipeline.run import run_job
from videoforge.core.video.settings import Crop
from videoforge.core.workdir import FINISHED_NAME, finished_files, note_finished


@pytest.mark.parametrize("keep", [False, True])
def test_changed_output_is_neither_offered_nor_reused(profile, tmp_path, keep):
    plan = make_plan(tmp_path)
    job = video_job(plan, tmp_path)
    state = JobState()
    run(job, plan, profile, state)
    job.video_output.write_bytes(b"an interrupted replacement")
    assert "video" not in offers(job, plan, profile, state)
    if keep:
        state.keep = ["video"]  # even a choice made before the file changed
    assert "x264" in run(job, plan, profile, state)


def test_another_jobs_completed_output_is_not_current(profile, tmp_path):
    plan = make_plan(tmp_path)
    job = video_job(plan, tmp_path)
    state = JobState()
    run(job, plan, profile, state)
    job.video_output.write_bytes(b"another job's completed encode")
    note_finished(job.work_dir, "video", "other-settings", [job.video_output], 1)
    assert not offers(job, plan, profile, state)["video"].current
    assert "x264" in run(job, plan, profile, state)


@pytest.mark.parametrize("changed_field", ["size", "mtime"])
def test_output_identity_survives_serialization(tmp_path, changed_field):
    from videoforge.core.job import StepRecord
    from videoforge.core.plan_io import from_json, to_json

    output = tmp_path / "encoded.flac"
    output.write_bytes(b"complete")
    record = StepRecord("audio.1", "settings", [output])
    assert not record.outputs_match([output])  # legacy record
    record.capture_outputs()
    restored = from_json(StepRecord, to_json(record))
    assert restored.outputs_match([output])
    original = output.stat()
    output.write_bytes(b"replacement" if changed_field == "size" else b"replaced")
    # Test each stored field independently; rapid Windows writes can keep the same timestamp.
    mtime_ns = original.st_mtime_ns + (2_000_000_000 if changed_field == "mtime" else 0)
    os.utime(output, ns=(original.st_atime_ns, mtime_ns))
    assert not restored.outputs_match([output])


def run(job, plan, profile, state):
    runner = FakeRunner()
    result = run_job(job, plan, profile, APP, state=state, runner=runner, prober=lambda *_: simulate_output(plan))
    assert result.status is JobStatus.DONE, result.error
    return tools_called(runner)


def offers(job, plan, profile, state):
    return {o.id: o for o in reuse_offers(job, plan, profile, APP, state.steps)}


def test_offers_by_section_and_whether_settings_match(profile, tmp_path):
    plan = make_plan(tmp_path)
    job = video_job(plan, tmp_path)
    state = JobState()
    assert offers(job, plan, profile, state) == {}  # nothing made yet
    run(job, plan, profile, state)

    found = offers(job, plan, profile, state)
    assert list(found) == ["video", "audio.1", "audio.2"]
    assert all(o.current for o in found.values())
    assert found["video"].file == job.video_output and found["video"].label == "Video (x264)"
    assert found["audio.1"].label.startswith("Audio 1")
    assert found["video"].finished is not None

    job.video.crop = Crop(0, 140, 0, 140)  # new settings: the video is still offered, as made with others
    found = offers(job, plan, profile, state)
    assert not found["video"].current and found["audio.1"].current


def test_keep_reuses_a_video_made_with_other_settings(profile, tmp_path):
    plan = make_plan(tmp_path)
    job = video_job(plan, tmp_path)
    state = JobState()
    run(job, plan, profile, state)
    (job.work_dir / "Show.S01E01.mkv.ffindex").write_bytes(b"index")  # what the real one leaves
    job.video.crop = Crop(0, 140, 0, 140)

    state.keep = ["video"]
    # the script is written again (and read for its frame rate); no encode, the same mux
    assert run(job, plan, profile, state) == ["vspipe"]
    assert state.keep == []  # used up
    assert offers(job, plan, profile, state)["video"].current  # adopted: today's settings now

    job.video.crop = Crop(0, 138, 0, 138)  # not kept: made again, as always
    assert run(job, plan, profile, state) == ["vspipe", "x264", "mkvmerge"]


def test_a_new_job_on_the_source_finds_the_finished_files(profile, tmp_path):
    from videoforge.core.job import OutputPolicy

    plan = make_plan(tmp_path)
    job = video_job(plan, tmp_path)
    run(job, plan, profile, JobState())

    fresh = JobState()  # e.g. removed and added again, or another label: no records of its own
    found = offers(job, plan, profile, fresh)
    assert set(found) == {"video", "audio.1", "audio.2"} and all(o.current for o in found.values())
    fresh.keep = [s for o in found.values() for s in o.steps]
    job.output_policy = OutputPolicy.REPLACE  # replacing a different job's final output is explicit
    assert "x264" not in run(job, plan, profile, fresh)

    job.video_output.write_bytes(b"something else")  # changed since: not offered to a job without a record
    assert "video" not in offers(job, plan, profile, JobState())


def test_finished_files_note(tmp_path):
    a, b = tmp_path / "a.ac3", tmp_path / "b.ac3"
    a.write_bytes(b"aaa")
    b.write_bytes(b"bbb")
    note_finished(tmp_path, "audio.1", "f1", [a, tmp_path / "missing.ac3", tmp_path.parent / "elsewhere"], 2.5)
    note_finished(tmp_path, "audio.2", "f2", [b], 1.0)
    found = finished_files(tmp_path)
    assert set(found) == {"a.ac3", "b.ac3"}
    assert (found["a.ac3"].step, found["a.ac3"].fingerprint, found["a.ac3"].seconds) == ("audio.1", "f1", 2.5)
    b.write_bytes(b"bbbb")  # rewritten (an encode cut short): no longer the finished one
    assert set(finished_files(tmp_path)) == {"a.ac3"}
    (tmp_path / FINISHED_NAME).write_text("not json", encoding="utf-8")
    assert finished_files(tmp_path) == {}
    note_finished(tmp_path / "gone", "x", "f", [a], 0)  # never raises
