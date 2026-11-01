"""The CRF search (core/pipeline/crfsearch.py): the CRFs it tries, its tries' steps and files, its run in the index
lane, and its result on the job. The last test searches for real (x264, mkvmerge, VapourSynth, vszip) and skips
without them.
"""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import re
import shutil
import subprocess

from fastapi.testclient import TestClient
import pytest
from test_sample import REAL, _plan
from test_server import APP, add, fake_probe, make_client, make_files, wait_for

from videoforge.core.pipeline import crfsearch
from videoforge.core.pipeline.crfsearch import Metric, Target, Try
from videoforge.core.video.settings import Encoder, EncoderSettings, RateControl
from videoforge.server.app import create_app
from videoforge.server.queue import Services
from videoforge.server.settings import ServerSettings


def _score(crf: int) -> float:
    return 100 - 2 * crf  # SSIMULACRA2 falling 2 a CRF: 70 at CRF 15


def _try(crf: int, score: float | None = None) -> Try:
    s = _score(crf) if score is None else score
    return Try(crf, 1000, 1.0, 100.0, 10.0, s, s - 8, 40.0)


def _walk(target: Target, start: float, encoder: Encoder = Encoder.X265, score=_score) -> list[int]:
    tries: list[Try] = []
    while (crf := crfsearch.next_crf(tries, target, start, encoder)) is not None:
        assert crf not in [t.crf for t in tries]
        tries.append(_try(crf, score(crf)))
    return [t.crf for t in tries]


def test_search_brackets_then_interpolates():
    """From the job's CRF: a failure goes down JUMP, then the line between the pass and the failure; it ends with
    the two one CRF apart."""
    goal = Target(Metric.SSIMULACRA2, 70)
    assert _walk(goal, 18) == [18, 14, 15, 16]
    assert crfsearch.answer([_try(c) for c in (18, 14, 15, 16)], goal) == 15
    assert _walk(goal, 10) == [10, 14, 18, 15, 16]  # passes go up
    assert _walk(goal, 15.4) == [15, 19, 16]


def test_search_ends_at_the_range():
    goal = Target(Metric.SSIMULACRA2, 70)
    assert _walk(goal, 49, score=lambda c: 90.0) == [49, 51]  # every CRF passes: the highest
    assert _walk(goal, 3, score=lambda c: 10.0) == [3, 0]  # none does
    assert crfsearch.answer([_try(3, 10.0), _try(0, 10.0)], goal) is None
    assert _walk(goal, 30, Encoder.SVTAV1, score=lambda c: 10.0) == [30, 24, 18, 12, 6, 1]  # SVT-AV1: from 1
    assert len(_walk(goal, 0, score=lambda c: 100.0 - c / 100)) == crfsearch.MAX_TRIES  # gives up


def test_a_try_without_the_metric_halves():
    goal = Target(Metric.XPSNR, 40)
    tries = [replace(_try(10), xpsnr=45.0), replace(_try(20), xpsnr=None)]
    assert crfsearch.next_crf(tries, goal, 10, Encoder.X264) == 15


def test_tries_share_a_script_and_keep_their_own_files(tmp_path):
    spec, plan = _plan(tmp_path)
    spec.encoder = EncoderSettings(Encoder.X265, RateControl.CRF, crf=18)
    spec.job_dir.mkdir(parents=True)
    (spec.job_dir / "video.info.txt").write_text("Frames: 2400\nFPS: 24000/1001 (23.976 fps)\n")
    home = crfsearch.search_dir(spec)
    a, b = (crfsearch.try_steps(spec, plan, APP, "mkv", 5, crf) for crf in (18, 22))
    assert [s.id for s in a] == ["search.script", "search.crf18.video", "search.crf18.mux", "search.crf18.quality"]
    assert a[0].key == b[0].key and a[0].outputs == b[0].outputs == (home / "sample.vpy",)
    encode = b[1].argvs[1]
    assert encode[encode.index("--crf") + 1] == "22" and encode[encode.index("--output") + 1] == str(
        home / "crf-22" / "video.hevc"
    )
    assert b[3].outputs == (home / "crf-22" / "sample.quality.json",)
    a[0].call(print)
    assert (home / "crf-18").is_dir() and (home / "sample.vpy").is_file()
    # The key leaves the CRF out (applying the one found keeps the result current); other settings don't.
    key = crfsearch.search_key(spec, plan)
    assert crfsearch.search_key(replace(spec, encoder=replace(spec.encoder, crf=30)), plan) == key
    assert crfsearch.search_key(replace(spec, encoder=replace(spec.encoder, preset="slow")), plan) != key
    with pytest.raises(ValueError, match="rate control at CRF"):
        crfsearch.check(replace(spec, encoder=replace(spec.encoder, rate_control=RateControl.ABR)))


class FakeSearcher:
    """The index lane's runner for a CRF search: the index, the script info (2400 frames), each try's encode
    (a size falling with the CRF), its MKV and scores (_score)."""

    def __init__(self):
        self.calls: list[str] = []

    def __call__(self, argvs, log, cancel=None):
        argv = [str(a) for a in argvs[-1]]
        if len(argvs) == 2:  # vspipe | encoder
            crf = int(float(argv[argv.index("--crf") + 1]))
            self.calls.append(f"encode {crf}")
            Path(argv[argv.index("--output") + 1]).write_bytes(b"\0" * (100_000 - crf * 1000))
        elif "videoforge.core.video.metrics" in argv:
            crf = int(re.search(r"crf-(\d+)", argv[-1]).group(1))  # pyright: ignore[reportOptionalMemberAccess]
            s = _score(crf)
            scores = {"frames": 144, "ssimulacra2": s, "ssimulacra2_p5": s - 8, "xpsnr": 50 - crf / 2}
            Path(argv[-1]).write_text(json.dumps(scores))
        elif "--info" in argv:
            self.calls.append("info")
            Path(argv[-1]).write_text("Frames: 2400\nFPS: 24000/1001 (23.976 fps)\n")
        elif "--output" in argv:
            Path(argv[argv.index("--output") + 1]).write_bytes(b"mkv")
        else:
            self.calls.append("index")
            Path(argv[-1]).write_bytes(b"index")


def test_crf_search_runs_in_the_index_lane(tmp_path):
    """POST /api/queue/search indexes the job, then tries CRFs beside the queue (the job is sampling meanwhile);
    the job shows each try and the CRF found. Applying it keeps the result current, and another target reuses
    the CRFs already tried."""
    make_files(tmp_path)
    runner = FakeSearcher()
    with make_client(tmp_path, runner=runner) as client:
        (job,) = add(client, tmp_path)
        wait_for(client, job, "ready", "warn")
        body = {"id": job, "percent": 5, "metric": "ssimulacra2", "target": 70}
        assert client.post("/api/queue/search", json=body | {"metric": "vmaf"}).status_code == 422
        assert client.post("/api/queue/search", json=body | {"target": "x"}).status_code == 422
        assert client.post("/api/queue/search", json=body).json()["taken"]
        wait_for(client, job, "sampling", "ready", "warn")
        done = wait_for(client, job, "ready", "warn")
        assert not done["search_error"] and not done["searching"] and not done["sample_error"]
        assert runner.calls == ["index", "info", "encode 18", "encode 14", "encode 15", "encode 16"]
        found = done["search"]
        assert (found["done"], found["crf"], found["exact"], found["current"]) == (True, 15, True, True)
        assert [t["crf"] for t in found["tries"]] == [18, 14, 15, 16]
        assert found["tries"][0]["kbps"] == pytest.approx(82_000 * 8 / 1000 / (144 / (24000 / 1001)))
        assert done["sample"] is None  # the test encode's own result is apart
        e = client.app.state.queue.get(job)
        assert any("CRF 15 is the highest that reaches SSIMULACRA2 70" in line for line in e.log)

        encoder = done["spec"]["encoder"] | {"crf": 15}
        client.patch(f"/api/jobs/{job}", json={"encoder": encoder})
        assert client.get(f"/api/jobs/{job}").json()["search"]["current"]

        # A stricter target from CRF 15: 15 and 14 are reused, 11 and 12 are new.
        client.post("/api/queue/search", json=body | {"target": 76})
        wait_for(client, job, "sampling", "ready", "warn")
        again = wait_for(client, job, "ready", "warn")["search"]
        assert [t["crf"] for t in again["tries"]] == [15, 11, 12, 13]
        assert runner.calls[6:] == ["encode 11", "encode 12", "encode 13"] and again["crf"] == 12

        abr = encoder | {"rate_control": "abr"}
        client.patch(f"/api/jobs/{job}", json={"encoder": abr})
        r = client.post("/api/queue/search", json=body)
        assert r.status_code == 422 and "rate control at CRF" in r.json()["detail"]


@pytest.mark.skipif(
    REAL is None or not (Path(REAL.tools.vs_plugins) / "vszip").is_dir(),
    reason="needs ffmpeg, x264, mkvmerge and tools/vs-plugins with vszip",
)
def test_a_real_crf_search_finds_a_crf_that_reaches_its_target(tmp_path):
    """x264 on 10% of a 20 s clip: the CRF found reaches the target, the one above it doesn't, and scores fall
    as the CRF rises."""
    from videoforge.core.video import vs as vsx

    assert REAL is not None
    (tmp_path / "src").mkdir()
    clip = tmp_path / "src" / "Movie.mkv"
    subprocess.run(
        [shutil.which("ffmpeg"), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
         "testsrc2=duration=20:size=320x180:rate=24", "-c:v", "libx264", "-qp", "0", "-pix_fmt", "yuv420p", "-y",
         str(clip)],
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
        body = {"id": job, "percent": 10, "metric": "ssimulacra2", "target": 80}
        assert client.post("/api/queue/search", json=body).json()["taken"]
        wait_for(client, job, "sampling", timeout=60)
        done = wait_for(client, job, "ready", "warn", timeout=300)
        assert not done["search_error"], done["search_error"]
        found = done["search"]
        tries = {t["crf"]: t for t in found["tries"]}
        assert found["done"] and found["crf"] is not None, found
        assert tries[found["crf"]]["ssimulacra2"] >= 80
        if found["exact"]:
            assert tries[found["crf"] + 1]["ssimulacra2"] < 80
        ordered = [tries[c]["ssimulacra2"] for c in sorted(tries)]
        assert ordered[0] > ordered[-1]
