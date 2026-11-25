"""Queue admission and shared-file ownership across full jobs."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time

import pytest
from test_server import FakeIndexer, FakeRun, add, make_client, make_files, wait_for

from videoforge.core.config import load_app_config
from videoforge.core.events import JobFinished, QueueFinished
from videoforge.core.execute import process
from videoforge.core.job import JobResult, JobSpec, JobStatus, OutputPolicy, StepStatus
from videoforge.core.models import AudioAction, JobInputs, Overrides, TrackOverride, track_key
from videoforge.core.pipeline.build import index_steps
from videoforge.core.pipeline.run import run_job
from videoforge.core.pipeline.steps import run_steps
from videoforge.core.video import vs
from videoforge.core.video.settings import Encoder, EncoderSettings, RateControl
from videoforge.core.workdir import clean_work_dir, work_dir
from videoforge.rule_sets.manual import ManualRuleSet
from videoforge.server.concurrency import Concurrency, RunPaths
from videoforge.server.events import EventHub
from videoforge.server.queue import JobQueue, Services
from videoforge.server.routes.video import _loading
from videoforge.server.store import Store


def until(predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "timed out waiting for queue state"
        time.sleep(0.01)


def test_live_limits_and_strict_order(tmp_path):
    make_files(tmp_path, "S01E01", "S01E02", "S01E03", "S01E04")
    with make_client(tmp_path, run=FakeRun(block=True)) as client:
        ids = add(client, tmp_path)
        q = client.app.state.queue
        for i in ids:
            wait_for(client, i, "ready", "warn")
        q.update(ids[2], encoder=EncoderSettings(encoder=Encoder.X265))
        config = client.get("/api/config").json()["concurrency"]
        assert not config["enabled"] and config["encoders"]["x265"]["run_alone"]
        config.update(enabled=True, total=3)
        assert client.put("/api/config", json={"concurrency": config}).status_code == 200
        events = []
        q.bus.subscribe(events.append, QueueFinished, JobFinished)
        q.enqueue(ids)
        q.start()
        until(lambda: q.queue_state()["active_ids"] == ids[:2])
        until(lambda: "alone" in q.queue_state()["waiting"].get(ids[2], ""))
        config["encoders"]["x265"]["run_alone"] = False
        client.put("/api/config", json={"concurrency": config})
        until(lambda: q.queue_state()["active_ids"] == ids[:3])
        config["enabled"] = False
        client.put("/api/config", json={"concurrency": config})
        client.post(f"/api/queue/cancel/{ids[1]}")
        until(lambda: q.queue_state()["active_ids"] == [ids[0], ids[2]])
        assert q.get(ids[3]).queued
        client.post("/api/queue/cancel")
        q.wait(5)
        assert q.get(ids[3]).queued
        assert len([e for e in events if isinstance(e, JobFinished)]) == 3
        assert len([e for e in events if isinstance(e, QueueFinished)]) == 1
        assert events[-1].statuses == (JobStatus.CANCELLED,) * 3 and events[-1].left == 1


def test_numbered_output_and_start_order(tmp_path):
    make_files(tmp_path, "S01E01", "S01E02", "S01E03")
    gates = [threading.Event() for _ in range(3)]
    targets = {}

    def run(spec, plan, *args, target, state, **kwargs):
        index = int(spec.name.split("E0")[1][0]) - 1
        targets[index] = target.path
        assert gates[index].wait(10)
        # The second job deliberately fails after the other writer has released its file.
        state.status = JobStatus.FAILED if index == 1 else JobStatus.DONE
        return JobResult(plan, state.status)

    with make_client(tmp_path, run=run) as client:
        ids = add(client, tmp_path)
        q = client.app.state.queue
        for i in ids:
            wait_for(client, i, "ready", "warn")
        out = tmp_path / "out"
        out.mkdir(exist_ok=True)
        (out / "Movie.mkv").touch()
        q.update(ids[0], output_dir=out, output_name="Movie", output_policy=OutputPolicy.RENAME)
        q.update(ids[1], output_dir=out, output_name="Movie.2")
        q.set_concurrency(Concurrency.model_validate({"enabled": True, "total": 3, "encoders": {"x264": {"cap": 3}}}))
        end = []
        q.bus.subscribe(end.append, QueueFinished)
        q.enqueue(ids)
        q.start()
        until(lambda: ids[1] in q.queue_state()["waiting"])
        assert q.queue_state()["active_ids"] == [ids[0]]  # job three cannot pass the collision
        gates[0].set()
        until(lambda: set(targets) == {0, 1, 2})
        assert targets[0] == targets[1] == out / "Movie.2.mkv"
        gates[2].set()
        until(lambda: q.queue_state()["active_ids"] == [ids[1]])
        gates[1].set()
        q.wait(5)
        assert [ev.statuses for ev in end] == [(JobStatus.DONE, JobStatus.FAILED, JobStatus.DONE)]


@pytest.mark.parametrize("sample_first", [True, False])
def test_samples_share_or_obey_exclusive_slot(tmp_path, sample_first):
    make_files(tmp_path, "S01E01", "S01E02")
    indexer = FakeIndexer(hold=["Show.S01E02.mkv"])
    with make_client(tmp_path, run=FakeRun(block=True), runner=indexer) as client:
        full, sample = add(client, tmp_path)
        q = client.app.state.queue
        for i in [full, sample]:
            wait_for(client, i, "ready", "warn")
        q.update(full, encoder=EncoderSettings(encoder=Encoder.X265))
        q.set_concurrency(Concurrency(enabled=True, limit_samples=True))
        if sample_first:
            assert q.sample(sample, 1)
            indexer.wait(1)
        q.enqueue([full])
        q.start()
        if sample_first:
            until(lambda: full in q.queue_state()["waiting"])
            assert not q.queue_state()["active_ids"]
        else:
            until(lambda: q.queue_state()["active_ids"] == [full])
            assert q.sample(sample, 1)
            until(lambda: q.get(sample).index_held)
            assert not indexer.calls
        q.set_concurrency(Concurrency(enabled=True))
        until(lambda: q.queue_state()["active_ids"] == [full])
        indexer.wait(1)
        q.stop_after_current()
        q.cancel_current()
        q.wait(5)
        assert q.get(sample).indexing
        q.stop_indexing()


def test_restart_recovers_all_active_jobs(tmp_path):
    make_files(tmp_path, "S01E01", "S01E02")
    with make_client(tmp_path, run=FakeRun(block=True)) as client:
        ids = add(client, tmp_path)
        q = client.app.state.queue
        for i in ids:
            wait_for(client, i, "ready", "warn")
        q.set_concurrency(Concurrency(enabled=True))
        q.enqueue(ids)
        q.start()
        until(lambda: all(q.get(i).progress for i in ids))
    with make_client(tmp_path) as client:
        q = client.app.state.queue
        assert q.concurrency.enabled and all(q.get(i).queued for i in ids)
        q.start()
        q.wait(5)
        assert all(q.get(i).state.status is JobStatus.DONE for i in ids)


def test_declared_paths_and_job_folder_collisions(tmp_path):
    source = tmp_path / "Episode.mkv"
    output = tmp_path / "Movie.2.mkv"
    job = JobSpec(JobInputs(source), "manual")
    active = RunPaths.for_job(job, output)
    assert active.conflicts(RunPaths.for_job(replace(job, label="main"), tmp_path / "remux.mkv"))
    assert not active.conflicts(RunPaths.for_job(replace(job, label="variant"), tmp_path / "variant.mkv"))
    for path in (output, output.with_name(output.name + ".partial"), job.job_dir / "video.264"):
        reader = JobSpec(JobInputs(tmp_path / "Other.mkv", audio=[path]), "manual")
        reads = RunPaths.for_job(reader, None)
        assert active.conflicts(reads) and reads.conflicts(active)


def test_remove_preserves_another_jobs_reserved_output(tmp_path):
    make_files(tmp_path, "S01E01", "S01E02")
    with make_client(tmp_path, run=FakeRun(block=True)) as client:
        removed, active = add(client, tmp_path)
        q = client.app.state.queue
        for i in (removed, active):
            wait_for(client, i, "ready", "warn")
        folder = q.get(removed).spec.work_dir
        folder.mkdir(parents=True, exist_ok=True)
        q.update(active, output_dir=folder)
        q.enqueue([active])
        q.start()
        until(lambda: q.get(active).progress)
        result = client.post("/api/jobs/remove", json={"ids": [removed], "work_dirs": True}).json()
        assert result["kept"] == {str(folder): "It contains a job input or output"}
        assert folder.is_dir()


def test_simultaneous_archive_cleanup(tmp_path):
    archive = tmp_path / "records"
    sources = [tmp_path / str(i) / "Episode.mkv" for i in range(8)]
    for source in sources:
        folder = work_dir(source)
        folder.mkdir(parents=True)
        (folder / "videoforge.log").write_text(str(source))
    for i in range(100):
        archive.mkdir(exist_ok=True)
        (archive / f"{i}.videoforge.log").touch()
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(lambda s: clean_work_dir(s, archive), sources))
    assert len(list(archive.glob("*.videoforge.log"))) == 100
    for source, result in zip(sources, results, strict=True):
        assert not work_dir(source).exists()
        assert next(iter(result.values())).read_text() == str(source)


def test_preview_waits_until_full_job_index_finishes(tmp_path):
    make_files(tmp_path)
    writing, finish, requesting, opened = (threading.Event() for _ in range(4))

    def index(commands, log, cancel):
        Path(commands[0][-1]).write_bytes(b"index under construction")
        writing.set()
        assert finish.wait(5)

    class Preview:
        def has(self, script, slot):
            return False

    with make_client(tmp_path) as client:
        [job_id] = add(client, tmp_path)
        wait_for(client, job_id, "ready", "warn")
        q = client.app.state.queue
        entry = q.get(job_id)
        entry.spec.job_dir.mkdir(parents=True, exist_ok=True)
        steps = index_steps(entry.spec, q.app)

        def preview():
            requesting.set()
            with _loading(entry, Preview(), "script", entry.id):
                opened.set()

        with ThreadPoolExecutor(2) as pool:
            producer = pool.submit(run_steps, steps, {}, runner=index, log=lambda _: None)
            assert writing.wait(5)
            reader = pool.submit(preview)
            try:
                assert requesting.wait(5) and not opened.wait(0.1)
            finally:
                finish.set()
            producer.result(5)
            reader.result(5)
        assert opened.is_set()


@pytest.mark.parametrize(
    "scenario", ["share", "cancel-producer", "cancel-waiter", "cancel-different", "failed-producer", "two-pass", "redo"]
)
def test_real_three_variants(tmp_path, scenario):
    app = replace(load_app_config(), min_free_gb=0, parallel_audio=1)
    if not all(shutil.which(tool) for tool in (app.tools.ffmpeg, app.tools.vspipe, app.tools.x264, app.tools.mkvmerge)):
        pytest.skip("requires ffmpeg, vspipe, x264 and MKVToolNix")
    vs.configure(app.tools.vs_plugins)
    source = tmp_path / "Episode.mkv"
    subprocess.run(
        [
            app.tools.ffmpeg,
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x180:rate=24",
            "-f",
            "lavfi",
            "-i",
            "sine=sample_rate=48000",
            "-t",
            "3",
            "-c:v",
            "ffv1",
            "-c:a",
            "pcm_s16le",
            "-ac",
            "2",
            "-metadata:s:a:0",
            "language=eng",
            str(source),
        ],
        check=True,
    )
    counts = Counter()
    overlap = threading.Barrier(2, timeout=20)
    first = threading.Event()
    release = threading.Event()
    owner = []
    lock = threading.Lock()

    def run(spec, *args, **kwargs):
        def measured(commands, log, token):
            last = commands[-1]
            tool = Path(last[0]).stem.lower()
            with lock:
                counts[tool] += 1
            if tool == "x264":
                if scenario == "share":
                    overlap.wait()  # distinct video settings must both reach the real encoder
                if scenario == "cancel-different" and spec.id == different.id:
                    first.set()
                    assert release.wait(15)
                elif (
                    scenario in ("cancel-producer", "cancel-waiter", "failed-producer")
                    and spec.label != different.spec.label
                ):
                    with lock:
                        if not owner:
                            owner.append(spec.id)
                            first.set()
                    if spec.id == owner[0]:
                        assert release.wait(15)
                        if scenario == "failed-producer":
                            raise process.ToolError("producer failed")
            process.run(commands, log, token)

        return run_job(spec, *args, runner=measured, **kwargs)

    store = Store(tmp_path / "queue.db")
    q = JobQueue(app, lambda _: ManualRuleSet(), store, EventHub(), Services(run=run, versions=None))
    try:
        q.set_concurrency(Concurrency.model_validate({"enabled": True, "total": 3, "encoders": {"x264": {"cap": 3}}}))
        encoder = EncoderSettings(preset="ultrafast", crf=24, options={"threads": "2"})
        if scenario == "two-pass":
            encoder.rate_control = RateControl.TWO_PASS
            encoder.bitrate_kbps = 600
        [one], _ = q.add(
            [JobInputs(source)],
            "manual",
            encoder=encoder,
            output_dir=tmp_path / "out",
            auto_index=False,
            auto_crop=False,
        )
        until(lambda: one.plan is not None or one.probe_error)
        assert one.plan and not one.plan.blocked, (one.probe_error, one.plan)
        track = track_key(one.plan.source.audio[0])
        q.update(one.id, qpf=False, overrides=Overrides(tracks={track: TrackOverride(action=AudioAction.OPUS)}))
        [matching] = q.duplicate([one.id])
        [different] = q.duplicate([matching.id])
        q.update(different.id, encoder=replace(encoder, crf=30, bitrate_kbps=400))
        entries = [one, matching, different]
        ids = [e.id for e in entries]
        assert q.enqueue(ids) == ids
        q.start()
        cancelled = None
        if scenario.startswith("cancel") or scenario == "failed-producer":
            assert first.wait(30), [e.state.error for e in entries]
            # Isolate cancellation during video from cancellation of an in-flight audio encode.
            until(lambda: any("audio.1" in e.state.steps for e in entries))
            if scenario == "cancel-different":
                cancelled = different.id
            elif scenario == "cancel-waiter":
                cancelled = next(i for i in ids[:2] if i != owner[0])
            else:
                cancelled = owner[0]
            if scenario != "failed-producer":
                q.cancel_current(cancelled)
            release.set()
        q.wait(60)
        assert not q.running
        for e in entries:
            if e.id == cancelled:
                assert e.state.status is (JobStatus.FAILED if scenario == "failed-producer" else JobStatus.CANCELLED)
            else:
                assert e.state.status is JobStatus.DONE, (e.state.error, list(e.log)[-5:])
                assert e.state.output.is_file() and e.state.run[-1].status is StepStatus.DONE
        assert counts["ffmpeg"] == 1
        assert counts["x264"] == {"cancel-producer": 3, "failed-producer": 3, "two-pass": 4}.get(scenario, 2)
        if cancelled not in ids[:2]:
            assert os.path.samefile(one.spec.video_output, matching.spec.video_output)
        if scenario == "redo":
            original = one.spec.video_output.read_bytes()
            q.choose_reuse({matching.id: ["audio.1"]})
            q.enqueue([matching.id])
            q.start()
            q.wait(30)
            assert matching.state.status is JobStatus.DONE and counts["x264"] == 3
            assert one.spec.video_output.read_bytes() == original
            assert not os.path.samefile(one.spec.video_output, matching.spec.video_output)
    finally:
        release.set()
        q.shutdown()
        store.close()
