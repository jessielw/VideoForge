"""The web server: jobs API, queue worker, events, restart recovery, folder browser, video preview.

Probing and running are faked (Services); the video preview tests use the real
VapourSynth on an ffmpeg-made clip and skip without the tools.
"""

from __future__ import annotations

import shutil
import subprocess
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


def make_client(tmp_path: Path, run=None, records=None) -> TestClient:
    services = Services(probe=fake_probe, run=run or FakeRun(),
                        record=(records.append if records is not None else None))
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
        assert job["tracks"]["audio"][0]["detected"] == flags

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


def test_folder_browser(tmp_path):
    make_files(tmp_path)
    with make_client(tmp_path) as client:
        listing = client.get("/api/fs/list", params={"path": str(tmp_path / "src"), "extensions": ".mkv"}).json()
        assert [f["name"] for f in listing["files"]] == ["Show.S01E01.mkv"]
        assert listing["parent"] == str(tmp_path)
        assert client.get("/api/fs/list", params={"path": "C:\\Windows"}).status_code == 403
        assert client.get("/api/fs/roots").json() == [str(tmp_path)]


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
