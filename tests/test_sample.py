"""The test encode (core/pipeline/sample.py): its blocks, script, steps and result; its run in the index lane;
the Video tab's compare stages. The last test encodes for real (x264, mkvmerge, VapourSynth) and skips without them.
"""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
import io
from pathlib import Path
import shutil
import subprocess
import threading
import time

from fastapi.testclient import TestClient
import pytest
from test_server import APP, add, fake_probe, make_client, make_files, wait_for

from videoforge.core.config import AppConfig, load_app_config
from videoforge.core.execute.process import Cancelled
from videoforge.core.job import JobSpec, JobStatus
from videoforge.core.models import JobInputs, Plan, SourceInfo, VideoInfo
from videoforge.core.pipeline import sample
from videoforge.core.video.info import ScriptInfo
from videoforge.core.video.settings import Encoder, EncoderSettings, RateControl
from videoforge.server.app import create_app
from videoforge.server.queue import Services
from videoforge.server.settings import ServerSettings

NTSC = Fraction(24000, 1001)


def test_blocks_are_staxrips():
    """2 s blocks, one in every 100 / percent of them; the last cycle gives what's left of a block."""
    sel = sample.selection(ScriptInfo(2400, NTSC), 5)
    assert sel == sample.Selection(cycle=960, length=48)
    assert sel.frames(2400) == 2 * 48 + 48 and sel.frames(1930) == 2 * 48 + 10 and sel.frames(30) == 30
    assert sample.selection(ScriptInfo(100, None), 10, Fraction(25)) == sample.Selection(500, 50)  # VFR: source's
    assert sample.selection(ScriptInfo(100, None), 10) == sample.Selection(480, 48)


def test_script_selects_before_the_output():
    text = "import vapoursynth as vs\ncore = vs.core\nclip = src\nclip.set_output()\n"
    out = sample.script_text(text, sample.Selection(960, 48)).splitlines()
    assert out[-1] == "clip.set_output()"
    assert out[-2] == ("clip = core.std.SelectEvery(clip, cycle=960, offsets=list(range(48)), modify_duration=False)")


def _plan(tmp_path: Path) -> tuple[JobSpec, Plan]:
    src = tmp_path / "Movie.mkv"
    src.write_bytes(b"x")
    video = VideoInfo(1920, 1080, default_duration_ns=41708333)
    spec = JobSpec(inputs=JobInputs(source=src), profile="manual")
    plan = Plan(SourceInfo(path=src, name=src.name, video=video), None, "1080p", "en")
    return spec, plan


def test_two_pass_samples_one_pass_at_its_bitrate(tmp_path):
    _spec, plan = _plan(tmp_path)
    found = ScriptInfo(2400, NTSC)
    crf = EncoderSettings(Encoder.X265, RateControl.CRF, crf=20)
    assert sample.one_pass(crf, plan, "mkv", found) is crf
    two = EncoderSettings(Encoder.X265, RateControl.TWO_PASS, bitrate_kbps=6000)
    assert sample.one_pass(two, plan, "mkv", found) == replace(two, rate_control=RateControl.ABR)
    sized = sample.one_pass(replace(two, target_mb=100), plan, "mkv", found)
    assert sized.rate_control is RateControl.ABR and sized.bitrate_kbps != 6000  # the size's bitrate
    assert sample.describe(crf) == "x265 crf 20" and sample.describe(two) == "x265 6000 kb/s"


def test_steps_encode_the_sample_and_mux_it(tmp_path):
    spec, plan = _plan(tmp_path)
    spec.job_dir.mkdir(parents=True)
    (spec.job_dir / "video.info.txt").write_text("Frames: 2400\nFPS: 24000/1001 (23.976 fps)\n")
    steps = sample.sample_steps(spec, plan, APP, "mkv", 5)
    assert [s.id for s in steps] == ["sample.script", "sample.video", "sample.mux"]
    home = sample.sample_dir(spec)
    pipe, encode = steps[1].argvs
    assert pipe[-2:] == (str(home / "sample.vpy"), "-") and encode[encode.index("--output") + 1] == str(
        home / "video.264"
    )
    assert "--qpfile" not in encode  # the chapters' keyframes are the whole video's
    assert steps[2].argvs[0][1:] == (
        "--output",
        str(home / "sample.mkv"),
        "--default-duration",
        "0:24000/1001p",
        str(home / "video.264"),
    )
    steps[0].call(print)
    assert "SelectEvery(clip, cycle=960, offsets=list(range(48))" in (home / "sample.vpy").read_text()

    av1 = replace(spec, encoder=EncoderSettings(Encoder.SVTAV1, RateControl.CRF, crf=30))
    video = sample.sample_steps(av1, plan, APP, "mkv", 5)[1].argvs[1]
    assert video[video.index("--frames") + 1] == "144"  # SvtAv1EncApp doesn't know a pipe's length
    assert "--default-duration" not in sample.sample_steps(av1, plan, APP, "mkv", 5)[2].argvs[0]  # an IVF's timed


def test_result_and_its_estimates(tmp_path):
    spec, plan = _plan(tmp_path)
    home = sample.sample_dir(spec)
    home.mkdir(parents=True)
    (spec.job_dir / "video.info.txt").write_text("Frames: 2400\nFPS: 24000/1001 (23.976 fps)\n")
    (home / "video.264").write_bytes(b"\0" * 300_000)
    assert sample.read_result(spec) is None  # no MKV
    from videoforge.core.job import StepRecord

    result = sample.finish(spec, plan, "mkv", 5, {"sample.video": StepRecord("sample.video", "f", seconds=12.0)})
    assert (result.frames, result.total_frames, result.encoder) == (144, 2400, "x264 crf 18")
    assert result.kbps == pytest.approx(300_000 * 8 / 1000 / (144 / float(NTSC)))
    assert result.estimate_mb == pytest.approx(result.kbps * 2400 / float(NTSC) / 8 / 1000)
    assert result.estimate_seconds == pytest.approx(200.0) and result.encode_fps == pytest.approx(12.0)
    (home / "sample.mkv").write_bytes(b"mkv")
    assert sample.read_result(spec) == result
    assert result.key == sample.sample_key(spec, plan)
    spec.encoder = replace(spec.encoder, crf=20)
    assert result.key != sample.sample_key(spec, plan)  # out of date


class FakeSampler:
    """The index lane's runner for a test encode: the FFMS2 index, the script info (2400 frames, 23.976 fps),
    the encode (300 kB; it waits for `gate` or a cancel) and the MKV."""

    def __init__(self):
        self.calls: list[str] = []
        self.gate = threading.Event()

    def __call__(self, argvs, log, cancel=None):
        argv = [str(a) for a in argvs[-1]]
        if len(argvs) == 2:  # vspipe | encoder
            self.calls.append("encode")
            log("[x264] [50.0%] 72/144 frames")
            while not self.gate.is_set():
                if cancel is not None and cancel.cancelled:
                    raise Cancelled()
                time.sleep(0.01)
            Path(argv[argv.index("--output") + 1]).write_bytes(b"\0" * 300_000)
        elif "--info" in argv:
            self.calls.append("info")
            Path(argv[-1]).write_text("Frames: 2400\nFPS: 24000/1001 (23.976 fps)\n")
        elif "--output" in argv:
            self.calls.append("mux")
            Path(argv[argv.index("--output") + 1]).write_bytes(b"mkv")
        else:
            self.calls.append("index")
            Path(argv[-1]).write_bytes(b"index")


def test_test_encode_runs_in_the_index_lane(tmp_path):
    """POST /api/queue/sample indexes the job if it has to, then encodes the sample beside the queue. The job is
    locked meanwhile (sampling), and its result shows on the job; the same sample again reuses its steps."""
    make_files(tmp_path)
    runner = FakeSampler()
    with make_client(tmp_path, runner=runner) as client:
        (job,) = add(client, tmp_path)
        wait_for(client, job, "ready", "warn")
        assert client.post("/api/queue/sample", json={"id": job, "percent": 3}).status_code == 422
        r = client.post("/api/queue/sample", json={"id": job, "percent": 5}).json()
        assert r["taken"]
        running = wait_for(client, job, "sampling")
        assert running["indexed"] and client.get("/api/queue").json()["sampling"] == job
        assert client.patch(f"/api/jobs/{job}", json={"qpf": False}).status_code == 409
        assert client.post("/api/queue/enqueue", json={"ids": [job]}).json()["enqueued"] == []
        assert not client.post("/api/queue/sample", json={"id": job, "percent": 5}).json()["taken"]
        runner.gate.set()
        done = wait_for(client, job, "ready", "warn")
        assert not done["sample_error"] and not done["sample_waiting"]
        assert runner.calls == ["index", "info", "encode", "mux"]
        found = done["sample"]
        assert (found["percent"], found["frames"], found["total_frames"], found["current"]) == (5, 144, 2400, True)
        assert found["estimate_mb"] == pytest.approx(found["kbps"] * 2400 / float(NTSC) / 8000)
        assert done["compare"] == {"encode": False, "sample": True}
        e = client.app.state.queue.get(job)
        assert e.state.status is None  # a test encode is no run
        assert any("Test encode: 144 frames of 2400" in line for line in e.log)

        client.post("/api/queue/sample", json={"id": job, "percent": 5})
        wait_for(client, job, "sampling", "ready", "warn")
        wait_for(client, job, "ready", "warn")
        assert runner.calls == ["index", "info", "encode", "mux"]  # all reused

        # An edit puts the sample out of date; stopping the lane cancels a test encode, which says nothing.
        video = client.get(f"/api/jobs/{job}").json()["spec"]["encoder"] | {"crf": 20}
        client.patch(f"/api/jobs/{job}", json={"encoder": video})
        assert not client.get(f"/api/jobs/{job}").json()["sample"]["current"]
        runner.gate.clear()
        client.post("/api/queue/sample", json={"id": job, "percent": 5})
        wait_for(client, job, "sampling")
        client.post("/api/queue/index/stop", json={"ids": [job]})
        stopped = wait_for(client, job, "ready", "warn")
        assert not stopped["sample_error"] and runner.calls[-1] == "encode"


def test_compare_stages_need_their_encodes(tmp_path):
    make_files(tmp_path)
    with make_client(tmp_path) as client:
        (job,) = add(client, tmp_path)
        wait_for(client, job, "ready", "warn")
        e = client.app.state.queue.get(job)
        e.spec.work_dir.mkdir(exist_ok=True)
        (e.spec.work_dir / "Show.S01E01.mkv.ffindex").write_bytes(b"index")  # indexed
        for stage in ("sample-in", "sample", "encode"):
            r = client.get(f"/api/jobs/{job}/video/info", params={"stage": stage})
            assert r.status_code == 409, stage


def _real_app() -> AppConfig | None:
    app = load_app_config()
    t = app.tools
    if shutil.which("ffmpeg") is None or not all(
        Path(p).is_file() for p in (t.x264, t.mkvmerge, Path(t.vs_plugins) / "ffms2.dll")
    ):
        return None
    return replace(app, profile="manual")


REAL = _real_app()


@pytest.mark.skipif(REAL is None, reason="needs ffmpeg, x264, mkvmerge and tools/vs-plugins")
def test_a_real_test_encode_compares_frame_for_frame(tmp_path):
    """x264 on 10% of a 30 s clip: two blocks (frames 0-47 and 480-527); the sample's frames are the script's
    selected ones, so frame n of `sample` is frame n of `sample-in`, encoded. A done run's output compares the
    same way (`encode` against `output`)."""
    from PIL import Image, ImageChops, ImageStat

    from videoforge.core.video import vs as vsx

    assert REAL is not None
    (tmp_path / "src").mkdir()
    clip = tmp_path / "src" / "Movie.mkv"
    subprocess.run(
        [shutil.which("ffmpeg"), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
         "testsrc2=duration=30:size=320x180:rate=24", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", str(clip)],
        check=True,
    )  # fmt: skip
    vsx.configure(REAL.tools.vs_plugins)
    app = create_app(
        ServerSettings(data_dir=tmp_path / "data", roots=[tmp_path], frontend_dir=tmp_path / "none"),
        REAL,
        services=Services(probe=fake_probe),
        setup_vapoursynth=False,
    )
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        (job,) = add(client, tmp_path, sources=[str(clip)], subtitles=[])
        wait_for(client, job, "ready", "warn")
        assert client.post("/api/queue/sample", json={"id": job, "percent": 10}).json()["taken"]
        wait_for(client, job, "sampling", timeout=60)
        done = wait_for(client, job, "ready", "warn", timeout=120)
        assert not done["sample_error"], done["sample_error"]
        found = done["sample"]
        assert (found["frames"], found["total_frames"], found["length"], found["cycle"]) == (96, 720, 48, 480)
        assert found["kbps"] > 0 and Path(found["file"]).is_file()
        base = f"/api/jobs/{job}/video"
        for stage in ("sample-in", "sample"):
            assert client.get(f"{base}/info", params={"stage": stage}).json()["frames"] == 96

        def frame(stage: str, n: int) -> Image.Image:
            r = client.get(f"{base}/frame", params={"n": n, "stage": stage, "fmt": "png"})
            assert r.status_code == 200, r.text
            return Image.open(io.BytesIO(r.content)).convert("RGB")

        def diff(a: Image.Image, b: Image.Image) -> float:
            return sum(ImageStat.Stat(ImageChops.difference(a, b)).mean)

        encoded = frame("sample", 60)  # the second block: script frame 492
        assert diff(encoded, frame("sample-in", 60)) < diff(encoded, frame("sample-in", 20))
        assert diff(encoded, frame("sample-in", 60)) == pytest.approx(diff(encoded, frame("output", 492)))

        # A done run's output: its frames against the script's.
        e = client.app.state.queue.get(job)
        e.state.status, e.state.output = JobStatus.DONE, Path(found["file"])
        assert client.get(f"/api/jobs/{job}").json()["compare"]["encode"]
        assert client.get(f"{base}/info", params={"stage": "encode"}).json()["frames"] == 96
        assert diff(frame("encode", 60), frame("sample-in", 60)) < 30
