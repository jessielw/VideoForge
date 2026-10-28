"""The job record and the event streams other tools read (core/record.py)."""

from __future__ import annotations

import json
from pathlib import Path

from conftest import simulate_output
from test_pipeline import APP, FakeRunner, make_plan

from videoforge.core.execute.process import Cancelled
from videoforge.core.job import JobState, JobStatus, OutputPolicy, StepRun, StepStatus
from videoforge.core.models import VideoHdr, VideoInfo
from videoforge.core.pipeline.build import job_output
from videoforge.core.pipeline.run import run_job, spec_from_plan
from videoforge.core.record import (
    SCHEMA,
    JsonLines,
    RunRecorder,
    _hdr,
    encoder_summary,
    read_record,
    record_path,
    summary_lines,
)
from videoforge.core.video.settings import Encoder, EncoderSettings


def lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def run(
    profile,
    tmp_path: Path,
    runner=None,
    label: str = "dubbed",
    queue: JsonLines | None = None,
    output_policy=OutputPolicy.STOP,
):
    plan = make_plan(tmp_path)
    spec = spec_from_plan(plan, tmp_path / "out")
    spec.label = label
    spec.output_policy = output_policy
    state = JobState()
    output = job_output(spec, plan, profile)
    rec = RunRecorder(
        spec, plan, profile, output, queue_events=queue, versions=lambda names: dict.fromkeys(names, "v1")
    )
    rec.started_run()
    result = run_job(
        spec,
        plan,
        profile,
        APP,
        state=state,
        runner=runner or FakeRunner(),
        prober=lambda *_: simulate_output(plan),
        on_step=lambda r: rec.step(r, state.run.index(r), len(state.run)),
    )
    rec.finished(result, state)
    return spec, output, result, rec


def test_a_finished_run_writes_its_record_and_events(profile, tmp_path):
    queue = JsonLines(tmp_path / "data" / "logs" / "events.jsonl")
    spec, output, result, rec = run(profile, tmp_path, queue=queue)
    assert result.status is JobStatus.DONE and output == tmp_path / "out" / "Show.S01E01.dubbed.mkv"
    work = tmp_path / "Show.S01E01.mkv_tmp" / "dubbed"  # the job's folder, by its label

    events = lines(work / "Show.S01E01.dubbed.mkv.videoforge.jsonl")
    assert all(e["v"] == SCHEMA and e["job"] == spec.id and e["run"] == rec.run_id for e in events)
    kinds = [e["event"] for e in events]
    assert kinds[0] == "run.started" and kinds[-1] == "run.finished"
    steps = [(e["event"], e["step"]) for e in events[1:-1]]
    assert steps == [
        ("step.started", "audio.1"),
        ("step.finished", "audio.1"),
        ("step.started", "audio.2"),
        ("step.finished", "audio.2"),
        ("step.started", "mux"),
        ("step.started", "validate"),
        ("step.finished", "validate"),
        ("step.finished", "mux"),
    ]  # validation finishes before mux publication can finish
    assert events[0]["output"] == str(output) and events[0]["label"] == "dubbed"
    assert events[2]["status"] == "done" and events[2]["n"] == 1 and events[2]["total"] == 4
    assert events[-1]["status"] == "done" and events[-1]["record"] == str(rec.record_file)
    queue.close()
    assert lines(tmp_path / "data" / "logs" / "events.jsonl") == events  # the queue-wide stream has them too

    doc = read_record(record_path(work, output))
    assert doc is not None and rec.record_file == work / "Show.S01E01.dubbed.mkv.videoforge.json"
    assert doc["run"]["status"] == "done" and doc["run"]["id"] == rec.run_id
    assert doc["job"] | {"id": None} == {
        "id": None,
        "name": "Show.S01E01.mkv",
        "label": "dubbed",
        "profile": spec.profile,
        "episode": "S01E01",
    }
    assert doc["source"]["path"] == str(tmp_path / "Show.S01E01.mkv") and doc["source"]["size"] == 1
    assert doc["output"]["path"] == str(output) and doc["output"]["container"] == "mkv"
    assert doc["video"] == {"encoded": False, "encode": str(tmp_path / "Show.S01E01_job.h264"), "language": "und"}
    ja, en = doc["audio"]
    assert (ja["index"], ja["track"], ja["action"], ja["codec"]) == (0, 1, "aac", "aac")
    assert ja["source"] | {"path": None} == {
        "kind": "source",
        "path": None,
        "id": 1,
        "index": 0,
        "copy": 0,
        "codec": "flac",
        "layout": "2.0",
        "atmos": False,
        "language": "ja",
        "title": ja["source"]["title"],
    }
    assert ja["encoder"]["label"] and "qaac" in ja["encoder"]["tools"] and "qaac64" in ja["command"]
    assert ja["file"] == str(result.encoded_audio[0])
    assert (en["track"], en["action"], en["layout"], en["channels"], en["bitrate_kbps"]) == (2, "ddp", "5.1", 6, 640)
    assert en["source"]["index"] == 1 and en["source"]["codec"] == "truehd"
    pgs, srt = doc["subtitles"]
    assert (pgs["track"], pgs["source"]["kind"], pgs["format"]) == (3, "source", "pgs")
    assert (srt["track"], srt["source"]["kind"], srt["source"]["path"]) == (
        4,
        "file",
        str(tmp_path / "Show.S01E01.en.srt"),
    )
    assert [s["id"] for s in doc["steps"]] == ["audio.1", "audio.2", "mux", "validate"]
    assert all(s["status"] == "done" for s in doc["steps"])
    assert set(doc["tools"]) == {"qaac", "ffmpeg", "deezy", "dee", "mkvmerge"} and doc["tools"]["mkvmerge"] == "v1"
    assert doc["log"] == str(work / "videoforge.log")
    assert doc["job_dir"] == str(work) and doc["work_dir"] == str(work.parent)


def test_a_failed_run_keeps_the_last_record(profile, tmp_path):
    _, output, _, first = run(profile, tmp_path)
    assert first.record_file is not None
    before = first.record_file.read_text(encoding="utf-8")
    _, _, result, rec = run(
        profile, tmp_path, runner=FakeRunner(fail_on="mkvmerge"), output_policy=OutputPolicy.REPLACE
    )
    assert result.status is JobStatus.FAILED and rec.record_file is None
    assert first.record_file.read_text(encoding="utf-8") == before  # it still describes the file that's there
    events = lines(first.record_file.with_suffix(".jsonl"))
    runs = [e for e in events if e["event"] == "run.finished"]
    assert [r["status"] for r in runs] == ["done", "failed"] and runs[1]["record"] is None
    assert "mkvmerge" in runs[1]["error"]
    failed = [e for e in events if e["event"] == "step.finished" and e["run"] == rec.run_id][-1]
    assert (failed["step"], failed["status"]) == ("mux", "failed")


def test_a_cancelled_run(profile, tmp_path):
    def cancelled(*_):
        raise Cancelled()

    _, output, result, rec = run(profile, tmp_path, runner=cancelled, label="")
    assert result.status is JobStatus.CANCELLED and rec.record_file is None
    events = lines(tmp_path / "Show.S01E01.mkv_tmp" / "main" / "Show.S01E01.mkv.videoforge.jsonl")
    assert [e["event"] for e in events] == ["run.started", "step.started", "step.finished", "run.finished"]
    assert events[2]["status"] == "cancelled" and events[-1]["status"] == "cancelled"


def test_json_lines_never_fail_and_roll_over(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, not a folder", encoding="utf-8")
    broken = JsonLines(blocker / "events.jsonl")
    broken.write({"a": 1})  # logged, not raised
    broken.write({"a": 2})

    path = tmp_path / "events.jsonl"
    stream = JsonLines(path, max_bytes=200, backups=2)
    for n in range(30):
        stream.write({"n": n, "pad": "x" * 20})
    stream.close()
    kept = [path, path.with_name("events.jsonl.1"), path.with_name("events.jsonl.2")]
    assert all(p.exists() for p in kept) and not path.with_name("events.jsonl.3").exists()
    assert all(p.stat().st_size <= 200 for p in kept)
    assert lines(path)[-1]["n"] == 29


def test_the_record_says_what_the_encode_carried_of_the_sources_hdr():
    fel = VideoInfo(3840, 2160, hdr=VideoHdr(7, 6, 6, "BL+EL+RPU", dv_el="FEL", hdr10plus=True))
    x265 = EncoderSettings(encoder=Encoder.X265)
    assert _hdr(fel, x265) == {
        "source": {
            "dolby_vision": "7.6 FEL",
            "dv_profile": 7,
            "dv_layers": "BL+EL+RPU",
            "dv_el": "FEL",
            "hdr10plus": True,
        },
        "dolby_vision": "8.1",
        "fel_baked": True,
        "hdr10plus": True,
    }
    # x264 carries none of it; an unticked choice drops it
    assert _hdr(fel, EncoderSettings())["dolby_vision"] is None and not _hdr(fel, EncoderSettings())["fel_baked"]
    dropped = _hdr(fel, EncoderSettings(encoder=Encoder.X265, dolby_vision=False, hdr10plus=False))
    assert (dropped["dolby_vision"], dropped["fel_baked"], dropped["hdr10plus"]) == (None, False, False)
    assert _hdr(None, x265)["source"] == {
        "dolby_vision": None,
        "dv_profile": None,
        "dv_layers": None,
        "dv_el": None,
        "hdr10plus": False,
    }


X265_TAIL = [
    "[x265] [91.7%] 44/48 Frames @ 2.766 FPS | 16221 kb/s | 0:00:15 [-0:00:01] | 3.72 MB [4.06 MB]  ",
    "[x265] x265 [INFO]: frame I:     19, Avg QP:23.50  kb/s: 33220.41",
    "[vspipe] Output 48 frames in 15.40 seconds (3.12 fps)",
    "[x265] x265 [INFO]: frame P:     19, Avg QP:26.35  kb/s: 7333.31 ",
    "[x265] x265 [INFO]: Weighted P-Frames: Y:5.3% UV:5.3%",
    "[x265] encoded 48 frames in 15.49s (3.10 fps), 16544.34 kb/s, Avg QP:25.51",
]
X264_TAIL = [
    "[x264] [100.0%] 48/48 Frames @ 21.16 FPS | 14271 kb/s | 0:00:02 [-0:00:00] | 3.57 MB [3.57 MB]  ",
    "[x264] x264 [INFO]: frame I:1     Avg QP:12.61  size:227074",
    "[x264] x264 [INFO]: kb/s:14271.11",
    "[x264] encoded 48 frames, 21.16 fps, 14271.11 kb/s, duration 0:00:02.26",
]


def test_the_encoders_closing_statistics_are_kept_without_their_tag():
    assert summary_lines(X265_TAIL) == [
        "x265 [INFO]: frame I:     19, Avg QP:23.50  kb/s: 33220.41",
        "x265 [INFO]: frame P:     19, Avg QP:26.35  kb/s: 7333.31",
        "x265 [INFO]: Weighted P-Frames: Y:5.3% UV:5.3%",
        "encoded 48 frames in 15.49s (3.10 fps), 16544.34 kb/s, Avg QP:25.51",
    ]  # vspipe's line between is not the encoder's
    assert summary_lines(X264_TAIL) == [line.removeprefix("[x264] ") for line in X264_TAIL[1:]]
    assert summary_lines(X265_TAIL[:-1]) is None  # cut short: no "encoded" line
    assert summary_lines(["[x265] [50.0%] 24/48 Frames"]) is None


def test_the_summary_is_the_final_pass_or_the_reused_encodes():
    def state(*runs: StepRun) -> JobState:
        return JobState(run=list(runs))

    pass1 = StepRun("video.pass1", "Video pass 1/2", status=StepStatus.DONE, tail=X264_TAIL)
    pass2 = StepRun("video.pass2", "Video pass 2/2", status=StepStatus.DONE, tail=X265_TAIL)
    assert encoder_summary(state(pass1, pass2), None)[-1].startswith("encoded 48 frames in 15.49s")
    reused = StepRun("video.pass2", "Video pass 2/2", status=StepStatus.REUSED)
    previous = {"video": {"encoder_summary": ["encoded 1 frames"]}}
    assert encoder_summary(state(pass1, reused), previous) == ["encoded 1 frames"]
    assert encoder_summary(state(pass1, reused), None) is None
    assert encoder_summary(state(StepRun("mux", "Mux", status=StepStatus.DONE)), previous) is None
