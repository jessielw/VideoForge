"""The web server: jobs API, queue worker, events, restart recovery, folder browser, video preview.

Probing and running are faked (Services); the video preview tests use the real
VapourSynth on an ffmpeg-made clip and skip without the tools.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from conftest import audio, source, sub
from fastapi.testclient import TestClient

from videoforge.core.config import PROJECT_ROOT, AppConfig, Tools
from videoforge.core.job import JobResult, JobSpec, JobStatus, StepRecord, StepStatus, planned_encode
from videoforge.core.jobs import ProbedInputs, external_tracks
from videoforge.core.models import AudioCodec as C
from videoforge.core.models import SubFormat as F
from videoforge.core.models import VideoInfo
from videoforge.core.pipeline.steps import Step, StepProgress
from videoforge.core.video.settings import Crop
from videoforge.server.app import create_app
from videoforge.server.queue import Services
from videoforge.server.settings import ServerSettings

APP = AppConfig(tools=Tools(mkvmerge="mkvmerge", deezy="deezy", dee="dee", truehdd="truehdd", qaac="qaac64",
                            ffmpeg="ffmpeg", vs_plugins=str(PROJECT_ROOT / "tools" / "vs-plugins")), profile="manual")


def make_files(root: Path, *episodes: str) -> None:
    (root / "src").mkdir(exist_ok=True)
    for ep in episodes or ("S01E01",):
        for f in (root / "src" / f"Show.{ep}.mkv", root / "src" / f"Show.{ep}.en.srt"):
            f.write_bytes(b"x")


def fake_probe(spec: JobSpec, _app=None) -> ProbedInputs:
    """ja FLAC + en TrueHD, en/de PGS, 1080p 23.976 with black bars."""
    info = source(
        [audio(C.FLAC, "2.0", "ja", index=0), audio(C.TRUEHD, "5.1", "en", index=1)],
        [sub(F.PGS, "en", "English", index=0), sub(F.PGS, "de", "German", index=1)],
        name=spec.inputs.source.name,
    )
    info.path = spec.inputs.source
    info.video = VideoInfo(1920, 1080, default_duration_ns=41708333)
    ext, issues = external_tracks(info, spec.inputs.subtitles)
    return ProbedInputs(spec.inputs, info, planned_encode(spec, info), ext, issues)


class FakeRun:
    """Logs, reports progress, records a step, and finishes DONE (or waits to be cancelled)."""

    def __init__(self, block: bool = False):
        self.runs: list[str] = []
        self.block = block

    def __call__(self, spec, plan, profile, app, *, state, log, cancel, progress, on_record, on_step):
        self.runs.append(spec.name)
        step = Step("video", "Video (x264)", argvs=(("x264", "--crf", "18"),))
        run = step.to_run()
        state.run = [run]
        on_step(run)
        run.status = StepStatus.RUNNING
        on_step(run)
        log("== 1/1 Video (x264)")
        log("[x264] [ 50.0%] 1/2 frames")
        run.log("[x264] [ 50.0%] 1/2 frames")  # as run_steps keeps a step's tail
        progress(StepProgress(0, 1, step, 0.5, 0.5))
        if self.block:
            while not cancel.cancelled:
                time.sleep(0.01)
            run.status = StepStatus.CANCELLED
            on_step(run)
            state.status, state.error = JobStatus.CANCELLED, "Cancelled"
            return JobResult(plan, JobStatus.CANCELLED, error="Cancelled")
        state.steps["video"] = StepRecord("video", "abc")
        on_record(state.steps["video"])
        run.status, run.exit_code = StepStatus.DONE, 0
        on_step(run)
        out = spec.output_dir / spec.inputs.source.name
        state.status, state.output = JobStatus.DONE, out
        return JobResult(plan, JobStatus.DONE, out)


def make_client(tmp_path: Path, run=None, records=None, detect_crop=None) -> TestClient:
    services = Services(probe=fake_probe, run=run or FakeRun(),
                        record=(records.append if records is not None else None), detect_crop=detect_crop)
    app = create_app(ServerSettings(data_dir=tmp_path / "data", roots=[tmp_path], frontend_dir=tmp_path / "none"),
                     APP, services=services, setup_vapoursynth=False)
    return TestClient(app)


def wait_for(client: TestClient, job_id: str, *statuses: str, timeout: float = 5) -> dict:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in statuses:
            return job
        time.sleep(0.02)
    raise AssertionError(f"{job_id} stayed {job['status']}, wanted {statuses}")


def add(client: TestClient, root: Path, **extra) -> list[str]:
    body = {"sources": [str(root / "src")], "subtitles": [str(root / "src")], "profile": "manual",
            "original_language": "ja", "output_dir": str(root / "out")} | extra
    r = client.post("/api/jobs", json=body)
    assert r.status_code == 200, r.text
    return r.json()["added"]


def test_add_inspect_and_edit(tmp_path):
    make_files(tmp_path, "S01E01", "S01E02")
    with make_client(tmp_path) as client:
        preview = client.post("/api/match", json={"sources": [str(tmp_path / "src")]}).json()
        assert [Path(j["source"]).name for j in preview["jobs"]] == ["Show.S01E01.mkv", "Show.S01E02.mkv"]

        ids = add(client, tmp_path)
        assert len(ids) == 2
        job = wait_for(client, ids[0], "ready", "warn")
        assert job["encoder"] == "x264 crf 18"  # the manual profile's default encode
        assert job["spec"]["encoder"]["preset"] == "slow"
        assert [a["action"] for a in job["plan"]["audio"]] == ["copy", "copy"]
        assert job["plan"]["encode_path"].endswith(r"Show.S01E01.mkv_tmp\video.264")
        assert [s["key"] for s in job["tracks"]["subs"]][:2] == ["id:10", "id:11"]
        flags = {"default": False, "forced": False, "hearing_impaired": False, "commentary": False, "original": False}
        assert job["tracks"]["subs"][0]["detected"] == flags
        assert job["tracks"]["audio"][0]["detected"] == flags | {"visual_impaired": False}  # audio description

        # Crop the video: the planned encode shrinks, the plan follows (no re-probe).
        video = job["spec"]["video"] | {"crop": {"left": 0, "top": 140, "right": 0, "bottom": 140}}
        edited = client.patch(f"/api/jobs/{ids[0]}", json={"video": video}).json()
        assert edited["crop"] == {"left": 0, "top": 140, "right": 0, "bottom": 140}

        # Track overrides: drop German.
        overrides = edited["spec"]["overrides"] | {"tracks": {"id:11": {"exclude": True}}}
        edited = client.patch(f"/api/jobs/{ids[0]}", json={"overrides": overrides}).json()
        assert "German" not in [s["title"] for s in edited["plan"]["subs"]]

        # A batch edit: one encoder setting for both episodes.
        enc = edited["spec"]["encoder"] | {"rate_control": "crf", "crf": 17}
        assert client.post("/api/jobs/apply", json={"ids": ids, "encoder": enc}).json()["updated"] == ids
        assert [j["encoder"] for j in client.get("/api/jobs").json()] == ["x264 crf 17", "x264 crf 17"]

        commands = client.get(f"/api/jobs/{ids[0]}/commands").json()
        assert [c["id"] for c in commands] == ["script", "index", "chapters", "video", "mux"]  # audio is copied
        assert "--crf 17" in commands[3]["command"] and " | " in commands[3]["command"]
        assert client.patch(f"/api/jobs/{ids[0]}", json={"encoder": {"rate_control": "nope"}}).status_code == 422
        assert client.get("/api/jobs/nope").status_code == 404
        (manual,) = client.get("/api/profiles").json()
        assert manual["id"] == "manual" and manual["default"] and manual["defaults"]["encoder"]["crf"] == 18


def test_files_added_to_a_job(tmp_path):
    make_files(tmp_path)
    extra = tmp_path / "extra"
    extra.mkdir()
    (extra / "Signs.ass").write_text("[Script Info]\n", encoding="utf-8")  # no language in the name
    (extra / "Show.fr.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\nSalut\n", encoding="utf-8")
    (extra / "notes.txt").write_text("x", encoding="utf-8")
    chapters = tmp_path / "chapters.xml"
    chapters.write_text("<Chapters/>", encoding="utf-8")
    with make_client(tmp_path) as client:
        (job_id,) = add(client, tmp_path)
        job = wait_for(client, job_id, "ready", "warn")
        en = job["spec"]["inputs"]["subtitles"]
        subs = en + [str(extra)]  # a folder adds its subtitle files

        job = client.patch(f"/api/jobs/{job_id}", json={"inputs": {"subtitles": subs, "chapters": str(chapters)}}).json()
        assert job["status"] in ("ready", "warn")  # read at once, no re-probe
        added = [s for s in job["tracks"]["subs"] if s["external_path"]]
        assert [(Path(s["external_path"]).name, s["format"], s["language"]) for s in added] == [
            ("Show.S01E01.en.srt", "srt", "en"), ("Show.fr.srt", "srt", "fr"), ("Signs.ass", "ass", "und")]
        assert job["plan"]["chapters_path"] == str(chapters)
        assert [i["code"] for i in job["issues"]] == ["subs.language"]  # the manual profile asks for a language

        key = next(s["key"] for s in added if s["language"] == "und")
        overrides = job["spec"]["overrides"] | {"tracks": {key: {"language": "en", "flags": {"forced": True}}}}
        job = client.patch(f"/api/jobs/{job_id}", json={"overrides": overrides}).json()
        assert not job["issues"] and ("en", True) in [(s["language"], s["forced"]) for s in job["plan"]["subs"]]

        job = client.patch(f"/api/jobs/{job_id}", json={"inputs": {"subtitles": en, "chapters": None}}).json()
        assert len([s for s in job["tracks"]["subs"] if s["external_path"]]) == 1
        assert job["plan"]["chapters_path"].endswith("chapters_chapters.txt")  # back to AutoQPF's
        bad = client.patch(f"/api/jobs/{job_id}", json={"inputs": {"subtitles": [str(extra / "gone.srt")]}})
        assert bad.status_code == 422


def test_queue_runs_jobs_and_streams_events(tmp_path):
    make_files(tmp_path, "S01E01", "S01E02")
    records: list = []
    with make_client(tmp_path, records=records) as client:
        ids = add(client, tmp_path)
        for i in ids:
            wait_for(client, i, "ready", "warn")
        with client.websocket_connect("/api/events") as ws:
            assert ws.receive_json()["type"] == "hello"
            assert client.post("/api/queue/start").json()["running"] in (True, False)
            seen, events = set(), []
            end = time.monotonic() + 5
            while not {"progress", "log", "step"} <= seen and time.monotonic() < end:
                events.append(ws.receive_json())
                seen.add(events[-1]["type"])
            assert {"progress", "log", "step"} <= seen
            step_event = next(ev for ev in events if ev["type"] == "step")
            assert step_event["step"]["id"] == "video" and "tail" not in step_event["step"]
            assert (step_event["index"], step_event["total"], step_event["step"]["status"]) == (0, 1, "pending")
            tool_line = next(ev for ev in events if ev["type"] == "log" and ev["line"].startswith("[x264]"))
            assert tool_line["step"] == "video"
            # The worker's last queue event says the queue stopped (it once said running until a reload).
            while not ((ev := ws.receive_json())["type"] == "queue" and ev["queued"] == 0 and ev["current"] is None):
                pass
            assert ev["running"] is False
        for i in ids:
            job = wait_for(client, i, "done")
            assert job["steps"]["video"]["fingerprint"] == "abc"
        assert len(records) == 2
        log = client.get(f"/api/jobs/{ids[0]}/log").json()["lines"]
        assert "[x264] [ 50.0%] 1/2 frames" in log
        (step,) = client.get(f"/api/jobs/{ids[0]}/steps").json()
        assert (step["status"], step["command"], step["exit_code"]) == ("done", "x264 --crf 18", 0)
        assert step["lines"] == ["[x264] [ 50.0%] 1/2 frames"] and not step["partial"]  # not the header
        assert (tmp_path / "src" / "Show.S01E01.mkv_tmp" / "videoforge.log").is_file()

        # Editing a finished job clears its outcome (but keeps its finished steps).
        job = client.get(f"/api/jobs/{ids[0]}").json()
        client.patch(f"/api/jobs/{ids[0]}", json={"qpf": False})
        job = client.get(f"/api/jobs/{ids[0]}").json()
        assert job["status"] in ("ready", "warn") and "video" in job["steps"]


def test_busy_jobs_cant_change_and_cancel_stops(tmp_path):
    make_files(tmp_path)
    run = FakeRun(block=True)
    with make_client(tmp_path, run=run) as client:
        (job_id,) = add(client, tmp_path)
        wait_for(client, job_id, "ready", "warn")
        client.post("/api/queue/start", json={"ids": [job_id]})
        wait_for(client, job_id, "running")
        assert client.patch(f"/api/jobs/{job_id}", json={"qpf": False}).status_code == 409
        assert client.delete(f"/api/jobs/{job_id}").status_code == 409
        client.post("/api/queue/cancel")
        wait_for(client, job_id, "cancelled")
        client.app.state.queue.wait(5)
        assert client.get("/api/queue").json()["running"] is False


def test_restart_requeues_an_interrupted_job(tmp_path):
    make_files(tmp_path)
    with make_client(tmp_path) as client:
        (job_id,) = add(client, tmp_path)
        wait_for(client, job_id, "ready", "warn")
        q = client.app.state.queue
        e = q.get(job_id)
        e.running = True  # as if the server died mid-run
        q._save(e)
    with make_client(tmp_path) as client:
        job = wait_for(client, job_id, "queued")
        assert "Interrupted" in job["issue"]
        client.post("/api/queue/start")
        wait_for(client, job_id, "done")
    with make_client(tmp_path) as client:  # after a restart the steps come from the saved state
        (step,) = client.get(f"/api/jobs/{job_id}/steps").json()
        assert step["status"] == "done" and step["lines"] == ["[x264] [ 50.0%] 1/2 frames"]


def test_shutdown_cancels_a_job_that_starts_as_it_begins(tmp_path):
    """The worker takes a job, then shutdown() cancels before that job has its cancel token: the job must still
    be cancelled at once, not run until shutdown gives up waiting."""
    make_files(tmp_path)
    with make_client(tmp_path, run=FakeRun(block=True)) as client:
        (job_id,) = add(client, tmp_path)
        wait_for(client, job_id, "ready", "warn")
        q = client.app.state.queue
        taken, go_on = threading.Event(), threading.Event()
        take = q._take_next

        def held_take_next():
            e = take()
            if e is not None:
                taken.set()
                go_on.wait(5)
            return e

        q._take_next = held_take_next
        client.post("/api/queue/start", json={"ids": [job_id]})
        assert taken.wait(5)
        stopper = threading.Thread(target=q.shutdown, kwargs={"timeout": 5})
        t0 = time.monotonic()
        stopper.start()
        time.sleep(0.2)  # shutdown() has cancelled: there was no token yet
        go_on.set()
        stopper.join()
        assert time.monotonic() - t0 < 2
        assert q.get(job_id).state.status is JobStatus.CANCELLED


def test_a_job_that_wont_stop_is_requeued_after_shutdown(tmp_path):
    """shutdown() stops waiting; the store closes; the job's later saves are dropped, so the store still says
    running and the next start queues it again, as after a crash."""
    make_files(tmp_path)
    release = threading.Event()

    class Stubborn(FakeRun):
        def __call__(self, spec, plan, profile, app, *, state, log, cancel, progress, on_record, on_step):
            run = Step("video", "Video (x264)", argvs=(("x264",),)).to_run()
            state.run = [run]
            run.status = StepStatus.RUNNING
            on_step(run)
            release.wait(5)  # ignores the cancel
            run.status = StepStatus.CANCELLED
            on_step(run)  # saves into the closed store
            return JobResult(plan, JobStatus.CANCELLED, error="Cancelled")

    errors = []
    old_hook, threading.excepthook = threading.excepthook, lambda a: errors.append(a.exc_value)
    try:
        with make_client(tmp_path, run=Stubborn()) as client:
            (job_id,) = add(client, tmp_path)
            wait_for(client, job_id, "ready", "warn")
            q = client.app.state.queue
            client.post("/api/queue/start", json={"ids": [job_id]})
            wait_for(client, job_id, "running")
            q.shutdown(timeout=0.3)
            client.app.state.store.close()
            release.set()
            q.wait(5)
    finally:
        threading.excepthook = old_hook
    assert errors == []
    with make_client(tmp_path) as client:
        job = wait_for(client, job_id, "queued")
        assert "Interrupted" in job["issue"]


def test_missing_encoder_tools_block_until_set(tmp_path):
    make_files(tmp_path)
    with make_client(tmp_path) as client:  # APP's qaac64/ffmpeg/dee... don't exist here
        (job_id,) = add(client, tmp_path)
        wait_for(client, job_id, "ready", "warn")
        missing = {e["id"]: e["missing"] for e in client.get("/api/config/encoders").json()}
        assert missing["aac"] and missing["flac"] == missing["ddp"] == []  # qaac is missing
        job = client.get(f"/api/jobs/{job_id}").json()
        key = f"id:{job['plan']['audio'][0]['source']['id']}"
        overrides = job["spec"]["overrides"] | {"tracks": {key: {"action": "aac"}}}
        job = client.patch(f"/api/jobs/{job_id}", json={"overrides": overrides}).json()
        assert job["status"] == "blocked"
        assert any(i["code"] == "tools.missing" and "AAC (qaac) needs" in i["message"] for i in job["issues"])

        client.put("/api/config", json={"tools": {"qaac": sys.executable, "ffmpeg": sys.executable}})
        assert {e["id"]: e["missing"] for e in client.get("/api/config/encoders").json()}["aac"] == []
        job = client.get(f"/api/jobs/{job_id}").json()  # replanned when the tools changed
        assert not any(i["code"] == "tools.missing" for i in job["issues"]) and job["status"] != "blocked"


def test_settings_page_config(tmp_path):
    folder = tmp_path / "media"
    folder.mkdir()
    with make_client(tmp_path) as client:
        cfg = client.get("/api/config").json()
        tools = {t["name"]: t for t in cfg["tools"]}
        assert tools["x264"]["path"] == "x264" and tools["x264"]["custom"] is None
        assert cfg["profile"] == "manual" and not cfg["roots_custom"] and cfg["restart"] == []

        changed = client.put("/api/config", json={"tools": {"x264": sys.executable}, "roots": [str(folder)]}).json()
        assert {t["name"]: t for t in changed["tools"]}["x264"]["path"] == sys.executable
        assert client.app.state.queue.app.tools.x264 == sys.executable  # new runs use it
        assert client.get("/api/fs/roots").json() == [str(folder)] and changed["roots_custom"]
        assert client.get("/api/fs/list", params={"path": str(tmp_path)}).status_code == 403

        checked = client.post("/api/config/tools/check", json={"name": "x264", "path": sys.executable}).json()
        assert checked["found"] == sys.executable and checked["status"] in ("ok", "unknown")
        assert len(client.get("/api/config/tools").json()) == len(cfg["tools"])

        assert client.put("/api/config", json={"tools": {"nope": "x"}}).status_code == 422
        assert client.put("/api/config", json={"roots": [str(tmp_path / "missing")]}).status_code == 422
        assert client.put("/api/config", json={"profile": "not-installed"}).status_code == 422
        changed = client.put("/api/config", json={"tools": {"vs_plugins": str(folder)}}).json()
        assert changed["restart"] and "preview" in changed["restart"][0]

    with make_client(tmp_path) as client:  # kept across a restart
        cfg = client.get("/api/config").json()
        assert {t["name"]: t for t in cfg["tools"]}["x264"]["custom"] == sys.executable
        assert cfg["roots"] == [str(folder)]
        reset = client.put("/api/config", json={"tools": {"x264": None}, "roots": None, "profile": None}).json()
        assert {t["name"]: t for t in reset["tools"]}["x264"]["path"] == "x264" and not reset["roots_custom"]


def test_presets(tmp_path):
    with make_client(tmp_path) as client:
        assert client.get("/api/presets").json() == {"video": [], "encoder": [], "template": [], "template_defaults": {}}
        saved = client.put("/api/presets/encoder/Fast x265", json={"encoder": "x265", "crf": 20, "preset": "fast"}).json()
        (enc,) = saved["encoder"]
        assert enc["name"] == "Fast x265" and enc["data"]["crf"] == 20 and enc["data"]["depth"] == 8  # filled in
        video = {"source_filter": "lsmash", "crop": {"left": 2, "top": 0, "right": 0, "bottom": 0},
                 "resize": {"width": 1280, "height": 720}, "filters": "clip = clip"}
        (vid,) = client.put("/api/presets/video/720p", json=video).json()["video"]
        assert "crop" not in vid["data"] and vid["data"]["resize"]["kernel"] == "Spline36"

        assert client.put("/api/presets/audio/x", json={}).status_code == 404
        assert client.put("/api/presets/encoder/%20", json={}).status_code == 422
        assert client.put("/api/presets/encoder/bad", json={"rate_control": "nope"}).status_code == 422

    with make_client(tmp_path) as client:  # kept across a restart
        assert [p["name"] for p in client.get("/api/presets").json()["encoder"]] == ["Fast x265"]
        assert client.delete("/api/presets/encoder/Fast x265").json()["encoder"] == []


def test_templates(tmp_path):
    """A template sets the whole run when jobs are added or on a batch; its auto crop is detected per
    job afterwards (the job can't be queued meanwhile), and a crop set by hand meanwhile wins."""
    make_files(tmp_path, "S01E01", "S01E02")
    gate = threading.Event()
    gate.set()

    def detect_crop(spec):
        assert gate.wait(5)
        return Crop(0, 20, 0, 22)

    template = {"video": {"filters": "clip = clip", "crop": {"left": 4, "top": 0, "right": 4, "bottom": 0}},
                "encoder": {"encoder": "x265", "crf": 16}, "mux": {"container": "mkv", "extra": "-x"},
                "qpf": False, "crop_mode": "auto"}
    with make_client(tmp_path, detect_crop=detect_crop) as client:
        ids = add(client, tmp_path, template=template)
        for job_id in ids:
            job = wait_for(client, job_id, "ready", "warn", "blocked")
            assert job["status"] != "blocked", job["issues"] if "issues" in job else job["plan"]["issues"]
            spec = job["spec"]
            assert spec["encoder"]["encoder"] == "x265" and spec["encoder"]["crf"] == 16
            assert spec["mux"] == {"container": "mkv", "extra": "-x"} and spec["qpf"] is False
            assert spec["video"]["filters"] == "clip = clip"
            assert spec["video"]["crop"] == {"left": 0, "top": 20, "right": 0, "bottom": 22} and not spec["autocrop"]

        # A batch: fixed crop on both; then the container alone keeps each job's extra arguments.
        fixed = template | {"crop_mode": "fixed"}
        assert client.post("/api/jobs/apply", json={"ids": ids, "template": fixed}).json()["updated"] == ids
        assert {client.get(f"/api/jobs/{i}").json()["spec"]["video"]["crop"]["left"] for i in ids} == {4}
        client.patch(f"/api/jobs/{ids[0]}", json={"mux": {"container": "mp4", "extra": "-y"}})
        client.post("/api/jobs/apply", json={"ids": ids, "container": "mkv"})
        assert [client.get(f"/api/jobs/{i}").json()["spec"]["mux"] for i in ids] == [
            {"container": "mkv", "extra": "-y"}, {"container": "mkv", "extra": "-x"}]

        # Auto again, held: the job shows it, can't be queued, and a hand crop meanwhile wins.
        gate.clear()
        client.patch(f"/api/jobs/{ids[0]}", json={"template": template})
        job = wait_for(client, ids[0], "cropping")
        assert client.post("/api/queue/enqueue", json={"ids": [ids[0]]}).json()["enqueued"] == []
        assert client.get(f"/api/jobs/{ids[0]}").json()["status"] == "cropping"
        hand = job["spec"]["video"] | {"crop": {"left": 0, "top": 8, "right": 0, "bottom": 8}}
        client.patch(f"/api/jobs/{ids[0]}", json={"video": hand})
        gate.set()
        job = wait_for(client, ids[0], "ready", "warn")
        assert job["spec"]["video"]["crop"]["top"] == 8 and not job["spec"]["autocrop"]
        state = client.post("/api/queue/enqueue", json={"ids": [ids[0]]}).json()
        assert state["enqueued"] == [ids[0]] and state["queued"] == 1  # the ids it queued; the queue's count
        client.post("/api/queue/dequeue", json={"ids": [ids[0]]})

        saved = client.put("/api/presets/template/Show", json=fixed).json()["template"]
        assert saved[0]["data"]["video"]["crop"]["left"] == 4  # a template keeps its crop
        assert client.get("/api/profiles").json()[0]["defaults"]["template"]["crop_mode"] == "keep"

        # The profile's default template: jobs added with no settings of their own get it; it follows a
        # rename and falls back to the profile's own defaults when deleted.
        assert client.put("/api/presets/template-default/manual", json={"name": "Nope"}).status_code == 404
        assert client.put("/api/presets/template-default/other", json={"name": "Show"}).status_code == 404
        listed = client.put("/api/presets/template-default/manual", json={"name": "Show"}).json()
        assert listed["template_defaults"] == {"manual": "Show"}
        listed = client.post("/api/presets/template/Show/rename", json={"to": "Show 1080p"}).json()
        assert [t["name"] for t in listed["template"]] == ["Show 1080p"] and listed["template_defaults"] == {"manual": "Show 1080p"}
        client.post("/api/jobs/remove", json={"ids": ids})
        (new,) = add(client, tmp_path, sources=[str(tmp_path / "src" / "Show.S01E01.mkv")])
        spec = client.get(f"/api/jobs/{new}").json()["spec"]
        assert spec["encoder"]["encoder"] == "x265" and spec["video"]["crop"]["left"] == 4
        (own,) = add(client, tmp_path, sources=[str(tmp_path / "src" / "Show.S01E01.mkv")], encoder={"crf": 20})
        assert client.get(f"/api/jobs/{own}").json()["spec"]["encoder"]["encoder"] == "x264"  # its own settings
        assert client.delete("/api/presets/template/Show 1080p").json()["template_defaults"] == {}


def test_template_audio(tmp_path):
    """A template's audio slots become each job's track overrides once its tracks are known: when added
    (after the probe) and on a batch (at once). The job's earlier audio choices are replaced."""
    make_files(tmp_path, "S01E01")
    template = {"audio": {"slots": [
        {"track": {"title": "Japanese"}},
        {"track": {}, "extra": [{"action": "ddp", "layout": "5.1", "bitrate_kbps": 640, "title": "DDP 5.1"}]},
        {"track": {"action": "aac"}},  # no third track: ignored
    ]}}
    with make_client(tmp_path) as client:
        (job_id,) = add(client, tmp_path, template=template)
        job = wait_for(client, job_id, "ready", "warn")
        assert [(a["action"], a["title"]) for a in job["plan"]["audio"]] == [
            ("copy", "Japanese"), ("copy", ""), ("ddp", "DDP 5.1")]
        assert job["spec"]["audio_template"] is None and job["spec"]["overrides"]["copies"] == ["id:2+1"]

        overrides = job["spec"]["overrides"] | {"tracks": {"id:1": {"title": "Mine"}}}
        client.patch(f"/api/jobs/{job_id}", json={"overrides": overrides})
        others = {"audio": {"slots": [{"track": {"action": "flac"}}], "others": "exclude"}}
        client.post("/api/jobs/apply", json={"ids": [job_id], "template": others})
        job = client.get(f"/api/jobs/{job_id}").json()
        assert [(a["action"], a["title"]) for a in job["plan"]["audio"]] == [("flac", "")]  # "Mine" replaced


def test_folder_browser(tmp_path):
    make_files(tmp_path)
    with make_client(tmp_path) as client:
        listing = client.get("/api/fs/list", params={"path": str(tmp_path / "src"), "extensions": ".mkv"}).json()
        assert [f["name"] for f in listing["files"]] == ["Show.S01E01.mkv"]
        assert listing["parent"] == str(tmp_path)
        assert client.get("/api/fs/list", params={"path": "C:\\Windows"}).status_code == 403
        assert client.get("/api/fs/roots").json() == [str(tmp_path)]
        paths = [str(tmp_path / "src"), str(tmp_path / "src" / "Show.S01E01.mkv"), str(tmp_path / "nope.mkv"),
                 "C:\\Windows", "relative.mkv"]
        kinds = client.post("/api/fs/kinds", json={"paths": paths}).json()
        assert [k["kind"] for k in kinds] == ["folder", "file", "missing", "outside", "missing"]


# --- real VapourSynth preview --------------------------------------------------------

FFMPEG = shutil.which("ffmpeg")


@pytest.mark.skipif(FFMPEG is None or not (PROJECT_ROOT / "tools" / "vs-plugins" / "bestsource.dll").exists(),
                    reason="needs ffmpeg and tools/vs-plugins")
def test_video_preview_endpoints(tmp_path):
    (tmp_path / "src").mkdir()
    clip = tmp_path / "src" / "Movie.mkv"
    subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=duration=2:size=320x136:rate=24",
         "-vf", "pad=320:180:0:22:black", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", str(clip)],
        check=True,
    )  # fmt: skip
    from videoforge.core.video import vs as vsx

    vsx.configure(APP.tools.vs_plugins)
    with make_client(tmp_path) as client:
        (job_id,) = add(client, tmp_path, sources=[str(clip)], subtitles=[])
        base = f"/api/jobs/{job_id}/video"
        assert client.get(f"{base}/info", params={"stage": "source"}).json()["height"] == 180
        crop = client.post(f"{base}/autocrop", params={"samples": 5}).json()
        assert crop["top"] in (20, 22) and crop["left"] == 0
        video = client.get(f"/api/jobs/{job_id}").json()["spec"]["video"] | {"crop": crop}
        client.patch(f"/api/jobs/{job_id}", json={"video": video})
        info = client.get(f"{base}/info").json()
        assert (info["width"], info["height"], info["frames"]) == (320, 180 - crop["top"] - crop["bottom"], 48)
        frame = client.get(f"{base}/frame", params={"n": 10})
        assert frame.headers["content-type"] == "image/jpeg" and frame.content[:2] == b"\xff\xd8"
        assert frame.headers["x-frame-count"] == "48"
        parts = client.get(f"{base}/script").json()
        assert "core.std.Crop" in parts["script"] and parts["body"][0].startswith("clip = core.std.Crop")
        assert not parts["custom"] and parts["script"] == "\n".join(parts["head"] + parts["body"] + parts["tail"]) + "\n"
        checked = client.get(f"{base}/check").json()
        assert checked["ok"] and checked["info"]["frames"] == 48 and checked["info"]["format"] == "YUV420P8"

        def run(custom):
            video = client.get(f"/api/jobs/{job_id}").json()["spec"]["video"] | {"custom": custom}
            client.patch(f"/api/jobs/{job_id}", json={"video": video})
            return client.get(f"{base}/check").json()

        head = len(parts["head"])
        bad = run("clip = src\nclip = core.std.Crop(clip, left=1000)")  # wider than the clip
        assert not bad["ok"] and bad["line"] == head + 2 and "Crop" in bad["error"]
        assert client.get(f"{base}/info").status_code == 422
        assert client.get(f"{base}/info").json()["detail"].startswith(f"Line {head + 2}: ")
        assert run("clip = src[:10]\nclip = (")["line"] == head + 2  # a syntax error
        not_a_clip = run("clip = 1")  # fails in the generated tail (the depth conversion)
        assert not_a_clip["line"] > head + 1 and "the body must leave a video clip" in not_a_clip["error"]
        assert client.get(f"{base}/script").json()["custom"]
        assert run("clip = src[5:15]")["info"]["frames"] == 10
