"""The web server: jobs API, queue worker, events, restart recovery, folder browser, video preview.

Probing and running are faked (Services); the video preview tests use the real
VapourSynth on an ffmpeg-made clip and skip without the tools.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

from conftest import audio, source, sub
from fastapi.testclient import TestClient
import pytest
from test_pipeline import fake_tool_files

from videoforge.core.config import PROJECT_ROOT, AppConfig, Tools
from videoforge.core.events import JobFinished
from videoforge.core.execute.process import Cancelled, ToolError
from videoforge.core.job import JobResult, JobSpec, JobStatus, StepRecord, StepStatus, planned_encode
from videoforge.core.jobs import ProbedInputs, external_tracks
from videoforge.core.models import AudioCodec as C, SubFormat as F, VideoInfo
from videoforge.core.pipeline.steps import Step, StepProgress
from videoforge.core.video.settings import Crop
from videoforge.core.workdir import keep_records, note_finished, work_dir
from videoforge.profiles.manual import ManualProfile
from videoforge.server.app import create_app
from videoforge.server.queue import Services
from videoforge.server.settings import ServerSettings

# Empty files for the muxer and the DDP / ffmpeg encodes (the faked runs never start them); qaac stays missing.
_TOOLS = fake_tool_files("mkvmerge", "deezy", "dee", "truehdd", "ffmpeg")
APP = AppConfig(
    tools=Tools(
        mkvmerge=_TOOLS["mkvmerge"],
        deezy=_TOOLS["deezy"],
        dee=_TOOLS["dee"],
        truehdd=_TOOLS["truehdd"],
        qaac="qaac64",
        ffmpeg=_TOOLS["ffmpeg"],
        vs_plugins=str(PROJECT_ROOT / "tools" / "vs-plugins"),
    ),
    profile="manual",
)


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

    def __call__(self, spec, plan, profile, app, *, state, log, cancel, progress, on_record, on_step, step_log):
        self.runs.append(spec.name)
        step = Step("video", "Video (x264)", argvs=(("x264", "--crf", "18"),))
        run = step.to_run()
        state.run = [run]
        on_step(run)
        run.status = StepStatus.RUNNING
        on_step(run)
        log("== 1/1 Video (x264)")
        run.log("[x264] [ 50.0%] 1/2 frames")  # as run_steps keeps a step's tail
        step_log(run, "[x264] [ 50.0%] 1/2 frames")
        progress(StepProgress(0, 1, step, 0.5, 0.5, fps=24.0, eta=10))
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


def make_client(tmp_path: Path, run=None, detect_crop=None, runner=None, send=None) -> TestClient:
    services = Services(probe=fake_probe, run=run or FakeRun(), detect_crop=detect_crop)
    if runner is not None:
        services.runner = runner
    if send is not None:
        services.send_notification = send
    app = create_app(
        ServerSettings(data_dir=tmp_path / "data", roots=[tmp_path], frontend_dir=tmp_path / "none"),
        APP,
        services=services,
        setup_vapoursynth=False,
    )
    return TestClient(app)


def test_health_gives_the_version(tmp_path):
    from videoforge import version

    assert make_client(tmp_path).get("/api/health").json() == {"ok": True, "version": version()}


def wait_for(client: TestClient, job_id: str, *statuses: str, timeout: float = 5) -> dict:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in statuses:
            return job
        time.sleep(0.02)
    raise AssertionError(f"{job_id} stayed {job['status']}, wanted {statuses}")


def add(client: TestClient, root: Path, **extra) -> list[str]:
    body = {
        "sources": [str(root / "src")],
        "subtitles": [str(root / "src")],
        "profile": "manual",
        "original_language": "ja",
        "output_dir": str(root / "out"),
    } | extra
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
        assert Path(job["plan"]["encode_path"]).parts[-2:] == ("Show.S01E01.mkv_tmp", "video.264")
        assert [s["key"] for s in job["tracks"]["subs"]][:2] == ["id:10", "id:11"]
        flags = {"default": False, "forced": False, "hearing_impaired": False, "commentary": False, "original": False}
        assert job["tracks"]["subs"][0]["detected"] == flags
        assert job["tracks"]["audio"][0]["detected"] == flags | {"visual_impaired": False}  # audio description

        # Crop the video: the planned encode shrinks, the plan follows (no re-probe).
        video = job["spec"]["video"] | {"crop": {"left": 0, "top": 140, "right": 0, "bottom": 140}}
        edited = client.patch(f"/api/jobs/{ids[0]}", json={"video": video}).json()
        assert edited["crop"] == {"left": 0, "top": 140, "right": 0, "bottom": 140} and not edited["custom_script"]
        # A custom body ignores the crop fields, so the summary names the script instead.
        custom = client.patch(f"/api/jobs/{ids[0]}", json={"video": video | {"custom": "clip = src"}}).json()
        assert custom["crop"] is None and custom["custom_script"]
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
        steps = ["script", "index", "script.info", "chapters", "video", "mux"]  # audio is copied
        assert [c["id"] for c in commands] == steps
        assert "--crf 17" in commands[4]["command"] and " | " in commands[4]["command"]
        assert client.patch(f"/api/jobs/{ids[0]}", json={"encoder": {"rate_control": "nope"}}).status_code == 422
        assert edited["output_name"] == "Show.S01E01.mkv"
        labelled = client.patch(f"/api/jobs/{ids[0]}", json={"label": ' dubbed? "JA" '}).json()
        assert labelled["spec"]["label"] == "dubbed JA"  # what a file name can't hold is dropped
        assert labelled["output_name"] == "Show.S01E01.dubbed JA.mkv"
        mux = client.get(f"/api/jobs/{ids[0]}/commands").json()[-1]["command"]
        assert "Show.S01E01.dubbed JA.mkv.partial" in mux
        # Its own name in place of the source's; the label still goes after it, the container's extension too.
        named = client.patch(f"/api/jobs/{ids[0]}", json={"output_name": " My Show: Pilot.MKV "}).json()
        assert named["spec"]["output_name"] == "My Show Pilot"
        assert named["output_name"] == "My Show Pilot.dubbed JA.mkv"
        client.post("/api/jobs/apply", json={"ids": ids, "output_name": "Same"})  # per job: a batch leaves it
        assert client.get(f"/api/jobs/{ids[1]}").json()["spec"]["output_name"] == ""
        assert client.patch(f"/api/jobs/{ids[0]}", json={"output_name": ""}).json()["output_name"] == (
            "Show.S01E01.dubbed JA.mkv"
        )
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

        job = client.patch(
            f"/api/jobs/{job_id}", json={"inputs": {"subtitles": subs, "chapters": str(chapters)}}
        ).json()
        assert job["status"] in ("ready", "warn")  # read at once, no re-probe
        added = [s for s in job["tracks"]["subs"] if s["external_path"]]
        assert [(Path(s["external_path"]).name, s["format"], s["language"]) for s in added] == [
            ("Show.S01E01.en.srt", "srt", "en"),
            ("Show.fr.srt", "srt", "fr"),
            ("Signs.ass", "ass", "und"),
        ]
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


def test_progress_guesses_the_jobs_time_left(tmp_path, monkeypatch):
    import videoforge.server.queue as queue_module

    make_files(tmp_path, "S01E01")
    with make_client(tmp_path) as client:
        (job_id,) = add(client, tmp_path)
        wait_for(client, job_id, "ready", "warn")
        queue = client.app.state.queue
        entry = queue.get(job_id)
        clock = [100.0]
        monkeypatch.setattr(queue_module, "_now", lambda: clock[0])
        progress = queue._progress(entry)
        step = Step("video", "Video (x264)")
        progress(StepProgress(0, 3, step, 1.0, 0.4, reused=True))  # done in an earlier run: no time spent
        progress(StepProgress(1, 3, step, 0.0, 0.4))
        assert entry.progress["left"] is None
        clock[0] = 130.0
        progress(StepProgress(1, 3, step, 0.5, 0.6))  # 0.2 in 30 s: 0.4 left takes 60 s
        assert (entry.progress["elapsed"], entry.progress["left"]) == (30, 60)


def test_queue_runs_jobs_and_streams_events(tmp_path):
    make_files(tmp_path, "S01E01", "S01E02")
    with make_client(tmp_path) as client:
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
            p = next(ev for ev in events if ev["type"] == "progress")
            assert (p["step"], p["overall"], p["fps"], p["eta"], p["elapsed"]) == ("Video (x264)", 0.5, 24.0, 10, 0)
            assert p["left"] is None  # too soon to guess the job's time left
            # The worker's last queue event says the queue stopped (it once said running until a reload).
            while not ((ev := ws.receive_json())["type"] == "queue" and ev["queued"] == 0 and ev["current"] is None):
                pass
            assert ev["running"] is False
        for i in ids:
            job = wait_for(client, i, "done")
            assert job["steps"]["video"]["fingerprint"] == "abc"
        log = client.get(f"/api/jobs/{ids[0]}/log").json()["lines"]
        assert "[x264] [ 50.0%] 1/2 frames" in log
        (step,) = client.get(f"/api/jobs/{ids[0]}/steps").json()
        assert (step["status"], step["command"], step["exit_code"]) == ("done", "x264 --crf 18", 0)
        assert step["lines"] == ["[x264] [ 50.0%] 1/2 frames"] and not step["partial"]  # not the header
        text_log = (tmp_path / "src" / "Show.S01E01.mkv_tmp" / "videoforge.log").read_text(encoding="utf-8")
        last = text_log.splitlines()[-1]
        assert last[:9].count(":") == 2 and last[9:] == f"Job complete: {tmp_path / 'out' / 'Show.S01E01.mkv'}"
        work = tmp_path / "src" / "Show.S01E01.mkv_tmp"
        record = json.loads((work / "Show.S01E01.mkv.videoforge.json").read_text(encoding="utf-8"))
        assert record["run"]["status"] == "done" and record["job"]["id"] == ids[0]
        assert [s["id"] for s in record["steps"]] == ["video"]
        assert f"Job record: {work / 'Show.S01E01.mkv.videoforge.json'}" in text_log
        stream = (tmp_path / "data" / "logs" / "events.jsonl").read_text(encoding="utf-8").splitlines()
        kinds = [(e["job"], e["event"]) for e in map(json.loads, stream)]
        for i in ids:
            assert [k for j, k in kinds if j == i] == ["run.started", "step.started", "step.finished", "run.finished"]

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


def test_notifications(tmp_path):
    """Destinations are saved with the events they want; a run tells the ones that want its job's end and
    the queue's; a failed send is retried; the Test button reports Apprise's reason."""
    make_files(tmp_path, "S01E01", "S01E02")
    sent: list[tuple[str, str, str]] = []
    failing = {"json://down"}

    def send(url, message):
        sent.append((url, message.event.value, message.title))
        return "Connection refused" if url in failing else None

    with make_client(tmp_path, send=send) as client:
        assert client.get("/api/config").json()["notifications"] == []
        assert {e["id"] for e in client.get("/api/config").json()["notification_events"]} >= {"job_done"}
        destinations = [
            {"name": "Phone", "url": "ntfy://videoforge", "events": ["queue_finished"]},
            {"url": "discord://1/abc"},  # no name, no events: its scheme, and the default events
            {"name": "Off", "url": "json://localhost", "enabled": False},
            {"name": "Down", "url": "json://down", "events": ["job_done"]},
        ]
        saved = client.put("/api/config", json={"notifications": destinations}).json()["notifications"]
        assert [d["name"] for d in saved] == ["Phone", "discord", "Off", "Down"]
        assert saved[1]["events"] == ["job_done", "job_failed", "queue_finished"]
        bad = client.put("/api/config", json={"notifications": [{"url": "nope"}]})
        assert bad.status_code == 422 and "recognise" in bad.json()["detail"]
        assert (
            client.put("/api/config", json={"notifications": [{"url": "json://x", "events": ["x"]}]}).status_code == 422
        )

        client.app.state.notifier.retry_wait = 0
        ids = add(client, tmp_path)
        for i in ids:
            wait_for(client, i, "ready", "warn")
        client.post("/api/queue/start")
        for i in ids:
            wait_for(client, i, "done")
        client.app.state.queue.wait(5)
        client.app.state.notifier.wait()
        assert sorted(sent) == sorted(
            [
                ("discord://1/abc", "job_done", "Done: Show.S01E01.mkv"),
                ("discord://1/abc", "job_done", "Done: Show.S01E02.mkv"),
            ]
            + [("json://down", "job_done", f"Done: Show.S01E0{n}.mkv") for n in (1, 2) for _ in range(3)]
            + [(u, "queue_finished", "Queue finished") for u in ("ntfy://videoforge", "discord://1/abc")]
        )

        sent.clear()
        assert client.post("/api/config/notifications/test", json={"url": "ntfy://videoforge"}).json() == {"ok": True}
        down = client.post("/api/config/notifications/test", json={"url": "json://down"})
        assert down.status_code == 400 and down.json()["detail"] == "Connection refused"
        assert [s[0] for s in sent] == ["ntfy://videoforge", "json://down"]  # no retry for a test
    with make_client(tmp_path) as client:  # kept across a restart
        assert [d["name"] for d in client.get("/api/config").json()["notifications"]] == [
            "Phone",
            "discord",
            "Off",
            "Down",
        ]


class WritingRun(FakeRun):
    """FakeRun that also writes the output file (for actions that move it)."""

    def __call__(self, spec, plan, profile, app, **kw):
        result = super().__call__(spec, plan, profile, app, **kw)
        if result.output is not None:
            result.output.parent.mkdir(parents=True, exist_ok=True)
            result.output.write_bytes(b"mkv")
        return result


def test_actions_and_plugins(tmp_path):
    """Actions are saved and run after each job (a move shows in the job's log and events.jsonl); a plugin
    in the data folder hears the run; switching one off is saved and asks for a restart."""
    make_files(tmp_path)
    plugin = tmp_path / "data" / "plugins" / "spy"
    plugin.mkdir(parents=True)
    (plugin / "videoforge-plugin.toml").write_text('id = "spy"\nmodule = "vf_spy_plugin"\n', encoding="utf-8")
    (plugin / "vf_spy_plugin.py").write_text(
        "from videoforge.plugins import Plugin\n"
        "seen = []\n"
        "def done(event, ctx):\n"
        "    seen.append((event.status.value, event.output.name))\n"
        "    ctx.job_log(event.spec.id, 'spy saw it')\n"
        "plugin = Plugin(name='Spy', version='0.1', on_job_finished=done)\n",
        encoding="utf-8",
    )
    with make_client(tmp_path, run=WritingRun()) as client:
        state = client.get("/api/config").json()
        assert state["actions"] == [] and state["allow_commands"] is False
        assert {k["id"] for k in state["action_kinds"]} == {"command", "move", "copy", "webhook"}
        assert [p["id"] for p in state["plugins"]["loaded"]] == ["spy"]
        assert state["plugins"]["folder"] == str(tmp_path / "data" / "plugins")

        bad = client.put("/api/config", json={"actions": [{"kind": "command", "target": "x {nope}"}]})
        assert bad.status_code == 422 and "Unknown token {nope}" in bad.json()["detail"]
        library = tmp_path / "library"
        saved = client.put(
            "/api/config", json={"actions": [{"name": "To library", "kind": "move", "target": str(library)}]}
        ).json()["actions"]
        assert saved == [
            {
                "name": "To library",
                "kind": "move",
                "target": str(library),
                "enabled": True,
                "events": ["job_done"],
                "overwrite": False,
            }
        ]

        [job] = add(client, tmp_path)
        wait_for(client, job, "ready", "warn")
        client.post("/api/queue/start")
        wait_for(client, job, "done")
        client.app.state.queue.wait(5)
        client.app.state.actions.wait()
        client.app.state.plugins.wait()
        assert (library / "Show.S01E01.mkv").read_bytes() == b"mkv"
        assert not (tmp_path / "out" / "Show.S01E01.mkv").exists()
        lines = client.get(f"/api/jobs/{job}/log").json()["lines"]
        assert f"Action 'To library': moved to {library / 'Show.S01E01.mkv'}" in lines
        assert "spy saw it" in lines
        assert sys.modules["vf_spy_plugin"].seen == [("done", "Show.S01E01.mkv")]
        events = [json.loads(x) for x in (tmp_path / "data" / "logs" / "events.jsonl").read_text("utf-8").splitlines()]
        moved = next(e for e in events if e["event"] == "action.finished")
        assert moved["action"] == "To library" and moved["type"] == "move" and moved["error"] is None

        off = client.put("/api/config", json={"disabled_plugins": ["spy"]}).json()
        assert off["plugins"]["loaded"][0]["enabled"] is False and len(off["restart"]) == 1
        assert client.put("/api/config", json={"disabled_plugins": []}).json()["restart"] == []
        client.put("/api/config", json={"disabled_plugins": ["spy"]})
    with make_client(tmp_path) as client:  # kept across a restart; the plugin is found but not loaded
        state = client.get("/api/config").json()
        assert [a["name"] for a in state["actions"]] == ["To library"]
        assert state["plugins"]["loaded"] == [] and [p["id"] for p in state["plugins"]["disabled"]] == ["spy"]
        assert state["restart"] == []


class EncodingRun(WritingRun):
    """WritingRun that leaves an encode in the work folder, as a real run does."""

    def __call__(self, spec, plan, profile, app, **kw):
        spec.work_dir.mkdir(exist_ok=True)
        (spec.work_dir / "video.264").write_bytes(b"264")
        return super().__call__(spec, plan, profile, app, **kw)


class KeepSpyRun(EncodingRun):
    """EncodingRun that notes what each run was told to keep and which step records it started with."""

    def __init__(self):
        super().__init__()
        self.seen: list[tuple[list[str], set[str]]] = []

    def __call__(self, spec, plan, profile, app, **kw):
        self.seen.append((list(kw["state"].keep), set(kw["state"].steps)))
        return super().__call__(spec, plan, profile, app, **kw)


def test_reuse_question(tmp_path):
    """/reuse lists what a start's jobs could reuse (a file another run finished counts, with other settings
    too); /start's `reuse` keeps the chosen sections and drops the records of the others."""
    make_files(tmp_path, "S01E01", "S01E02")
    run = KeepSpyRun()
    with make_client(tmp_path, run=run) as client:
        one, two = add(client, tmp_path)
        for job in (one, two):
            wait_for(client, job, "ready", "warn")
        q = client.app.state.queue
        assert client.post("/api/queue/reuse", json={"ids": [one]}).json() == {"jobs": []}

        video = q.get(one).spec.video_output
        video.parent.mkdir()
        video.write_bytes(b"264")
        note_finished(video.parent, "video", "made with other settings", [video], 12.0)
        jobs = client.post("/api/queue/reuse", json={}).json()["jobs"]  # Start queue: every runnable job
        assert [(j["id"], j["name"]) for j in jobs] == [(one, "Show.S01E01.mkv")]
        (offer,) = jobs[0]["offers"]
        assert (offer["id"], offer["file"], offer["size"], offer["seconds"]) == ("video", str(video), 3, 12.0)
        assert offer["current"] is False and offer["label"] == "Video (x264)"

        client.post("/api/queue/start", json={"ids": [one], "reuse": {one: ["video"]}})
        q.wait(5)
        assert run.seen[-1][0] == ["video"]

        q.get(one).state.steps["video"] = StepRecord("video", "old", [video])
        client.post("/api/queue/start", json={"ids": [one], "reuse": {one: []}})  # made again
        q.wait(5)
        assert run.seen[-1] == ([], set())
        assert client.post("/api/queue/reuse", json={"ids": [two]}).json() == {"jobs": []}


def test_work_folders(tmp_path):
    """Off by default: a done job keeps its work folder. On: it's deleted after its record and log are copied
    to <data dir>/records, and the record path actions get is the copy. Removing jobs can delete theirs."""
    make_files(tmp_path, "S01E01", "S01E02", "S01E03")
    records = tmp_path / "data" / "records"
    finished = []
    with make_client(tmp_path, run=EncodingRun()) as client:
        client.app.state.queue.bus.subscribe(finished.append, JobFinished, name="spy")
        cfg = client.get("/api/config").json()
        assert (cfg["delete_work_dir"], cfg["delete_work_dir_default"]) == (False, False)
        assert cfg["records_dir"] == str(records)
        one, two, three = add(client, tmp_path)
        work = {i: tmp_path / "src" / f"Show.S01E0{n}.mkv_tmp" for n, i in enumerate((one, two, three), 1)}
        for job in (one, two, three):
            wait_for(client, job, "ready", "warn")

        client.post("/api/queue/start", json={"ids": [one]})
        wait_for(client, one, "done")
        client.app.state.queue.wait(5)
        assert (work[one] / "video.264").is_file() and not records.exists()

        assert client.put("/api/config", json={"delete_work_dir": "yes"}).status_code == 422
        assert client.put("/api/config", json={"delete_work_dir": True}).json()["delete_work_dir"] is True
        client.post("/api/queue/start", json={"ids": [two]})
        wait_for(client, two, "done")
        client.app.state.queue.wait(5)
        assert not work[two].exists()
        record = records / "Show.S01E02.mkv.videoforge.json"
        assert json.loads(record.read_text("utf-8"))["output"]["path"].endswith("Show.S01E02.mkv")
        assert "Job complete:" in (records / "Show.S01E02.mkv.videoforge.log").read_text("utf-8")
        assert finished[-1].record == record
        assert any(
            line.startswith("Work folder deleted: ") for line in client.get(f"/api/jobs/{two}/log").json()["lines"]
        )
        client.app.state.queue.job_log(two, "an action's line")  # doesn't make the folder again
        assert not work[two].exists()

        r = client.post("/api/jobs/remove", json={"ids": [one, three], "work_dirs": True}).json()
        assert r == {"removed": [one, three], "deleted": [str(work[one])], "kept": {}}  # three never had one
        assert not work[one].exists()
        assert client.post("/api/jobs/remove", json={"ids": [two]}).json()["deleted"] == []
    with make_client(tmp_path) as client:  # kept across a restart
        assert client.get("/api/config").json()["delete_work_dir"] is True


def test_keep_records_keeps_the_newest(tmp_path):
    dest = tmp_path / "records"
    for n in range(3):
        source = tmp_path / f"s{n}.mkv"
        work_dir(source).mkdir()
        (work_dir(source) / "videoforge.log").write_text("log", encoding="utf-8")
        (work_dir(source) / f"s{n}.mkv.videoforge.json").write_text("{}", encoding="utf-8")
        copied = keep_records(source, dest, keep=2)
        for path in copied.values():
            os.utime(path, (n + 1, n + 1))  # the earlier copies are older
    assert copied == {
        "s2.mkv.videoforge.json": dest / "s2.mkv.videoforge.json",
        "videoforge.log": dest / "s2.mkv.videoforge.log",
    }
    assert sorted(p.name for p in dest.iterdir()) == [
        "s1.mkv.videoforge.json",
        "s1.mkv.videoforge.log",
        "s2.mkv.videoforge.json",
        "s2.mkv.videoforge.log",
    ]


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
        def __call__(self, spec, plan, profile, app, *, state, log, cancel, progress, on_record, on_step, step_log):
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
    with make_client(tmp_path) as client:  # APP's qaac64 doesn't exist
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
        assert not changed["restart"]  # the preview worker restarts with the new folder

        assert (cfg["parallel_audio"], cfg["parallel_audio_default"]) == (2, 2)
        assert client.put("/api/config", json={"parallel_audio": 0}).json()["parallel_audio"] == 0
        assert client.app.state.queue.app.parallel_audio == 0  # new runs use it
        for bad in (-1, 9, 1.5, "2", True):
            assert client.put("/api/config", json={"parallel_audio": bad}).status_code == 422

    with make_client(tmp_path) as client:  # kept across a restart
        cfg = client.get("/api/config").json()
        assert {t["name"]: t for t in cfg["tools"]}["x264"]["custom"] == sys.executable
        assert cfg["roots"] == [str(folder)] and cfg["parallel_audio"] == 0
        assert client.app.state.queue.app.parallel_audio == 0
        reset = client.put(
            "/api/config", json={"tools": {"x264": None}, "roots": None, "profile": None, "parallel_audio": None}
        ).json()
        assert {t["name"]: t for t in reset["tools"]}["x264"]["path"] == "x264" and not reset["roots_custom"]
        assert reset["parallel_audio"] == 2


def test_presets(tmp_path):
    with make_client(tmp_path) as client:
        assert client.get("/api/presets").json() == {
            "video": [],
            "encoder": [],
            "template": [],
            "template_defaults": {},
        }
        saved = client.put(
            "/api/presets/encoder/Fast x265", json={"encoder": "x265", "crf": 20, "preset": "fast"}
        ).json()
        (enc,) = saved["encoder"]
        assert enc["name"] == "Fast x265" and enc["data"]["crf"] == 20 and enc["data"]["depth"] == 8  # filled in
        video = {
            "source_filter": "lsmash",
            "crop": {"left": 2, "top": 0, "right": 0, "bottom": 0},
            "resize": {"width": 1280, "height": 720},
            "filters": "clip = clip",
        }
        (vid,) = client.put("/api/presets/video/720p", json=video).json()["video"]
        assert "crop" not in vid["data"] and vid["data"]["resize"]["kernel"] == "Spline36"
        assert [f["category"] for f in vid["data"]["filters"]] == ["crop", "resize", "custom"]  # the old text, upgraded

        assert client.put("/api/presets/audio/x", json={}).status_code == 404
        assert client.put("/api/presets/encoder/%20", json={}).status_code == 422
        assert client.put("/api/presets/encoder/bad", json={"rate_control": "nope"}).status_code == 422

    with make_client(tmp_path) as client:  # kept across a restart
        assert [p["name"] for p in client.get("/api/presets").json()["encoder"]] == ["Fast x265"]
        assert client.delete("/api/presets/encoder/Fast x265").json()["encoder"] == []


def test_keep_ar_resize_is_fitted_on_the_server(tmp_path):
    """A keep-AR resize's height follows each crop change (and the probe), whatever height was sent."""
    make_files(tmp_path, "S01E01")
    with make_client(tmp_path) as client:
        (job_id,) = add(client, tmp_path)
        video = wait_for(client, job_id, "ready", "warn")["spec"]["video"]
        resize = {"width": 1280, "height": 720, "kernel": "Spline36", "keep_ar": True, "mod": 2}
        bars = {"left": 0, "top": 140, "right": 0, "bottom": 140}
        client.patch(f"/api/jobs/{job_id}", json={"video": video | {"crop": bars, "resize": resize}})
        job = client.get(f"/api/jobs/{job_id}").json()
        assert job["spec"]["video"]["resize"]["height"] == 534
        client.patch(
            f"/api/jobs/{job_id}",
            json={"video": job["spec"]["video"] | {"crop": {"left": 0, "top": 0, "right": 0, "bottom": 0}}},
        )
        assert client.get(f"/api/jobs/{job_id}").json()["spec"]["video"]["resize"]["height"] == 720


def test_templates(tmp_path):
    """A template sets the whole run when jobs are added or on a batch; its auto crop is detected per
    job afterwards, on the index lane after the index (the job can't be queued meanwhile), and a crop set
    by hand meanwhile wins."""
    make_files(tmp_path, "S01E01", "S01E02")
    indexer = FakeIndexer()
    gate = threading.Event()
    gate.set()

    def detect_crop(spec):
        assert gate.wait(5)
        return Crop(0, 20, 0, 22)

    template = {
        "video": {"filters": "clip = clip", "crop": {"left": 4, "top": 0, "right": 4, "bottom": 0}},
        "encoder": {"encoder": "x265", "crf": 16},
        "mux": {"container": "mkv", "extra": "-x"},
        "qpf": False,
        "crop_mode": "auto",
    }
    with make_client(tmp_path, detect_crop=detect_crop, runner=indexer) as client:
        ids = add(client, tmp_path, template=template)
        for job_id in ids:
            job = wait_for(client, job_id, "ready", "warn", "blocked")
            assert job["status"] != "blocked", job["issues"] if "issues" in job else job["plan"]["issues"]
            spec = job["spec"]
            assert spec["encoder"]["encoder"] == "x265" and spec["encoder"]["crf"] == 16
            assert spec["mux"] == {"container": "mkv", "extra": "-x"} and spec["qpf"] is False
            assert [(f["category"], f["script"]) for f in spec["video"]["filters"]] == [  # the old text, upgraded
                ("crop", ""),
                ("resize", ""),
                ("custom", "clip = clip"),
            ]
            assert spec["video"]["crop"] == {"left": 0, "top": 20, "right": 0, "bottom": 22} and not spec["autocrop"]
            assert job["indexed"]  # the lane indexed it first, one job at a time
        assert len(indexer.calls) == 2

        # A batch: fixed crop on both; then the container alone keeps each job's extra arguments.
        fixed = template | {"crop_mode": "fixed"}
        assert client.post("/api/jobs/apply", json={"ids": ids, "template": fixed}).json()["updated"] == ids
        assert {client.get(f"/api/jobs/{i}").json()["spec"]["video"]["crop"]["left"] for i in ids} == {4}
        client.patch(f"/api/jobs/{ids[0]}", json={"mux": {"container": "mp4", "extra": "-y"}})
        client.post("/api/jobs/apply", json={"ids": ids, "container": "mkv"})
        assert [client.get(f"/api/jobs/{i}").json()["spec"]["mux"] for i in ids] == [
            {"container": "mkv", "extra": "-y"},
            {"container": "mkv", "extra": "-x"},
        ]

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
        assert [t["name"] for t in listed["template"]] == ["Show 1080p"] and listed["template_defaults"] == {
            "manual": "Show 1080p"
        }
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
    template = {
        "audio": {
            "slots": [
                {"track": {"title": "Japanese"}},
                {"track": {}, "extra": [{"action": "ddp", "layout": "5.1", "bitrate_kbps": 640, "title": "DDP 5.1"}]},
                {"track": {"action": "aac"}},  # no third track: ignored
            ]
        }
    }
    with make_client(tmp_path) as client:
        (job_id,) = add(client, tmp_path, template=template)
        job = wait_for(client, job_id, "ready", "warn")
        assert [(a["action"], a["title"]) for a in job["plan"]["audio"]] == [
            ("copy", "Japanese"),
            ("copy", ""),
            ("ddp", "DDP 5.1"),
        ]
        assert job["spec"]["audio_template"] is None and job["spec"]["overrides"]["copies"] == ["id:2+1"]
        # What the template set stays on the job, for the track editor (both source tracks and the copy).
        chosen = job["spec"]["audio_from_template"]
        assert sorted(chosen["tracks"]) == ["id:1", "id:2", "id:2+1"] and chosen["copies"] == ["id:2+1"]
        assert chosen["tracks"]["id:1"]["title"] == "Japanese" and chosen["tracks"]["id:2"]["action"] is None
        assert chosen["tracks"]["id:2+1"]["action"] == "ddp" and job["spec"]["subs_from_template"] is None

        overrides = job["spec"]["overrides"] | {"tracks": {"id:1": {"title": "Mine"}}}
        client.patch(f"/api/jobs/{job_id}", json={"overrides": overrides})
        others = {"audio": {"slots": [{"track": {"action": "flac"}}], "others": "exclude"}}
        client.post("/api/jobs/apply", json={"ids": [job_id], "template": others})
        job = client.get(f"/api/jobs/{job_id}").json()
        assert [(a["action"], a["title"]) for a in job["plan"]["audio"]] == [("flac", "")]  # "Mine" replaced
        chosen = job["spec"]["audio_from_template"]
        assert (
            chosen["copies"] == []
            and chosen["tracks"]["id:2"]["exclude"]
            and chosen["tracks"]["id:1"]["action"] == "flac"
        )


def test_template_audio_rules(tmp_path):
    """Audio by rules once the tracks are known: "original" is the profile's guess (the first track's
    language, ja), pinned before the rules run; output in rule order, one default."""
    make_files(tmp_path, "S01E01")  # ja FLAC 2.0, en TrueHD 5.1
    template = {
        "audio": {
            "mode": "rules",
            "others": "exclude",
            "rules": [
                {
                    "original": False,
                    "min_channels": 6,
                    "track": {"action": "ddp", "title": "English", "flags": {"default": True}},
                },
                {"original": True, "first_only": True, "track": {"title": "Japanese", "flags": {"default": True}}},
            ],
        }
    }
    with make_client(tmp_path) as client:
        (job_id,) = add(client, tmp_path, template=template, original_language=None)
        job = wait_for(client, job_id, "ready", "warn")
        assert [(a["action"], a["title"], a["default"]) for a in job["plan"]["audio"]] == [
            ("ddp", "English", True),
            ("copy", "Japanese", False),
        ]
        spec = job["spec"]
        assert spec["overrides"]["original_language"] == "ja" and spec["audio_template"] is None
        assert spec["overrides"]["order"] == ["id:2", "id:1"] and sorted(spec["audio_from_template"]["tracks"]) == [
            "id:1",
            "id:2",
        ]


def test_template_audio_fits_each_track(tmp_path):
    """One template suits sources with less audio: a slot asking for more than its track has is fitted
    to it instead of blocking the job. The same settings set by hand still block."""
    make_files(tmp_path, "S01E01")  # FLAC 2.0, TrueHD 5.1 without Atmos
    ddp51 = {"action": "ddp", "layout": "5.1", "bitrate_kbps": 640}
    template = {"audio": {"slots": [{"track": ddp51}, {"track": {"action": "atmos", "bitrate_kbps": 768}}]}}
    with make_client(tmp_path) as client:
        (job_id,) = add(client, tmp_path, template=template)
        job = wait_for(client, job_id, "ready", "warn", "blocked")
        assert job["status"] != "blocked", job["issues"]
        assert [(a["action"], a["out_layout"], a["bitrate_kbps"]) for a in job["plan"]["audio"]] == [
            ("ddp", "2.0", 256),
            ("ddp", "5.1", 640),
        ]

        overrides = job["spec"]["overrides"] | {"tracks": {"id:1": ddp51}}
        job = client.patch(f"/api/jobs/{job_id}", json={"overrides": overrides}).json()
        assert job["status"] == "blocked" and any(i["code"] == "audio.upmix" for i in job["issues"])


def test_template_subs(tmp_path):
    """A template's subtitle rules set each job's subtitles once its tracks are known, added files too:
    first matching rule wins, rule order, one default. A batch apply replaces the earlier choices."""
    make_files(tmp_path, "S01E01")  # en PGS, de PGS, and an added Show.S01E01.en.srt
    template = {
        "subs": {
            "rules": [
                {"languages": ["en"], "formats": ["srt"], "track": {"title": "Added", "flags": {"default": True}}},
                {"languages": ["en"], "track": {"flags": {"default": True}}},
            ],
            "others": "exclude",
        }
    }
    with make_client(tmp_path) as client:
        (job_id,) = add(client, tmp_path, template=template)
        job = wait_for(client, job_id, "ready", "warn")
        assert job["spec"]["subs_template"] is None
        assert [(s["language"], s["title"], s["default"]) for s in job["plan"]["subs"]] == [
            ("en", "Added", True),
            ("en", "English", False),
        ]  # German left out
        chosen = job["spec"]["subs_from_template"]
        assert chosen["order"] == ["ext:Show.S01E01.en.srt", "id:10"] and chosen["tracks"]["id:11"]["exclude"]

        overrides = job["spec"]["overrides"] | {"tracks": {"id:11": {"title": "Mine"}}}
        client.patch(f"/api/jobs/{job_id}", json={"overrides": overrides})
        keep = {"subs": {"rules": [{"languages": ["de"]}], "others": "keep"}}
        client.post("/api/jobs/apply", json={"ids": [job_id], "template": keep})
        job = client.get(f"/api/jobs/{job_id}").json()
        assert [(s["language"], s["title"]) for s in job["plan"]["subs"]] == [
            ("de", "German"),
            ("en", "English"),
            ("en", ""),
        ]  # "Mine" replaced; German first by rule


def test_template_audio_is_dropped_without_a_track_editor(tmp_path, monkeypatch):
    """A profile whose rules choose the tracks keeps its own picks: the template's audio and subtitles are dropped."""
    monkeypatch.setattr(ManualProfile, "track_editor", False)
    make_files(tmp_path, "S01E01")
    template = {
        "audio": {"slots": [{"track": {"exclude": True}}], "others": "exclude"},
        "subs": {"rules": [], "others": "exclude"},
    }
    with make_client(tmp_path) as client:
        (job_id,) = add(client, tmp_path, template=template)
        job = wait_for(client, job_id, "ready", "warn")
        assert job["spec"]["audio_template"] is None and job["spec"]["subs_template"] is None
        assert job["spec"]["overrides"]["tracks"] == {}
        assert job["spec"]["audio_from_template"] is None and job["spec"]["subs_from_template"] is None


class FakeIndexer:
    """The index lane's tool runner: logs vspipe's progress and writes the FFMS2 index. A job named in
    `hold` waits for its gate (or a cancel); one in `fail` fails."""

    def __init__(self, hold=(), fail=()):
        self.calls: list[tuple[str, ...]] = []
        self.gates = {name: threading.Event() for name in hold}
        self.fail = set(fail)

    def __call__(self, argvs, log, cancel=None):
        argv = argvs[0]
        self.calls.append(tuple(argv))
        work = Path(argv[-1]).parent  # FFMS2 (the default): ffindex <source> <cachefile>
        name = work.name.removesuffix("_tmp")
        log("[vspipe] Creating lwi index file 50%")
        gate = self.gates.get(name)
        while gate is not None and not gate.is_set():
            if cancel is not None and cancel.cancelled:
                raise Cancelled()
            time.sleep(0.01)
        if name in self.fail:
            raise ToolError("vspipe exited with code 1")
        Path(argv[-1]).write_bytes(b"index")

    def wait(self, calls: int, timeout: float = 5) -> None:
        end = time.monotonic() + timeout
        while len(self.calls) < calls:
            assert time.monotonic() < end, f"{len(self.calls)} index runs, wanted {calls}"
            time.sleep(0.01)


def test_preview_clips_are_released_before_the_index_lane_and_on_remove(tmp_path):
    """The index lane may write a file a preview clip holds open (a FEL's enhancement layer), and a removed
    job's work folder may be deleted next: the jobs' clips are freed first."""
    make_files(tmp_path, "S01E01")
    indexer = FakeIndexer()
    released = []
    with make_client(tmp_path, runner=indexer) as client:
        client.app.state.queue.services.release_preview = released.append
        [one] = add(client, tmp_path)
        wait_for(client, one, "ready", "warn")
        client.post("/api/queue/index", json={"ids": [one]})
        indexer.wait(1)
        assert wait_for(client, one, "ready", "warn")["indexed"]
        assert released == [[one]]
        client.post("/api/jobs/remove", json={"ids": [one], "work_dirs": True})
        assert released == [[one], [one]]


def test_index_lane(tmp_path):
    """Index runs the script and index steps only, one job at a time, next to the encode queue; the job's
    encode then reuses them. Its video opens at once afterwards (the summary's `indexed`)."""
    make_files(tmp_path, "S01E01", "S01E02", "S01E03")
    indexer = FakeIndexer(hold=["Show.S01E01.mkv"], fail=["Show.S01E03.mkv"])
    with make_client(tmp_path, runner=indexer) as client:
        ids = add(client, tmp_path)
        for i in ids:
            assert not wait_for(client, i, "ready", "warn")["indexed"]
        r = client.post("/api/queue/index", json={"ids": ids}).json()
        assert r["taken"] == ids
        indexer.wait(1)
        first = wait_for(client, ids[0], "indexing")
        assert first["progress"]["step"] == "Index the source"
        assert client.get(f"/api/jobs/{ids[1]}").json()["status"] == "index-queued"
        state = client.get("/api/queue").json()
        assert state["indexing"] == ids[0] and state["index_queued"] == 2
        assert client.post("/api/queue/index", json={"ids": ids}).json()["taken"] == []  # in the lane already

        # The encode queue runs meanwhile: a job waiting in the lane leaves it (its run indexes first);
        # the one being indexed can't be queued until it's done.
        client.post("/api/queue/start", json={"ids": [ids[1], ids[0]]})
        client.app.state.queue.wait(5)
        assert wait_for(client, ids[1], "done")
        assert client.get(f"/api/jobs/{ids[0]}").json()["status"] == "indexing"

        # Its video opens once it's indexed (only the lane indexes); its script shows meanwhile. It's locked.
        assert client.get(f"/api/jobs/{ids[0]}/video/script").status_code == 200
        assert client.get(f"/api/jobs/{ids[0]}/video/check").status_code == 409
        assert client.get(f"/api/jobs/{ids[2]}/video/frame").status_code == 409  # not indexed yet
        r = client.patch(f"/api/jobs/{ids[0]}", json={"qpf": False})
        assert r.status_code == 409 and "being indexed" in r.text
        indexer.gates["Show.S01E01.mkv"].set()
        done = wait_for(client, ids[0], "ready", "warn")
        checked = client.get(f"/api/jobs/{ids[0]}/video/check")
        assert checked.status_code == 200 and not checked.json()["ok"]  # opened (the test's source isn't a video)
        assert done["indexed"] and not done["index_error"]
        third = wait_for(client, ids[2], "ready", "warn")
        assert not third["indexed"] and "vspipe exited with code 1" in third["index_error"]
        assert client.get("/api/queue").json()["indexing"] is None

        q = client.app.state.queue
        e = q.get(ids[0])
        assert set(e.state.steps) == {"script", "index"} and e.state.status is None  # no run, no outcome
        assert (e.spec.work_dir / "video.vpy").is_file() and (e.spec.work_dir / "videoforge.log").is_file()
        assert [c[1:] for c in indexer.calls] == [
            (
                "-m",
                "videoforge.core.video.ffindex",
                str(q.get(i).spec.inputs.source),
                str(q.get(i).spec.work_dir / (q.get(i).spec.inputs.source.name + ".ffindex")),
            )
            for i in (ids[0], ids[2])
        ]
        assert any("index done" in line for line in e.log)
        stream = (tmp_path / "data" / "logs" / "events.jsonl").read_text(encoding="utf-8").splitlines()
        indexed = [
            (e["event"], e["job"], e.get("error")) for e in map(json.loads, stream) if e["event"].startswith("index.")
        ]
        assert indexed[:2] == [("index.started", ids[0], None), ("index.finished", ids[0], None)]
        assert indexed[-1][1] == ids[2] and "vspipe exited with code 1" in indexed[-1][2]

        # Indexing again reuses the steps while the index is there, and builds it again once it's gone.
        client.post("/api/queue/index", json={"ids": [ids[0]]})
        wait_for(client, ids[0], "ready", "warn")
        assert len(indexer.calls) == 2 and sum("index done" in line for line in e.log) == 2
        (e.spec.work_dir / "Show.S01E01.mkv.ffindex").unlink()
        assert not client.get(f"/api/jobs/{ids[0]}").json()["indexed"]
        client.post("/api/queue/index", json={"ids": [ids[0]]})
        indexer.wait(3)
        assert wait_for(client, ids[0], "ready", "warn")["indexed"]


def test_index_lane_stop(tmp_path):
    make_files(tmp_path, "S01E01", "S01E02")
    indexer = FakeIndexer(hold=["Show.S01E01.mkv"])
    with make_client(tmp_path, runner=indexer) as client:
        ids = add(client, tmp_path)
        for i in ids:
            wait_for(client, i, "ready", "warn")
        client.post("/api/queue/index", json={"ids": ids})
        indexer.wait(1)
        wait_for(client, ids[0], "indexing")
        assert client.post("/api/jobs/remove", json={"ids": [ids[0]]}).json()["removed"] == []  # busy indexing
        client.post("/api/queue/index/stop")
        for i in ids:
            job = wait_for(client, i, "ready", "warn")
            assert not job["indexed"] and not job["index_error"]  # cancelled: nothing to report
        assert len(indexer.calls) == 1
        assert client.get("/api/queue").json() | {"running": False} == {
            "running": False,
            "current": None,
            "stop_after_current": False,
            "queued": 0,
            "indexing": None,
            "index_queued": 0,
        }


def test_index_now_goes_first(tmp_path):
    """The editor's Index (first): ahead of the jobs waiting in the lane, also one already waiting."""
    make_files(tmp_path, "S01E01", "S01E02", "S01E03", "S01E04")
    indexer = FakeIndexer(hold=["Show.S01E01.mkv"])
    with make_client(tmp_path, runner=indexer) as client:
        ids = add(client, tmp_path)
        for i in ids:
            wait_for(client, i, "ready", "warn")
        client.post("/api/queue/index", json={"ids": ids[:3]})
        indexer.wait(1)
        assert client.post("/api/queue/index", json={"ids": [ids[3]], "first": True}).json()["taken"] == [ids[3]]
        assert client.post("/api/queue/index", json={"ids": [ids[2]], "first": True}).json()["taken"] == [ids[2]]
        indexer.gates["Show.S01E01.mkv"].set()
        indexer.wait(4)
        order = [Path(c[-1]).name.removesuffix(".mkv.ffindex") for c in indexer.calls]
        assert order == ["Show.S01E01", "Show.S01E03", "Show.S01E04", "Show.S01E02"]


def test_index_lane_waits_for_the_preview(tmp_path):
    """A job opened in the editor while it waits in the lane: the preview loading its clip holds the job's source
    lock, so the lane waits (it can still be stopped) and then finds the index there."""
    make_files(tmp_path, "S01E01", "S01E02")
    indexer = FakeIndexer()
    with make_client(tmp_path, runner=indexer) as client:
        ids = add(client, tmp_path)
        for i in ids:
            wait_for(client, i, "ready", "warn")
        q = client.app.state.queue
        first, second = q.get(ids[0]), q.get(ids[1])
        first.source_lock.acquire()  # the preview is indexing both
        second.source_lock.acquire()
        client.post("/api/queue/index", json={"ids": ids})
        wait_for(client, ids[0], "indexing")
        time.sleep(0.3)
        assert indexer.calls == [] and any("Waiting for the preview" in line for line in first.log)
        first.source_lock.release()
        indexer.wait(1)
        wait_for(client, ids[1], "indexing")
        client.post("/api/queue/index/stop")  # stops the wait
        assert not wait_for(client, ids[1], "ready", "warn")["index_error"]
        assert len(indexer.calls) == 1 and wait_for(client, ids[0], "ready", "warn")["indexed"]
        second.source_lock.release()


def test_index_lane_survives_a_restart(tmp_path):
    """The lane's jobs and order are kept: after a restart the job stopped mid-index goes again first, then the
    rest in order. Stopping the lane by hand empties it for good; a shutdown doesn't."""
    make_files(tmp_path, "S01E01", "S01E02", "S01E03")
    indexer = FakeIndexer(hold=["Show.S01E03.mkv"])
    with make_client(tmp_path, runner=indexer) as client:
        ids = add(client, tmp_path)
        for i in ids:
            wait_for(client, i, "ready", "warn")
        client.post("/api/queue/index", json={"ids": [ids[2]]})
        indexer.wait(1)
        wait_for(client, ids[2], "indexing")
        client.post("/api/queue/index", json={"ids": ids[:2]})
    assert not (tmp_path / "src" / "Show.S01E03.mkv_tmp" / "Show.S01E03.mkv.ffindex").exists()  # cancelled

    indexer = FakeIndexer()
    with make_client(tmp_path, runner=indexer) as client:
        store = client.app.state.store
        indexer.wait(3)  # (jobs still probing let the others go first, so the order isn't checked)
        for i in ids:
            assert wait_for(client, i, "ready", "warn")["indexed"]
        assert store.get_setting("index_lane") == []

        indexer.gates["Show.S01E01.mkv"] = threading.Event()
        (tmp_path / "src" / "Show.S01E01.mkv_tmp" / "Show.S01E01.mkv.ffindex").unlink()
        client.post("/api/queue/index", json={"ids": [ids[0]]})
        wait_for(client, ids[0], "indexing")
        assert store.get_setting("index_lane") == [ids[0]]
        client.post("/api/queue/index/stop")
        wait_for(client, ids[0], "ready", "warn")
        assert store.get_setting("index_lane") == []


def test_index_lane_waits_for_an_encode_on_its_disk(tmp_path, monkeypatch):
    """While an encode runs, a job whose source is on the encode's disk is held back (a job on another disk goes
    ahead); Index now doesn't wait; the setting turns it off; the encode ending lets the job go."""
    make_files(tmp_path, "S01E01", "S01E02", "S01E03", "S01E04")
    monkeypatch.setattr("videoforge.server.queue.disks", lambda p: frozenset({"y" if "S01E03" in str(p) else "x"}))
    indexer = FakeIndexer()
    with make_client(tmp_path, run=FakeRun(block=True), runner=indexer) as client:
        ids = add(client, tmp_path)
        for i in ids:
            wait_for(client, i, "ready", "warn")
        client.post("/api/queue/start", json={"ids": [ids[0]]})
        wait_for(client, ids[0], "running")
        client.post("/api/queue/index", json={"ids": ids[1:3]})
        indexer.wait(1)
        assert "S01E03" in indexer.calls[0][-1]  # another disk: it goes first
        wait_for(client, ids[1], "index-queued")
        time.sleep(0.3)
        assert client.get(f"/api/jobs/{ids[1]}").json()["index_held"] and len(indexer.calls) == 1

        client.post("/api/queue/index", json={"ids": [ids[3]], "first": True})  # Index now: no wait
        indexer.wait(2)
        assert "S01E04" in indexer.calls[1][-1]
        assert client.get(f"/api/jobs/{ids[1]}").json()["index_held"]

        assert client.put("/api/config", json={"index_waits_for_disk": False}).json()["index_waits_for_disk"] is False
        indexer.wait(3)
        assert not wait_for(client, ids[1], "ready", "warn")["index_held"]

        client.put("/api/config", json={"index_waits_for_disk": True})
        (tmp_path / "src" / "Show.S01E02.mkv_tmp" / "Show.S01E02.mkv.ffindex").unlink()
        client.post("/api/queue/index", json={"ids": [ids[1]]})
        time.sleep(0.3)
        assert client.get(f"/api/jobs/{ids[1]}").json()["index_held"] and len(indexer.calls) == 3
        client.post("/api/queue/cancel")
        indexer.wait(4)
        assert not wait_for(client, ids[1], "ready", "warn")["index_held"]


def test_folder_browser(tmp_path):
    make_files(tmp_path)
    with make_client(tmp_path) as client:
        listing = client.get("/api/fs/list", params={"path": str(tmp_path / "src"), "extensions": ".mkv"}).json()
        assert [f["name"] for f in listing["files"]] == ["Show.S01E01.mkv"]
        assert listing["parent"] == str(tmp_path)
        # Programs: by extension on Windows; elsewhere runnable, or without an extension (execute bit lost).
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        for name in ("dee", "dee.exe", "lib.so", "run.sh"):
            (tools_dir / name).write_bytes(b"")
        (tools_dir / "run.sh").chmod(0o755)
        listing = client.get("/api/fs/list", params={"path": str(tools_dir), "programs": "true"}).json()
        want = ["dee.exe"] if os.name == "nt" else ["dee", "run.sh"]
        assert [f["name"] for f in listing["files"]] == want
        outside = str(tmp_path.parent)  # a real folder, outside the one root
        assert client.get("/api/fs/list", params={"path": outside}).status_code == 403
        assert client.get("/api/fs/roots").json() == [str(tmp_path)]
        paths = [
            str(tmp_path / "src"),
            str(tmp_path / "src" / "Show.S01E01.mkv"),
            str(tmp_path / "nope.mkv"),
            outside,
            "relative.mkv",
        ]
        kinds = client.post("/api/fs/kinds", json={"paths": paths}).json()
        assert [k["kind"] for k in kinds] == ["folder", "file", "missing", "outside", "missing"]

        # New folders, and deleting them: one with things in it only when asked to.
        made = client.post("/api/fs/mkdir", json={"path": str(tmp_path), "name": " out "}).json()["path"]
        assert made == str(tmp_path / "out") and (tmp_path / "out").is_dir()
        assert client.post("/api/fs/mkdir", json={"path": str(tmp_path), "name": "out"}).status_code == 409
        for bad in ("", "..", "a/b", "a:b"):
            assert client.post("/api/fs/mkdir", json={"path": str(tmp_path), "name": bad}).status_code == 422
        assert client.post("/api/fs/mkdir", json={"path": outside, "name": "x"}).status_code == 403
        (tmp_path / "out" / "sub").mkdir()
        (tmp_path / "out" / "sub" / "a.mkv").write_bytes(b"12345")
        (tmp_path / "out" / "b.txt").write_bytes(b"123")
        assert client.get("/api/fs/contents", params={"path": made}).json() == {"files": 2, "dirs": 1, "bytes": 8}
        assert client.post("/api/fs/rmdir", json={"path": made}).status_code == 409
        assert (tmp_path / "out" / "sub" / "a.mkv").exists()
        assert client.post("/api/fs/rmdir", json={"path": made, "recursive": True}).status_code == 200
        assert not (tmp_path / "out").exists()
        (tmp_path / "empty").mkdir()
        assert client.post("/api/fs/rmdir", json={"path": str(tmp_path / "empty")}).status_code == 200
        # Never a browsable root (or what holds one), never outside them.
        assert client.post("/api/fs/rmdir", json={"path": str(tmp_path), "recursive": True}).status_code == 403
        assert client.post("/api/fs/rmdir", json={"path": outside, "recursive": True}).status_code == 403
        assert (tmp_path / "src").is_dir()


# --- real VapourSynth preview --------------------------------------------------------

FFMPEG = shutil.which("ffmpeg")


@pytest.mark.skipif(
    FFMPEG is None or not (PROJECT_ROOT / "tools" / "vs-plugins" / "ffms2.dll").exists(),
    reason="needs ffmpeg and tools/vs-plugins",
)
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
        wait_for(client, job_id, "ready", "warn")
        assert client.get(f"{base}/info", params={"stage": "source"}).status_code == 409  # not indexed
        client.post("/api/queue/index", json={"ids": [job_id], "first": True})  # FFMS2, through ffindex
        assert wait_for(client, job_id, "ready", "warn", timeout=60)["indexed"]
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
        assert (
            not parts["custom"] and parts["script"] == "\n".join(parts["head"] + parts["body"] + parts["tail"]) + "\n"
        )
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
