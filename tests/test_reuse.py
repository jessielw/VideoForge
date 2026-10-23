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
    note_finished(job.job_dir, "video", "other-settings", [job.video_output], 1)
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


def variant(job, plan, label, **changes):
    """Another job on the source, as Duplicate makes it: its own label (so its own folder and output)."""
    from copy import deepcopy
    from dataclasses import replace

    other = replace(deepcopy(job), label=label, **changes)
    other_plan = deepcopy(plan)
    other_plan.encode_path = other.video_output
    return other, other_plan


def run_logged(job, plan, profile, state):
    runner, lines = FakeRunner(), []
    result = run_job(
        job, plan, profile, APP, state=state, runner=runner, log=lines.append, prober=lambda *_: simulate_output(plan)
    )
    assert result.status is JobStatus.DONE, result.error
    return tools_called(runner), lines


def test_jobs_on_one_source_keep_their_own_folders_and_link_identical_encodes(profile, tmp_path):
    """dubbed and subbed differ only in the mux: subbed links dubbed's video and audio encodes into its own folder
    (no encode); 720p resizes, so its video is made again in its own folder and dubbed's is left as it was."""
    plan = make_plan(tmp_path)
    dubbed, dubbed_plan = variant(video_job(plan, tmp_path), plan, "dubbed")
    dubbed_state = JobState()
    tools, _ = run_logged(dubbed, dubbed_plan, profile, dubbed_state)
    assert "x264" in tools and dubbed.job_dir == tmp_path / "Show.S01E01.mkv_tmp" / "dubbed"
    assert dubbed.video_output.parent == dubbed.job_dir and (dubbed.job_dir / "video.vpy").is_file()
    (dubbed.work_dir / "Show.S01E01.mkv.ffindex").write_bytes(
        b"index"
    )  # the source's, shared: what the real one leaves

    subbed, subbed_plan = variant(dubbed, dubbed_plan, "subbed")
    state = JobState()
    tools, lines = run_logged(subbed, subbed_plan, profile, state)
    assert tools == ["python", "mkvmerge"]  # the indexer keeps the source's index; every encode is linked
    assert any("Video (x264): made by the job in dubbed/, reused" in line for line in lines)
    assert os.path.samefile(subbed.video_output, dubbed.video_output)
    assert subbed.video_output.parent == subbed.job_dir
    assert {"video", "audio.1", "audio.2"} <= set(state.steps)
    linked = finished_files(subbed.job_dir)[subbed.video_output.name]
    assert linked.portable and linked.portable == finished_files(dubbed.job_dir)[dubbed.video_output.name].portable
    assert run_logged(subbed, subbed_plan, profile, state)[0] == []  # its own records now: nothing to do

    small, small_plan = variant(dubbed, dubbed_plan, "720p")
    small.video.crop = Crop(0, 140, 0, 140)
    tools, _ = run_logged(small, small_plan, profile, JobState())
    assert "x264" in tools and "qaac64" not in tools  # the audio is the same: linked
    assert not os.path.samefile(small.video_output, dubbed.video_output)
    assert run_logged(dubbed, dubbed_plan, profile, dubbed_state)[0] == []  # dubbed's files are intact


def test_a_section_made_again_is_not_taken_from_another_job(profile, tmp_path):
    plan = make_plan(tmp_path)
    dubbed, dubbed_plan = variant(video_job(plan, tmp_path), plan, "dubbed")
    run_logged(dubbed, dubbed_plan, profile, JobState())
    subbed, subbed_plan = variant(dubbed, dubbed_plan, "subbed")

    found = {o.id: o for o in reuse_offers(subbed, subbed_plan, profile, APP, {})}
    assert found["video"].origin == "dubbed" and found["video"].current
    assert found["video"].file == dubbed.video_output

    state = JobState(redo=["video"])
    tools, _ = run_logged(subbed, subbed_plan, profile, state)
    assert "x264" in tools and "qaac64" not in tools and state.redo == []
    assert not os.path.samefile(subbed.video_output, dubbed.video_output)


def test_a_linked_file_brings_the_files_its_tool_wrote_beside_it(tmp_path):
    """x265's pass 2 reads `<stats>.cutree` beside the stats file pass 1 wrote."""
    from videoforge.core.pipeline.share import _link

    source, target = tmp_path / "a" / "video.stats", tmp_path / "b" / "video.stats"
    source.parent.mkdir()
    target.parent.mkdir()
    source.write_bytes(b"stats")
    (source.parent / "video.stats.cutree").write_bytes(b"cutree")
    (source.parent / FINISHED_NAME).write_text("{}", encoding="utf-8")
    target.write_bytes(b"stale")
    _link(source, target)
    assert os.path.samefile(source, target) and (target.parent / "video.stats.cutree").read_bytes() == b"cutree"
    assert not (target.parent / FINISHED_NAME).exists()
