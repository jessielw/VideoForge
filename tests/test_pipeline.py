"""The pipeline: steps with a fake tool runner (order, resume, failures), a real job end to end,
and process.run on real subprocesses."""

from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time

from conftest import audio, plan_for, simulate_output, source, sub
import pytest

from videoforge.core.config import PROJECT_ROOT, AppConfig, Tools
from videoforge.core.execute import process
from videoforge.core.execute.control import Priority
from videoforge.core.execute.mux import MuxSettings
from videoforge.core.execute.process import Cancelled, CancelToken, ToolError
from videoforge.core.job import JobSpec, JobState, JobStatus, OutputPolicy, StepStatus
from videoforge.core.models import (
    AudioAction,
    AudioCodec as C,
    Issue,
    JobInputs,
    Layout,
    Plan,
    Severity,
    SubFormat as F,
    VideoColor,
    VideoHdr,
    VideoInfo,
)
from videoforge.core.pipeline.build import build_steps
from videoforge.core.pipeline.run import run_job, run_plan
from videoforge.core.video import hdr, target
from videoforge.core.video.settings import Crop, Encoder, EncoderSettings, RateControl, SourceFilter


def fake_tool_files(*names: str) -> dict[str, str]:
    """Empty files standing in for tools that must exist (audio encodes are blocked without them);
    the fake runner never starts them, and their stems are the tool names."""
    folder = Path(tempfile.mkdtemp(prefix="vf-tools-"))
    for name in names:
        (folder / f"{name}.exe").write_bytes(b"")
    return {name: str(folder / f"{name}.exe") for name in names}


_TOOLS = fake_tool_files("mkvmerge", "deezy", "dee", "truehdd", "qaac64", "ffmpeg")
APP = AppConfig(
    tools=Tools(
        mkvmerge=_TOOLS["mkvmerge"],
        deezy=_TOOLS["deezy"],
        dee=_TOOLS["dee"],
        truehdd=_TOOLS["truehdd"],
        qaac=_TOOLS["qaac64"],
        ffmpeg=_TOOLS["ffmpeg"],
        x264="x264",
        vspipe="vspipe",
    ),
    parallel_audio=0,  # one step at a time, in order (the parallel tests set their own)
)


def encode_audio(plan: Plan) -> None:
    """Japanese FLAC 2.0 -> AAC, English TrueHD 5.1 -> DDP 640 (the manual profile copies by default)."""
    ja, en = plan.audio
    ja.action, ja.out_codec = AudioAction.AAC, C.AAC
    en.action, en.out_codec, en.out_layout, en.bitrate_kbps = AudioAction.DDP, C.EAC3, Layout(5, 1), 640


def make_plan(root: Path):
    files = {name: root / name for name in ("Show.S01E01.mkv", "Show.S01E01_job.h264", "Show.S01E01.en.srt")}
    for f in files.values():
        f.write_bytes(b"x")
    src = source(
        [audio(C.FLAC, "2.0", "ja", index=0), audio(C.TRUEHD, "5.1", "en", index=1)],
        [sub(F.PGS, "en", "English", index=0)],
        name="Show.S01E01.mkv",
    )
    src.path = files["Show.S01E01.mkv"]
    src.video = VideoInfo(1920, 1080, default_duration_ns=41708333)
    srt = sub(F.SRT, "en", external=str(files["Show.S01E01.en.srt"]))
    plan = plan_for(src, source(name="Show.S01E01_job.h264"), external_subs=[srt])
    encode_audio(plan)
    plan.encode_path = files["Show.S01E01_job.h264"]
    plan.inputs = JobInputs(src.path, plan.encode_path, [files["Show.S01E01.en.srt"]])
    assert not plan.blocked, plan.issues
    return plan


def test_pgs_compression_changes_only_the_mux_step(profile, tmp_path):
    plan = make_plan(tmp_path)
    job = JobSpec(inputs=plan.inputs, profile="manual")
    output = tmp_path / "out.mkv"
    before = {s.id: s for s in build_steps(job, plan, profile, APP, output).steps}
    job.mux.pgs_zlib = True
    after = {s.id: s for s in build_steps(job, plan, profile, APP, output).steps}
    argv = after["mux"].argvs[0]
    assert argv[argv.index("--compression") + 1] == "10:zlib"
    assert before["mux"].fingerprint() != after["mux"].fingerprint()
    for key in before.keys() - {"mux"}:
        assert before[key].fingerprint() == after[key].fingerprint()
    job.mux.container = "mp4"
    mp4 = build_steps(job, plan, profile, APP, tmp_path / "out.mp4")
    assert "--compression" not in next(s for s in mp4.steps if s.id == "mux").argvs[0]


class FakeRunner:
    """Writes each command's output (and x264 stats) file, like the real tools would."""

    def __init__(self, fail_on: str | None = None):
        self.calls: list[list[list[str]]] = []
        self.fail_on = fail_on

    def __call__(self, argvs, log, cancel):
        self.calls.append([list(a) for a in argvs])
        last = list(argvs[-1])
        if self.fail_on and self.fail_on in last[0]:
            log(f"[{Path(last[0]).stem}] Error: something broke")
            raise ToolError(f"{last[0]} exited with code 2", 2)
        for flag in ("-o", "--output", "--stats", "-e"):
            if flag in last and last[last.index(flag) + 1] != os.devnull:
                Path(last[last.index(flag) + 1]).write_bytes(b"out")
        if "--info" in last and last[-1] != "-":  # the script info step: vspipe writes the clip's info
            Path(last[-1]).write_text(self.script_info, encoding="utf-8")
        if "videoforge.core.execute.loudness" in last:  # an audio measure step: <out.json> after the module
            Path(last[3]).write_text('{"max_volume": -4.5}', encoding="utf-8")
        if "timestamps_v2" in last:  # mkvextract: <track>:<file>, one timestamp per frame
            stamps = "".join(f"{round(i * 1001 / 24)}\n" for i in range(241))  # and the last frame's end
            Path(last[-1].split(":", 1)[1]).write_text("# timestamp format v2\n" + stamps, encoding="utf-8")
        log(f"[{Path(last[0]).stem}] [ 50.0%] 1/2 frames")

    script_info = "Width: 1920\nHeight: 1080\nFrames: 240\nFPS: 24000/1001 (23.976 fps)\n"


def tools_called(runner: FakeRunner) -> list[str]:
    return [Path(c[-1][0]).stem for c in runner.calls]


def test_run_plan_happy_path(profile, tmp_path):
    plan = make_plan(tmp_path)
    runner = FakeRunner()
    events, lines = [], []
    result = run_plan(
        plan,
        tmp_path / "out",
        profile,
        APP,
        runner=runner,
        prober=lambda path, _mkv: simulate_output(plan),
        progress=events.append,
        log=lines.append,
    )
    assert result.status is JobStatus.DONE, (result.error, result.issues)
    assert result.output == tmp_path / "out" / "Show.S01E01.mkv" and result.output.is_file()
    assert tools_called(runner) == ["qaac64", "deezy", "mkvmerge"]  # a reused encode: no video steps
    starts = [e.step.label.split(":")[0] for e in events if e.fraction == 0.0]
    assert starts == ["Encode audio 1", "Encode audio 2", "Mux"]
    assert any(0 < e.fraction < 1 for e in events)  # progress from the tools' output
    assert events[-1].overall == pytest.approx(1.0) and "== Validate" in lines
    assert not list((tmp_path / "out").glob("*.partial"))
    work = tmp_path / "Show.S01E01.mkv_tmp" / "main"  # the encodes stay in the job's folder for fix mode
    assert result.work_dir == work and sorted(result.encoded_audio) == [0, 1]
    assert all(p.parent == work and p.is_file() for p in result.encoded_audio.values())


def test_rerun_reuses_finished_steps(profile, tmp_path):
    plan = make_plan(tmp_path)
    state = JobState()
    prober = lambda *_: simulate_output(plan)
    first = FakeRunner()
    assert (
        run_plan(plan, tmp_path / "out", profile, APP, state=state, runner=first, prober=prober).status
        is JobStatus.DONE
    )
    assert set(state.steps) == {"audio.1", "audio.2", "mux"} and state.status is JobStatus.DONE

    again = FakeRunner()
    assert (
        run_plan(plan, tmp_path / "out", profile, APP, state=state, runner=again, prober=prober).status
        is JobStatus.DONE
    )
    assert again.calls == []  # nothing changed: every step reused

    srt = tmp_path / "Show.S01E01.en.srt"
    srt.write_bytes(b"changed subtitle")  # a new SRT: only the mux runs again
    third = FakeRunner()
    run_plan(plan, tmp_path / "out", profile, APP, state=state, runner=third, prober=prober)
    assert tools_called(third) == ["mkvmerge"]


def test_stale_output_does_not_pass_for_a_new_one(profile, tmp_path):
    """A step's outputs are deleted before it runs, so a tool that writes nothing fails."""
    plan = make_plan(tmp_path)
    run_plan(plan, tmp_path / "out", profile, APP, runner=FakeRunner(), prober=lambda *_: simulate_output(plan))
    again = run_plan(
        plan, tmp_path / "out", profile, APP, output_policy=OutputPolicy.REPLACE, runner=lambda *_: None
    )  # no state: nothing reused
    assert again.status is JobStatus.FAILED and "was not written" in again.error


def test_invalid_output_is_reported(profile, tmp_path):
    plan = make_plan(tmp_path)
    bad = simulate_output(plan)
    bad.subs[0].title = "Wrong"
    result = run_plan(plan, tmp_path / "out", profile, APP, runner=FakeRunner(), prober=lambda *_: bad)
    assert result.status is JobStatus.INVALID
    assert any(i.code == "plan.subs" for i in result.issues)


def test_blocked_plan_is_skipped(profile, tmp_path):
    plan = make_plan(tmp_path)
    plan.issues.append(Issue(Severity.BLOCK, "pair.no_encode", "No encode"))
    runner = FakeRunner()
    result = run_plan(plan, tmp_path / "out", profile, APP, runner=runner)
    assert result.status is JobStatus.SKIPPED and "No encode" in result.error
    assert not runner.calls


def test_missing_input_fails_before_running(profile, tmp_path):
    plan = make_plan(tmp_path)
    (tmp_path / "Show.S01E01.en.srt").unlink()
    runner = FakeRunner()
    result = run_plan(plan, tmp_path / "out", profile, APP, runner=runner)
    assert result.status is JobStatus.FAILED and "Show.S01E01.en.srt" in result.error
    assert not runner.calls


def test_missing_encoder_tool_fails_before_running(profile, tmp_path):
    plan = make_plan(tmp_path)  # encodes AAC and DDP
    app = replace(APP, tools=replace(APP.tools, qaac=str(tmp_path / "qaac64.exe")))
    runner = FakeRunner()
    result = run_plan(plan, tmp_path / "out", profile, app, runner=runner)
    assert result.status is JobStatus.FAILED and result.error == "AAC (qaac) needs qaac: set it in Settings"
    assert not runner.calls


def test_tool_failure_leaves_no_output(profile, tmp_path):
    plan = make_plan(tmp_path)
    result = run_plan(plan, tmp_path / "out", profile, APP, runner=FakeRunner(fail_on="mkvmerge"))
    assert result.status is JobStatus.FAILED and "mkvmerge" in result.error
    assert not (tmp_path / "out" / "Show.S01E01.mkv").exists()
    assert not list((tmp_path / "out").glob("*.partial"))


def test_cancel_is_reported(profile, tmp_path):
    plan = make_plan(tmp_path)

    def cancelled(*_):
        raise Cancelled()

    state = JobState()
    assert run_plan(plan, tmp_path / "out", profile, APP, state=state, runner=cancelled).status is JobStatus.CANCELLED
    assert [r.status for r in state.run] == [StepStatus.CANCELLED] + [StepStatus.PENDING] * 3


# --- the per-step record the Log tab shows ---------------------------------------------


def test_step_runs_record_each_step(profile, tmp_path):
    plan = make_plan(tmp_path)
    state, seen = JobState(), []
    prober = lambda *_: simulate_output(plan)
    on_step = lambda r: seen.append((r.id, r.status))
    run_plan(plan, tmp_path / "out", profile, APP, state=state, runner=FakeRunner(), prober=prober, on_step=on_step)
    ids = ["audio.1", "audio.2", "mux", "validate"]
    assert [r.id for r in state.run] == ids
    assert seen[:4] == [(i, StepStatus.PENDING) for i in ids]  # the whole list first
    assert seen[4:6] == [("audio.1", StepStatus.RUNNING), ("audio.1", StepStatus.DONE)]
    assert all(r.status is StepStatus.DONE for r in state.run)
    mux = state.run[2]
    assert APP.tools.mkvmerge in mux.command and " --output " in mux.command and mux.exit_code == 0
    assert mux.tail == ["[mkvmerge] [ 50.0%] 1/2 frames"]  # its own lines, not the step header
    assert state.run[-1].command == "" and state.run[-1].exit_code is None

    run_plan(plan, tmp_path / "out", profile, APP, state=state, runner=FakeRunner(), prober=prober)
    assert [r.status for r in state.run] == [StepStatus.REUSED] * 3 + [StepStatus.DONE]


def test_failed_step_is_named(profile, tmp_path):
    plan = make_plan(tmp_path)
    state = JobState()
    result = run_plan(plan, tmp_path / "out", profile, APP, state=state, runner=FakeRunner(fail_on="deezy"))
    assert [r.status for r in state.run] == [StepStatus.DONE, StepStatus.FAILED, StepStatus.PENDING, StepStatus.PENDING]
    failed = state.run[1]
    assert failed.exit_code == 2 and "exited with code 2" in failed.error
    assert failed.tail == ["[deezy] Error: something broke"]
    assert result.error.startswith(f"Step 2/4 · {failed.label}: ") and "deezy" in result.error
    assert state.error == result.error


def test_failed_validation_is_the_last_step(profile, tmp_path):
    plan = make_plan(tmp_path)
    bad = simulate_output(plan)
    bad.subs[0].title = "Wrong"
    state = JobState()
    run_plan(plan, tmp_path / "out", profile, APP, state=state, runner=FakeRunner(), prober=lambda *_: bad)
    v = state.run[-1]
    assert v.status is StepStatus.FAILED and v.error and any(line.startswith("block:") for line in v.tail)

    def broken_probe(*_):
        raise ToolError("mkvmerge could not read the output")

    result = run_plan(plan, tmp_path / "out", profile, APP, state=state, runner=FakeRunner(), prober=broken_probe)
    assert state.run[-1].status is StepStatus.FAILED and result.error.startswith("Step 4/4 · Validate: mkvmerge")


def test_vp9_steps(profile, tmp_path):
    """VP9 runs through ffmpeg into an IVF: its first pass writes ffmpeg's "-0.log", the chapters' qpfile becomes
    forced keyframes once written (the encode refreshes when its turn comes), and the mux tags the pixel aspect
    and colour."""
    plan = make_plan(tmp_path)
    plan.source.video.sar_num, plan.source.video.sar_den = 32, 27
    plan.source.video.color = VideoColor("bt709", "bt709", "bt709", "limited")
    job = JobSpec(
        inputs=JobInputs(plan.source.path, subtitles=plan.inputs.subtitles),
        profile="manual",
        encoder=EncoderSettings(Encoder.VP9, rate_control=RateControl.TWO_PASS, bitrate_kbps=3000, preset="4"),
        output_dir=tmp_path / "out",
    )
    plan.encode_path = job.video_output
    assert job.video_output.name == "video.ivf"
    built = build_steps(job, plan, profile, APP, tmp_path / "out" / "Show.S01E01.mkv")
    steps = {s.id: s for s in built.steps}
    pass1, pass2, mux = steps["video.pass1"], steps["video.pass2"], steps["mux"]
    assert pass1.argvs[1][0] == APP.tools.ffmpeg and "libvpx-vp9" in pass1.argvs[1]
    assert pass1.outputs == (job.job_dir / "video.stats-0.log",) and pass1.outputs[0] in pass2.inputs
    assert "-force_key_frames" not in pass2.argvs[1] and pass2.refresh is not None  # no qpfile yet
    qpfile = next(p for p in steps["chapters"].outputs if p.suffix == ".qpf")
    qpfile.parent.mkdir(parents=True, exist_ok=True)
    qpfile.write_text("0 I\n720 I\n", encoding="utf-8")
    again = pass2.refresh()
    assert again.argvs[1][again.argvs[1].index("-force_key_frames") + 1] == "expr:eq(n,0)+eq(n,720)"
    argv = mux.argvs[0]
    assert argv[argv.index("--aspect-ratio-factor") + 1] == "0:32/27"
    assert argv[argv.index("--colour-primaries") + 1] == "0:1" and argv[argv.index("--colour-range") + 1] == "0:1"
    assert "--default-duration" not in argv  # the IVF times itself


def test_svtav1_steps(profile, tmp_path):
    """SVT-AV1 runs SvtAv1EncApp into an IVF: once the info step and the chapters step have written their files
    (the encode refreshes when its turn comes), it's given the script's frames (its rate control needs the length)
    and, in CRF, the qpfile's keyframes; the mux tags the pixel aspect, the colour and the HDR10."""
    p3 = "G(13250,34500)B(7500,3000)R(34000,16000)WP(15635,16450)L(10000000,50)"
    plan = make_plan(tmp_path)
    plan.source.video.sar_num, plan.source.video.sar_den = 32, 27
    plan.source.video.color = VideoColor("bt2020", "smpte2084", "bt2020nc", "limited", 2, p3, 1000, 400)
    job = JobSpec(
        inputs=JobInputs(plan.source.path, subtitles=plan.inputs.subtitles),
        profile="manual",
        encoder=EncoderSettings(Encoder.SVTAV1, crf=30, preset="6", depth=10),
        output_dir=tmp_path / "out",
    )
    plan.encode_path = job.video_output
    built = build_steps(job, plan, profile, APP, tmp_path / "out" / "Show.S01E01.mkv")
    steps = {s.id: s for s in built.steps}
    video, mux = steps["video"], steps["mux"]
    assert video.argvs[1][0] == APP.tools.svtav1 and job.video_output.name == "video.ivf"
    assert "--frames" not in video.argvs[1] and "--force-key-frames" not in video.argvs[1]  # not written yet
    assert video.argvs[1][video.argvs[1].index("--mastering-display") + 1].startswith("G(0.265,0.69)")
    job.job_dir.mkdir(parents=True, exist_ok=True)
    info_file = job.job_dir / target.info.SCRIPT_INFO
    info_file.write_text("Width: 1920\nHeight: 1080\nFrames: 1440\nFPS: 24000/1001\n", encoding="utf-8")
    qpfile = next(p for p in steps["chapters"].outputs if p.suffix == ".qpf")
    qpfile.write_text("0 I\n720 I\n", encoding="utf-8")
    argv = video.refresh().argvs[1]
    assert argv[argv.index("--frames") + 1] == "1440" and argv[argv.index("--force-key-frames") + 1] == "0f,720f"
    argv = mux.argvs[0]
    assert argv[argv.index("--aspect-ratio-factor") + 1] == "0:32/27"
    assert argv[argv.index("--colour-transfer-characteristics") + 1] == "0:16"
    assert argv[argv.index("--max-luminance") + 1] == "0:1000" and argv[argv.index("--max-frame-light") + 1] == "0:400"

    # a bitrate: no forced keyframes (SvtAv1EncApp refuses them), still the frames
    two = replace(job, encoder=replace(job.encoder, rate_control=RateControl.TWO_PASS, bitrate_kbps=3000))
    steps = {s.id: s for s in build_steps(two, plan, profile, APP, tmp_path / "out" / "Show.S01E01.mkv").steps}
    for k in ("video.pass1", "video.pass2"):
        argv = steps[k].argvs[1]
        assert argv[argv.index("--frames") + 1] == "1440" and "--force-key-frames" not in argv, k


def test_video_steps_two_pass(profile, tmp_path):
    plan = make_plan(tmp_path)
    job = JobSpec(
        inputs=JobInputs(plan.source.path, subtitles=plan.inputs.subtitles),
        profile="manual",
        encoder=EncoderSettings(rate_control=RateControl.TWO_PASS, bitrate_kbps=9000),
        qpf=False,
        output_dir=tmp_path / "out",
    )
    job.video.crop = Crop(0, 140, 0, 140)
    plan.encode_path = job.video_output
    built = build_steps(job, plan, profile, APP, tmp_path / "out" / "Show.S01E01.mkv")
    ids = ["script", "index", "script.info", "audio.1", "audio.2", "video.pass1", "video.pass2", "mux"]
    assert [s.id for s in built.steps] == ids
    pass1, pass2 = built.steps[5], built.steps[6]
    assert pass1.argvs[0][:4] == ("vspipe", "-c", "y4m", "-p")
    assert "--pass" in pass1.argvs[1] and os.devnull in pass1.argvs[1]
    assert pass2.argvs[1][-3:] == ("--output", str(job.video_output), "-")
    assert job.job_dir / "video.stats" in pass2.inputs  # pass 1 again means pass 2 again

    runner = FakeRunner()
    state = JobState()
    result = run_job(job, plan, profile, APP, state=state, runner=runner, prober=lambda *_: simulate_output(plan))
    assert result.status is JobStatus.DONE, result.error
    assert "core.std.Crop(clip, left=0, right=0, top=140, bottom=140)" in (job.job_dir / "video.vpy").read_text()
    # FFMS2 (the default) is indexed by core/video/ffindex.py, with progress
    assert tools_called(runner) == ["python", "vspipe", "qaac64", "deezy", "x264", "x264", "mkvmerge"]
    assert runner.calls[0][0][1:3] == ["-m", "videoforge.core.video.ffindex"]

    (job.work_dir / "Show.S01E01.mkv.ffindex").write_bytes(b"index")  # what the real one leaves
    job.video.crop = Crop(0, 138, 0, 138)  # a new crop: script and video again; the index and audio reused
    again = FakeRunner()
    run_job(job, plan, profile, APP, state=state, runner=again, prober=lambda *_: simulate_output(plan))
    assert tools_called(again) == ["vspipe", "x264", "x264", "mkvmerge"]

    job.video.source_filter = SourceFilter.LSMASH  # another filter: its own index, by opening the script
    third = FakeRunner()
    run_job(job, plan, profile, APP, state=state, runner=third, prober=lambda *_: simulate_output(plan))
    assert tools_called(third) == ["vspipe", "vspipe", "x264", "x264", "mkvmerge"]


def test_the_encode_is_timed_by_the_scripts_frame_rate(profile, tmp_path):
    """An IVTC of a 29.97 source: the mux and AutoQPF take the script's 23.976 (vspipe --info), not the source's."""
    plan = make_plan(tmp_path)
    plan.source.video = VideoInfo(720, 480, default_duration_ns=33366667, frames=300)
    job = video_job(plan, tmp_path)
    job.qpf = True
    out = tmp_path / "out" / "Show.S01E01.mkv"
    built = build_steps(job, plan, profile, APP, out)
    step = {s.id: s for s in built.steps}
    ids = [s.id for s in built.steps]
    assert ids.index("index") < ids.index("script.info") < ids.index("chapters")
    assert step["script.info"].argvs == (
        ("vspipe", "--info", str(job.job_dir / "video.vpy"), str(job.job_dir / "video.info.txt")),
    )
    mux = step["mux"].argvs[0]
    assert mux[mux.index("--default-duration") + 1] == "0:30000/1001p"  # before a run: the source's
    assert step["chapters"].key == "30000/1001"

    job.job_dir.mkdir(parents=True)
    (job.job_dir / "video.info.txt").write_text(FakeRunner.script_info, encoding="utf-8")
    mux = step["mux"].refresh().argvs[0]  # once the info step has run
    assert mux[mux.index("--default-duration") + 1] == "0:24000/1001p"
    assert step["chapters"].refresh().key == "24000/1001"

    job.qpf = False  # AutoQPF reads a real source; the rest runs with the fake tools
    runner = FakeRunner()
    result = run_job(job, plan, profile, APP, state=JobState(), runner=runner, prober=lambda *_: simulate_output(plan))
    assert result.status is JobStatus.DONE, result.error
    mux = runner.calls[-1][0]
    assert mux[mux.index("--default-duration") + 1] == "0:24000/1001p"
    assert not [i for i in result.issues if i.code == "video.length"]  # 240 frames at 23.976 = 300 at 29.97


def test_a_vfr_source_keeps_its_timestamps(profile, tmp_path):
    """A VFR source's timestamps (mkvextract) time the encode while they fit the script's frames; an IVTC that
    drops frames is muxed at the script's rate. MP4Box takes none: no timestamps step."""
    plan = make_plan(tmp_path)
    plan.source.video = VideoInfo(1920, 1080, default_duration_ns=41708333, frames=240, vfr=True, id=0)
    job = video_job(plan, tmp_path)
    out = tmp_path / "out" / "Show.S01E01.mkv"
    built = build_steps(job, plan, profile, APP, out)
    step = {s.id: s for s in built.steps}
    ids = [s.id for s in built.steps]
    stamps = job.work_dir / "timestamps.txt"
    raw_stamps = job.work_dir / "timestamps.source.txt"
    argv = ("mkvextract", "--ui-language", "en", "timestamps_v2", str(plan.source.path), f"0:{raw_stamps}")
    assert step["timestamps"].argvs == (argv,) and step["timestamps"].outputs == (raw_stamps,)
    assert ids.index("script.info") < ids.index("timestamps") < ids.index("video")
    mux = step["mux"].argvs[0]
    assert mux[mux.index("--timestamps") + 1] == f"0:{stamps}" and "--default-duration" not in mux  # before a run

    job.job_dir.mkdir(parents=True)
    FakeRunner()([argv], lambda _: None, None)  # 240 timestamps
    step["timestamps.normalize"].call(lambda _: None)
    info_file = job.job_dir / "video.info.txt"
    info_file.write_text(FakeRunner.script_info, encoding="utf-8")  # 240 frames: they fit
    mux = step["mux"].refresh().argvs[0]
    assert mux[mux.index("--timestamps") + 1] == f"0:{stamps}" and "--default-duration" not in mux
    info_file.write_text(FakeRunner.script_info.replace("Frames: 240", "Frames: 192"), encoding="utf-8")
    mux = step["mux"].refresh().argvs[0]  # a decimated script: its own rate
    assert "--timestamps" not in mux and mux[mux.index("--default-duration") + 1] == "0:24000/1001p"

    job.mux = MuxSettings(container="mp4")
    mp4 = build_steps(job, plan, profile, APP, tmp_path / "out" / "Show.S01E01.mp4")
    assert "timestamps" not in [s.id for s in mp4.steps]

    job.mux = MuxSettings()
    shutil.rmtree(job.work_dir)
    runner = FakeRunner()
    result = run_job(job, plan, profile, APP, state=JobState(), runner=runner, prober=lambda *_: simulate_output(plan))
    assert result.status is JobStatus.DONE, result.error
    mux = runner.calls[-1][0]
    assert mux[mux.index("--timestamps") + 1] == f"0:{stamps}"
    assert not [i for i in result.issues if i.code == "video.length"]


def test_a_vfr_mp4_source_is_copied_into_an_mkv_for_its_timestamps(profile, tmp_path):
    """mkvextract reads Matroska only: an MP4's video track is copied into an MKV (mkvmerge) to read them from."""
    plan = make_plan(tmp_path)
    mp4 = tmp_path / "Show.S01E01.mp4"
    mp4.write_bytes(b"x")
    plan.source.path = mp4
    plan.source.video = VideoInfo(1920, 1080, default_duration_ns=41708333, frames=240, vfr=True, id=0)
    job = video_job(plan, tmp_path)
    built = build_steps(job, plan, profile, APP, tmp_path / "out" / "Show.S01E01.mkv")
    step = {s.id: s for s in built.steps}
    ids = [s.id for s in built.steps]
    mkv, stamps = job.work_dir / "timestamps.mkv", job.work_dir / "timestamps.source.txt"
    assert ids.index("timestamps.remux") + 1 == ids.index("timestamps")
    remux = step["timestamps.remux"].argvs[0]
    assert remux[:5] == (APP.tools.mkvmerge, "--ui-language", "en", "--output", str(mkv))
    assert remux[5:8] == ("--video-tracks", "0", "--no-subtitles") and remux[-1] == str(mp4)
    argv = ("mkvextract", "--ui-language", "en", "timestamps_v2", str(mkv), f"0:{stamps}")
    assert step["timestamps"].argvs == (argv,) and step["timestamps"].inputs == (mkv,)


def test_a_script_shorter_than_the_source_warns(profile, tmp_path):
    plan = make_plan(tmp_path)
    plan.source.video = VideoInfo(1920, 1080, default_duration_ns=41708333, frames=480)  # 20 s; the script's 10 s
    job = video_job(plan, tmp_path)
    result = run_job(job, plan, profile, APP, runner=FakeRunner(), prober=lambda *_: simulate_output(plan))
    assert result.status is JobStatus.DONE, result.error
    assert [i.code for i in result.issues if i.severity is Severity.WARN] == ["video.length"]


# --- audio encodes beside the video ------------------------------------------------


def video_job(plan, tmp_path):
    job = JobSpec(
        inputs=JobInputs(plan.source.path, subtitles=plan.inputs.subtitles),
        profile="manual",
        qpf=False,
        output_dir=tmp_path / "out",
    )
    plan.encode_path = job.video_output
    return job


class OverlapRunner(FakeRunner):
    """FakeRunner that notes which tools run at once. A tool in `waits` waits (up to 5 s) until all the
    tools named there for it have started."""

    def __init__(self, waits: dict[str, set[str]] | None = None, fail_on: str | None = None):
        super().__init__(fail_on)
        self.waits = waits or {}
        self.lock = threading.Lock()
        self.cond = threading.Condition(self.lock)
        self.started: set[str] = set()
        self.active: list[str] = []
        self.together: list[set[str]] = []  # who ran at once, at each start

    def __call__(self, argvs, log, cancel):
        measure = "videoforge.core.execute.loudness" in argvs[-1]
        name = "measure" if measure else Path(argvs[-1][0]).stem
        with self.cond:
            self.started.add(name)
            self.active.append(name)
            self.together.append(set(self.active))
            self.cond.notify_all()
            self.cond.wait_for(lambda: self.waits.get(name, set()) <= self.started, timeout=5)
        try:
            super().__call__(argvs, log, cancel)
        finally:
            with self.cond:
                self.active.remove(name)


def test_audio_encodes_run_beside_the_video(profile, tmp_path):
    plan = make_plan(tmp_path)
    job = video_job(plan, tmp_path)
    runner = OverlapRunner(waits={"x264": {"qaac64", "deezy"}, "qaac64": {"x264", "deezy"}, "deezy": {"x264", "qaac64"}})
    state, events = JobState(), []
    app = replace(APP, parallel_audio=2)
    prober = lambda *_: simulate_output(plan)
    result = run_job(job, plan, profile, app, state=state, runner=runner, prober=prober, progress=events.append)
    assert result.status is JobStatus.DONE, result.error
    assert any({"qaac64", "deezy", "x264"} <= t for t in runner.together)
    assert tools_called(runner)[0] == "python" and tools_called(runner)[-1] == "mkvmerge"  # index first, mux last
    assert all(r.status is StepStatus.DONE for r in state.run)
    assert [e.overall for e in events] == sorted(e.overall for e in events)  # it only goes forward
    assert events[-1].overall == pytest.approx(1.0)

    again = OverlapRunner()  # a rerun reuses the background steps like any other
    run_job(job, plan, profile, app, state=state, runner=again, prober=prober)
    assert tools_called(again) == ["python"]  # the fake leaves no index file, so only that runs again


def test_a_target_size_sets_the_two_pass_bitrate(profile, tmp_path):
    """Pass 1 by the planned audio sizes; pass 2 waits for the audio encodes (beside pass 1) and counts their files."""
    plan = make_plan(tmp_path)
    plan.source.video = VideoInfo(1920, 1080, default_duration_ns=41708333, frames=240)
    job = video_job(plan, tmp_path)
    job.encoder = EncoderSettings(rate_control=RateControl.TWO_PASS, target_mb=10)
    out = tmp_path / "out" / "Show.S01E01.mkv"
    built = build_steps(job, plan, profile, APP, out)
    step = {s.id: s for s in built.steps}
    assert set(built.encoded_audio.values()) <= set(step["video.pass2"].inputs)  # so run_steps waits for the audio

    def bitrate(s):
        argv = s.argvs[1]
        return int(argv[argv.index("--bitrate") + 1])

    before = target.budget(10, plan, "mkv", None)
    assert before is not None and bitrate(step["video.pass1"]) == bitrate(step["video.pass2"]) == before.kbps

    runner = OverlapRunner(waits={"x264": {"qaac64", "deezy"}, "qaac64": {"x264", "deezy"}, "deezy": {"x264", "qaac64"}})
    app = replace(APP, parallel_audio=2)
    result = run_job(job, plan, profile, app, state=JobState(), runner=runner, prober=lambda *_: simulate_output(plan))
    assert result.status is JobStatus.DONE, result.error
    assert any({"qaac64", "deezy", "x264"} <= t for t in runner.together)  # pass 1 beside the audio
    encodes = [c[1] for c in runner.calls if Path(c[-1][0]).stem == "x264"]
    found = target.info.read(job.job_dir / target.info.SCRIPT_INFO)
    planned = target.budget(10, plan, "mkv", found)
    encoded = target.budget(10, plan, "mkv", found, built.encoded_audio)
    assert planned is not None and encoded is not None and planned.kbps != encoded.kbps
    assert encoded.audio == 3 * len(built.encoded_audio)  # the fake tools' files
    assert [int(a[a.index("--bitrate") + 1]) for a in encodes] == [planned.kbps, encoded.kbps]


@pytest.mark.parametrize("parallel", [0, 2])
def test_a_normalized_track_is_measured_first(profile, tmp_path, parallel):
    plan = make_plan(tmp_path)
    plan.audio[0].options = {"normalize": "peak"}  # the AAC (ffmpeg | qaac)
    job = video_job(plan, tmp_path)
    built = build_steps(job, plan, profile, APP, tmp_path / "out" / "Show.S01E01.mkv")
    ids = [s.id for s in built.steps]
    assert ids.index("audio.1.measure") + 1 == ids.index("audio.1") and "audio.2.measure" not in ids
    step = {s.id: s for s in built.steps}
    assert step["audio.1.measure"].outputs[0] in step["audio.1"].inputs and step["audio.1"].refresh is not None

    runner = OverlapRunner(waits={"x264": {"measure"}, "measure": {"x264"}} if parallel else {})
    app = replace(APP, parallel_audio=parallel)
    result = run_job(job, plan, profile, app, state=JobState(), runner=runner, prober=lambda *_: simulate_output(plan))
    assert result.status is JobStatus.DONE, result.error
    if parallel:
        assert any({"measure", "x264"} <= t for t in runner.together)  # the measure beside the video
    (ffmpeg, _), *_ = [c for c in runner.calls if Path(c[-1][0]).stem == "qaac64"]
    assert ffmpeg[ffmpeg.index("-af") + 1] == "volume=4.5dB"  # FakeRunner's measure: -4.5 dB


@pytest.mark.parametrize("parallel", [1, 2])
def test_parallel_audio_limit(profile, tmp_path, parallel):
    plan = make_plan(tmp_path)  # a reused encode: only the audio and the mux
    runner = OverlapRunner(waits={"qaac64": {"deezy"}, "deezy": {"qaac64"}} if parallel == 2 else {})
    app = replace(APP, parallel_audio=parallel)
    result = run_plan(plan, tmp_path / "out", profile, app, runner=runner, prober=lambda *_: simulate_output(plan))
    assert result.status is JobStatus.DONE, result.error
    assert max(len(t - {"mkvmerge"}) for t in runner.together) == parallel
    assert not any("mkvmerge" in t and len(t) > 1 for t in runner.together)  # the mux waits for the audio


def test_failed_audio_stops_the_video(profile, tmp_path):
    plan = make_plan(tmp_path)
    job = video_job(plan, tmp_path)

    class Runner(OverlapRunner):
        def __call__(self, argvs, log, cancel):
            if Path(argvs[-1][0]).stem != "x264":
                return super().__call__(argvs, log, cancel)
            with self.cond:
                self.started.add("x264")
                self.cond.notify_all()
            end = time.monotonic() + 5
            while not cancel.cancelled and time.monotonic() < end:
                time.sleep(0.01)
            raise Cancelled()  # the real runner, on the cancel

    runner = Runner(waits={"deezy": {"x264"}}, fail_on="deezy")
    state = JobState()
    result = run_job(job, plan, profile, replace(APP, parallel_audio=2), state=state, runner=runner)
    assert result.status is JobStatus.FAILED and "deezy" in result.error
    status = {r.id: r.status for r in state.run}
    assert status["audio.2"] is StepStatus.FAILED and status["video"] is StepStatus.CANCELLED
    assert status["mux"] is StepStatus.PENDING
    assert result.error.startswith(f"Step {[r.id for r in state.run].index('audio.2') + 1}/")
    assert "mux" not in state.steps and "audio.2" not in state.steps


def test_cancel_stops_the_background_steps(profile, tmp_path):
    plan = make_plan(tmp_path)
    token = CancelToken()

    def runner(argvs, log, cancel):
        token.cancel()  # the user cancels while the first audio encode runs
        while not cancel.cancelled:
            time.sleep(0.01)
        raise Cancelled()

    state = JobState()
    result = run_plan(
        plan, tmp_path / "out", profile, replace(APP, parallel_audio=1), state=state, runner=runner, cancel=token
    )
    assert result.status is JobStatus.CANCELLED
    assert [r.status for r in state.run] == [StepStatus.CANCELLED] + [StepStatus.PENDING] * 3


def test_cancel_token_follows_its_parent():
    parent = CancelToken()
    child = CancelToken(parent)
    child.cancel()
    assert child.cancelled and not parent.cancelled
    other = CancelToken(parent)
    parent.cancel()
    assert other.cancelled


# A tool that starts a child: both print their name, a count and their priority (Windows' class, else the nice
# value) every 20 ms until killed.
_PRIORITY = """
import os

def priority():
    if os.name != "nt":
        return os.getpriority(os.PRIO_PROCESS, 0)
    import ctypes
    k = ctypes.WinDLL("kernel32")
    k.GetCurrentProcess.restype = ctypes.c_void_p
    k.GetPriorityClass.argtypes = [ctypes.c_void_p]
    return k.GetPriorityClass(k.GetCurrentProcess())
"""
_TICKER = (
    _PRIORITY
    + """
import subprocess, sys, time

role = sys.argv[1]
if role == "parent":
    subprocess.Popen([sys.executable, __file__, "child"])
n = 0
while True:
    print(role, n, priority(), flush=True)
    n += 1
    time.sleep(0.02)
"""
)
_IDLE = 0x40 if os.name == "nt" else 19
# Priority.NORMAL leaves a tool at the one it inherits (CI runners may start us below normal)
_INHERITED = int(subprocess.check_output([sys.executable, "-c", _PRIORITY + "print(priority())"]))


class _Ticker:
    """process.run on _TICKER in a thread, with its lines as (role, priority)."""

    def __init__(self, tmp_path: Path, token: CancelToken) -> None:
        script = tmp_path / "ticker.py"
        script.write_text(_TICKER, encoding="utf-8")
        self.token, self.lines, self.error = token, [], None
        self.thread = threading.Thread(target=self._run, args=([[sys.executable, str(script), "parent"]],))
        self.thread.start()

    def _run(self, argvs) -> None:
        try:
            process.run(argvs, self._line, self.token)
        except BaseException as e:
            self.error = e

    def _line(self, line: str) -> None:
        role, _n, prio = line.split("] ", 1)[1].split()
        self.lines.append((role, int(prio)))

    def wait_for(self, check, timeout: float = 10) -> None:
        end = time.monotonic() + timeout
        while not check(list(self.lines)):
            assert time.monotonic() < end and self.thread.is_alive(), self.lines[-5:]
            time.sleep(0.02)

    def both_since(self, n: int):
        return lambda lines: {role for role, _ in lines[n:]} == {"parent", "child"}

    def stop(self) -> None:
        self.token.cancel()
        self.thread.join(10)
        assert isinstance(self.error, Cancelled)


def test_pause_suspends_a_tool_and_its_children(tmp_path):
    ticker = _Ticker(tmp_path, CancelToken())
    try:
        ticker.wait_for(ticker.both_since(0))
        ticker.token.pause()
        time.sleep(0.3)  # lines already written still come in
        n = len(ticker.lines)
        time.sleep(0.5)
        assert len(ticker.lines) == n and ticker.token.paused
        ticker.token.resume()
        ticker.wait_for(ticker.both_since(n))
        assert 0.7 <= ticker.token.paused_seconds < 5 and not ticker.token.paused
    finally:
        ticker.stop()


def test_a_tool_started_while_paused_waits(tmp_path):
    token = CancelToken()
    token.pause()
    ticker = _Ticker(tmp_path, CancelToken(token))  # a step's token: its parent's pause holds
    try:
        time.sleep(0.5)
        assert ticker.lines == []
        token.resume()
        ticker.wait_for(ticker.both_since(0))
    finally:
        ticker.stop()


def test_priority_reaches_a_tool_and_its_children(tmp_path):
    """The tool priority from the start, and a priority chosen while it runs (lowered: raising one back needs
    a privilege on Linux)."""
    ticker = _Ticker(tmp_path, CancelToken(tool_priority=Priority.IDLE, encoder_priority=Priority.HIGH))
    try:
        ticker.wait_for(ticker.both_since(0))
        assert {p for _, p in ticker.lines} == {_IDLE}  # python isn't an encoder
    finally:
        ticker.stop()
    ticker = _Ticker(tmp_path, CancelToken())
    try:
        ticker.wait_for(ticker.both_since(0))
        assert {p for _, p in ticker.lines} == {_INHERITED}
        ticker.token.set_priority(Priority.IDLE)
        assert ticker.token.priority is Priority.IDLE
        n = len(ticker.lines)
        ticker.wait_for(lambda lines: {(r, p) for r, p in lines[n:]} >= {("parent", _IDLE), ("child", _IDLE)})
    finally:
        ticker.stop()


# --- a real job end to end -----------------------------------------------------------

TOOLS = PROJECT_ROOT / "tools"
FFMPEG = shutil.which("ffmpeg")
needs_tools = pytest.mark.skipif(
    FFMPEG is None
    or not (TOOLS / "vs-plugins" / "ffms2.dll").exists()
    or not (TOOLS / "x264" / "x264.exe").exists()
    or not (TOOLS / "MKVToolNix" / "mkvmerge.exe").exists(),
    reason="needs ffmpeg and tools/ (vs-plugins, x264, MKVToolNix)",
)


@needs_tools
@pytest.mark.parametrize("ext", [".mkv", ".mp4", ".ts"])
def test_probe_reads_the_pixel_aspect(tmp_path, ext):
    """An anamorphic source's pixel aspect ratio, whatever the container (a TS has it in the stream only)."""
    from fractions import Fraction

    from videoforge.core.config import load_app_config
    from videoforge.core.probe import probe

    src = tmp_path / f"dvd{ext}"
    subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=duration=1:size=720x480:rate=24",
         "-vf", "setsar=32/27", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", str(src)],
        check=True,
    )  # fmt: skip
    video = probe(src, load_app_config().tools.mkvmerge).video
    assert video is not None and (video.width, video.height) == (720, 480)
    assert abs(video.sar - Fraction(32, 27)) < Fraction(1, 500), video.sar


@needs_tools
def test_real_plan_warns_on_an_unlisted_option(tmp_path):
    """A mistyped x264 option warns in the plan (x264's --fullhelp), before anything runs; a real one doesn't."""
    from videoforge.core.config import load_app_config
    from videoforge.core.job import plan_spec, probe_spec
    from videoforge.profiles import get_profile

    app = load_app_config()
    src = tmp_path / "clip.mkv"
    subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=duration=1:size=320x240:rate=24",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", str(src)],
        check=True,
    )  # fmt: skip
    job = JobSpec(
        inputs=JobInputs(src),
        profile="manual",
        output_dir=tmp_path / "out",
        encoder=EncoderSettings(preset="ultrafast", options={"bframes": "4", "bfrmaes": "4"}),
        qpf=False,
    )
    plan = plan_spec(job, probe_spec(job, app), get_profile("manual"), app.tools)
    unknown = [i for i in plan.issues if i.code == "video.option_unknown"]
    assert len(unknown) == 1 and "--bfrmaes: did you mean --bframes?" in unknown[0].message, plan.issues


@needs_tools
@pytest.mark.parametrize(("keep_ar", "container"), [(False, "mkv"), (True, "mkv"), (False, "mp4")])
def test_real_anamorphic_job_keeps_its_shape(tmp_path, keep_ar, container):
    """A 16:9 DVD (720x480, 32:27 pixels), cropped: as it is, the encode keeps the pixel aspect; resized
    with keep AR, it's square at the cropped picture's aspect. Either way the output plays at the same shape."""
    from fractions import Fraction

    if container == "mp4" and shutil.which("MP4Box") is None:
        pytest.skip("needs MP4Box (GPAC) on PATH")
    from videoforge.core.config import load_app_config
    from videoforge.core.execute.mux import MuxSettings
    from videoforge.core.job import plan_spec, probe_spec
    from videoforge.core.probe import probe
    from videoforge.core.video import vs as vsx
    from videoforge.core.video.settings import Resize
    from videoforge.profiles import get_profile

    app = load_app_config()
    vsx.configure(app.tools.vs_plugins)
    vsx.ensure_vspipe(app.tools.vspipe)
    src = tmp_path / "Movie.2001.mkv"
    subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=duration=1:size=720x480:rate=24",
         "-f", "lavfi", "-i", "sine=duration=1", "-map", "0:v", "-map", "1:a", "-vf", "setsar=32/27",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ac", "2", "-metadata:s:a:0", "language=eng",
         "-y", str(src)],
        check=True,
    )  # fmt: skip
    job = JobSpec(
        inputs=JobInputs(src),
        profile="manual",
        output_dir=tmp_path / "out",
        encoder=EncoderSettings(preset="ultrafast", crf=30),
        qpf=False,
        mux=MuxSettings(container=container),
    )
    job.video.crop = Crop(8, 0, 8, 0)
    if keep_ar:
        job.video.resize = Resize(854, 480, keep_ar=True)
    probed = probe_spec(job, app)
    assert probed.source.video is not None and probed.source.video.sar == Fraction(32, 27)
    job.video.fit_resize(720, 480, probed.source.video.sar)
    profile = get_profile("manual")
    plan = plan_spec(job, probed, profile)
    assert not plan.blocked, plan.issues
    lines: list[str] = []
    result = run_job(job, plan, profile, app, log=lines.append)
    assert result.status is JobStatus.DONE, (result.error, result.issues, lines[-15:])
    out = probe(result.output, app.tools.mkvmerge).video
    assert out is not None
    if keep_ar:
        assert (out.width, out.height, out.sar) == (854, 492, 1)
    else:
        # Matroska keeps a display size in whole pixels (834x480): 417:352, not quite 32:27.
        assert (out.width, out.height) == (704, 480) and abs(out.sar - Fraction(32, 27)) < Fraction(1, 1000)
    assert result.output.suffix == f".{container}"
    shape = Fraction(out.width, out.height) * out.sar
    assert abs(shape / (Fraction(704, 480) * Fraction(32, 27)) - 1) < Fraction(1, 200)


@needs_tools
def test_real_decimated_job_keeps_the_scripts_frame_rate(tmp_path):
    """A 30 fps source a script decimates to 24 (as an IVTC does): the output plays at 24 fps for as long as the
    source, and AutoQPF's chapter keyframe is the 24 fps frame. The source's attachment (a font) goes along."""
    from videoforge.core.config import load_app_config
    from videoforge.core.job import plan_spec, probe_spec
    from videoforge.core.probe import mkvmerge_identify, probe
    from videoforge.core.video import vs as vsx
    from videoforge.core.video.settings import FilterCategory, FilterStep
    from videoforge.profiles import get_profile

    app = load_app_config()
    vsx.configure(app.tools.vs_plugins)
    vsx.ensure_vspipe(app.tools.vspipe)
    src = tmp_path / "Show.S01E01.mkv"
    meta = tmp_path / "chapters.txt"
    meta.write_text(
        ";FFMETADATA1\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=1500\ntitle=Chapter 01\n"
        "[CHAPTER]\nTIMEBASE=1/1000\nSTART=1500\nEND=3000\ntitle=Chapter 02\n",
        encoding="utf-8",
    )
    subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=duration=3:size=320x180:rate=30",
         "-f", "lavfi", "-i", "sine=duration=3", "-i", str(meta), "-map", "0:v", "-map", "1:a", "-map_chapters", "2",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-y", str(tmp_path / "plain.mkv")],
        check=True,
    )  # fmt: skip
    font = tmp_path / "Font.ttf"
    font.write_bytes(b"not really a font")
    subprocess.run(
        [app.tools.mkvmerge, "-q", "-o", str(src), "--attachment-mime-type", "font/ttf", "--attach-file", str(font),
         str(tmp_path / "plain.mkv")],
        check=True,
    )  # fmt: skip
    job = JobSpec(
        inputs=JobInputs(src),
        profile="manual",
        output_dir=tmp_path / "out",
        encoder=EncoderSettings(preset="ultrafast", crf=30),
    )
    decimate = "clip = core.std.SelectEvery(clip, 5, [0, 1, 2, 3])\nclip = core.std.AssumeFPS(clip, fpsnum=24)"
    job.video.filters.insert(0, FilterStep(FilterCategory.FIELD, "Decimate", decimate))
    profile = get_profile("manual")
    plan = plan_spec(job, probe_spec(job, app), profile)
    assert not plan.blocked, plan.issues

    lines: list[str] = []
    result = run_job(job, plan, profile, app, log=lines.append)
    assert result.status is JobStatus.DONE, (result.error, result.issues, lines[-15:])
    assert not [i for i in result.issues if i.code == "video.length"]
    out = probe(result.output, app.tools.mkvmerge)
    assert out.video is not None and out.video.default_duration_ns == pytest.approx(1e9 / 24, abs=2)
    assert out.video.frames == 72  # 3 s at 24 fps
    assert [a["file_name"] for a in mkvmerge_identify(result.output, app.tools.mkvmerge)["attachments"]] == ["Font.ttf"]
    qpf = (job.job_dir / "chapters.qpf").read_text().split()
    assert "36" in qpf and "45" not in qpf  # chapter 2 at 1.5 s: frame 36 at 24 fps (45 at the source's 30)


@needs_tools
@pytest.mark.parametrize("offset", [0, 500])
@pytest.mark.parametrize("encode_audio", [False, True])
def test_real_vfr_job_keeps_the_sources_timestamps(tmp_path, offset, encode_audio):
    """A VFR source (5 s at 23.976 fps, then 4 s at 29.97): the output's timestamps are the source's (StaxRip's
    mkvextract timestamps_v2 + --timestamps), not a constant averaged rate."""
    from videoforge.core.config import load_app_config
    from videoforge.core.job import plan_spec, probe_spec
    from videoforge.core.video import vs as vsx
    from videoforge.profiles import get_profile

    app = load_app_config()
    vsx.configure(app.tools.vs_plugins)
    vsx.ensure_vspipe(app.tools.vspipe)
    raw, src = tmp_path / "video.h264", tmp_path / "Show.S01E01.mkv"
    subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
         "testsrc2=duration=10:size=320x180:rate=24000/1001", "-frames:v", "240", "-c:v", "libx264",
         "-pix_fmt", "yuv420p", "-y", str(raw)],
        check=True,
    )  # fmt: skip
    subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "sine=duration=9", "-c:a", "aac",
         "-y", str(tmp_path / "audio.m4a")],
        check=True,
    )  # fmt: skip
    ms = [i * 1001 / 24 if i < 120 else 120 * 1001 / 24 + (i - 120) * 1001 / 30 for i in range(240)]
    given = tmp_path / "given.txt"
    given.write_text("# timestamp format v2\n" + "".join(f"{t + offset:.6f}\n" for t in ms), encoding="utf-8")
    subtitle = tmp_path / "cue.srt"
    subtitle.write_text("1\n00:00:01,200 --> 00:00:02,000\nTiming cue\n", encoding="utf-8")
    subprocess.run(
        [app.tools.mkvmerge, "-q", "-o", str(src), "--timestamps", f"0:{given}", str(raw), str(tmp_path / "audio.m4a"), str(subtitle)],
        check=True,
    )  # fmt: skip
    job = JobSpec(
        inputs=JobInputs(src),
        profile="manual",
        output_dir=tmp_path / "out",
        encoder=EncoderSettings(preset="ultrafast", crf=30),
    )
    profile = get_profile("manual")
    plan = plan_spec(job, probe_spec(job, app), profile)
    assert plan.source.video is not None and plan.source.video.vfr
    assert not plan.blocked, plan.issues

    if encode_audio:
        plan.audio[0].action = AudioAction.FLAC
        plan.audio[0].out_codec = C.FLAC
    lines: list[str] = []
    result = run_job(job, plan, profile, app, log=lines.append)
    assert result.status is JobStatus.DONE, (result.error, result.issues, lines[-15:])
    assert not [i for i in result.issues if i.code == "video.length"]

    def timestamps(path: Path) -> list[str]:
        out = tmp_path / f"{path.stem}.timestamps.txt"
        subprocess.run([app.tools.mkvextract, str(path), "timestamps_v2", f"0:{out}"], check=True, capture_output=True)
        return out.read_text(encoding="utf-8").splitlines()[1:]

    source_stamps = timestamps(src)
    assert len(source_stamps) == 241  # each frame's, and the last one's end
    assert (
        int(source_stamps[1]) - int(source_stamps[0]) == 42 and int(source_stamps[200]) - int(source_stamps[199]) == 33
    )
    output_stamps = timestamps(result.output)
    assert [float(t) for t in output_stamps[:240]] == [float(t) - offset for t in source_stamps[:240]]
    assert float(output_stamps[240]) == pytest.approx(float(source_stamps[240]) - offset, abs=1)
    from videoforge.core.probe import probe

    output_info = probe(result.output, app.tools.mkvmerge)
    cue = tmp_path / "output.srt"
    subprocess.run(
        [app.tools.mkvextract, str(result.output), "tracks", f"{output_info.subs[0].id}:{cue}"],
        check=True,
        capture_output=True,
    )
    assert ("00:00:00,700" if offset else "00:00:01,200") in cue.read_text(encoding="utf-8")


@needs_tools
def test_real_job_end_to_end(tmp_path):
    """ffmpeg-made source (letterboxed video, English AAC 2.0, chapters) -> crop + x264 + AutoQPF + mux."""
    from videoforge.core.config import load_app_config
    from videoforge.core.job import plan_spec, probe_spec
    from videoforge.core.probe import probe
    from videoforge.core.video import vs as vsx
    from videoforge.profiles import get_profile

    app = load_app_config()
    vsx.configure(app.tools.vs_plugins)
    vsx.ensure_vspipe(app.tools.vspipe)
    src = tmp_path / "Movie.2020.mkv"
    meta = tmp_path / "chapters.txt"
    meta.write_text(
        ";FFMETADATA1\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=1500\ntitle=Chapter 01\n"
        "[CHAPTER]\nTIMEBASE=1/1000\nSTART=1500\nEND=3000\ntitle=Chapter 02\n",
        encoding="utf-8",
    )
    subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=duration=3:size=320x136:rate=24",
         "-f", "lavfi", "-i", "sine=duration=3", "-i", str(meta), "-map", "0:v", "-map", "1:a", "-map_chapters", "2",
         "-vf", "pad=320:180:0:22:black", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ac", "2",
         "-metadata:s:a:0", "language=eng", "-y", str(src)],
        check=True,
    )  # fmt: skip
    srt = tmp_path / "Movie.2020.en.srt"
    srt.write_text("1\n00:00:00,500 --> 00:00:02,000\nHello\n", encoding="utf-8")

    job = JobSpec(
        inputs=JobInputs(src, subtitles=[srt]),
        profile="manual",
        output_dir=tmp_path / "out",
        encoder=EncoderSettings(preset="ultrafast", crf=30),
    )
    job.video.crop = Crop(0, 22, 0, 22)
    profile = get_profile("manual")
    plan = plan_spec(job, probe_spec(job, app), profile)
    assert not plan.blocked, plan.issues
    assert plan.encode_path == job.video_output and plan.chapters_path == job.job_dir / "chapters_chapters.txt"

    lines: list[str] = []
    result = run_job(job, plan, profile, app, log=lines.append)
    assert result.status is JobStatus.DONE, (result.error, result.issues, lines[-15:])
    out = probe(result.output, app.tools.mkvmerge)
    assert (out.video.width, out.video.height) == (320, 136)
    assert [a.language for a in out.audio] == ["en"] and len(out.subs) == 1 and out.has_chapters
    qpf = (job.job_dir / "chapters.qpf").read_text().split()
    assert qpf[:2] == ["0", "K"] and "36" in qpf  # chapter 2 at 1.5 s = frame 36


@needs_tools
@pytest.mark.skipif(shutil.which("MP4Box") is None, reason="needs MP4Box (GPAC) on PATH")
@pytest.mark.parametrize(("embedded", "offset_ms"), [(False, 0), (True, 0), (True, 500)])
def test_real_mp4_job_end_to_end(tmp_path, embedded, offset_ms):
    """MP4 keeps both cue boundaries, including the last cue and a source's nonzero video origin."""
    from videoforge.core.config import load_app_config
    from videoforge.core.execute.mux import MuxSettings
    from videoforge.core.job import plan_spec, probe_spec
    from videoforge.core.models import SubFormat
    from videoforge.core.probe import probe
    from videoforge.core.video import vs as vsx
    from videoforge.profiles import get_profile

    app = load_app_config()
    vsx.configure(app.tools.vs_plugins)
    vsx.ensure_vspipe(app.tools.vspipe)
    src = tmp_path / "Clip.mkv"
    meta = tmp_path / "chapters.txt"
    meta.write_text(
        ";FFMETADATA1\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=1500\ntitle=Start\n"
        "[CHAPTER]\nTIMEBASE=1/1000\nSTART=1500\nEND=3000\ntitle=Middle\n",
        encoding="utf-8",
    )
    subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=duration=3:size=320x180:rate=24",
         "-f", "lavfi", "-i", "sine=duration=3", "-i", str(meta), "-map", "0:v", "-map", "1:a", "-map_chapters", "2",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ac", "2",
         "-metadata:s:a:0", "language=eng", "-y", str(src)],
        check=True,
    )  # fmt: skip
    srt = tmp_path / "Clip.en.srt"
    srt.write_text(
        "1\n00:00:01,200 --> 00:00:02,000\nHello\n\n2\n00:00:02,400 --> 00:00:02,800\nLast\n",
        encoding="utf-8",
    )
    if embedded:
        original = tmp_path / "original.mkv"
        src.replace(original)
        subprocess.run(
            [app.tools.mkvmerge, "-o", str(src), "--sync", f"0:{offset_ms}", str(original),
             "--language", "0:eng", str(srt)],
            check=True, capture_output=True,
        )  # fmt: skip

    job = JobSpec(
        inputs=JobInputs(src, subtitles=[] if embedded else [srt]),
        profile="manual",
        output_dir=tmp_path / "out",
        qpf=False,
        encoder=EncoderSettings(preset="ultrafast", crf=30),
        mux=MuxSettings(container="mp4"),
    )
    profile = get_profile("manual")
    plan = plan_spec(job, probe_spec(job, app), profile, app.tools)
    assert not plan.blocked, plan.issues

    lines: list[str] = []
    result = run_job(job, plan, profile, app, log=lines.append)
    assert result.status is JobStatus.DONE, (result.error, result.issues, lines[-15:])
    assert result.output == tmp_path / "out" / "Clip.mp4"
    out = probe(result.output, app.tools.mkvmerge)
    assert [a.language for a in out.audio] == ["en"] and [s.format for s in out.subs] == [SubFormat.TX3G]
    assert (job.job_dir / "chapters_mp4.txt").read_text().splitlines()[2:4] == [
        "CHAPTER02=00:00:01.500",
        "CHAPTER02NAME=Middle",
    ]
    assert out.has_chapters
    cues = subprocess.run(
        [FFMPEG, "-v", "error", "-i", str(result.output), "-map", "0:s:0", "-f", "srt", "-"],
        check=True, capture_output=True, text=True,
    ).stdout  # fmt: skip
    boundaries = [line for line in cues.splitlines() if "-->" in line]
    assert boundaries == (
        ["00:00:00,700 --> 00:00:01,500", "00:00:01,900 --> 00:00:02,300"]
        if offset_ms
        else ["00:00:01,200 --> 00:00:02,000", "00:00:02,400 --> 00:00:02,800"]
    )


@needs_tools
@pytest.mark.parametrize(("ext", "container"), [(".mp4", "mkv"), (".m2ts", "mkv"), (".m2ts", "mp4"), (".mp4", "mp4")])
def test_real_mp4_and_ts_sources_run_end_to_end(tmp_path, ext, container):
    """An MP4 or a TS source whose audio starts 0.5 s after its video (an MP4's edit list MediaInfo doesn't list,
    a TS's timestamps: ffprobe reads both): one AC-3 track copied, one encoded to FLAC, both still 0.5 s late in
    the output. MediaInfo calls an x264 TS VFR: its timestamps are copied out through an MKV."""
    if container == "mp4" and shutil.which("MP4Box") is None:
        pytest.skip("needs MP4Box (GPAC) on PATH")
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        pytest.skip("needs ffprobe on PATH")
    from videoforge.core.config import load_app_config
    from videoforge.core.job import plan_spec, probe_spec
    from videoforge.core.models import AudioAction, Overrides, TrackOverride
    from videoforge.core.video import vs as vsx
    from videoforge.profiles import get_profile

    app = load_app_config()
    vsx.configure(app.tools.vs_plugins)
    vsx.ensure_vspipe(app.tools.vspipe)
    src, delay = tmp_path / f"Movie.2020{ext}", 0.5
    video, sound = tmp_path / "video.mkv", tmp_path / "audio.mka"
    subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=duration=3:size=320x180:rate=24",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", str(video)],
        check=True,
    )  # fmt: skip
    subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", f"sine=duration={3 - delay}", "-f", "lavfi",
         "-i", f"sine=frequency=880:duration={3 - delay}", "-map", "0", "-map", "1", "-c:a", "ac3", "-y", str(sound)],
        check=True,
    )  # fmt: skip
    # An MP4 is encoded straight in: a stream copy from MKV makes an edit list that hides the first frames.
    picture, codec = (["-i", str(video)], ["-c:v", "copy"]) if ext == ".m2ts" else (
        ["-f", "lavfi", "-i", "testsrc2=duration=3:size=320x180:rate=24"], ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
    )  # fmt: skip
    subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", *picture, "-itsoffset", str(delay), "-i", str(sound),
         "-map", "0:v", "-map", "1:a:0", "-map", "1:a:1", *codec, "-c:a", "copy", "-metadata:s:a:0", "language=eng",
         "-metadata:s:a:1", "language=jpn", "-y", str(src)],
        check=True,
    )  # fmt: skip
    job = JobSpec(
        inputs=JobInputs(src),
        profile="manual",
        output_dir=tmp_path / "out",
        encoder=EncoderSettings(preset="ultrafast", crf=30),
        overrides=Overrides(original_language="en", tracks={"id:2": TrackOverride(action=AudioAction.FLAC)}),
        mux=MuxSettings(container=container),
    )
    profile = get_profile("manual")
    plan = plan_spec(job, probe_spec(job, app), profile, app.tools)
    assert not plan.blocked, plan.issues
    ms = round(delay * 1000)
    assert [(a.source.id, a.source.delay_ms, a.action) for a in plan.audio] == [
        (1, ms, AudioAction.COPY),
        (2, ms, AudioAction.FLAC),
    ]

    lines: list[str] = []
    result = run_job(job, plan, profile, app, log=lines.append)
    assert result.status is JobStatus.DONE, (result.error, result.issues, lines[-15:])
    assert result.output == tmp_path / "out" / f"Movie.2020.{container}"
    shown = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "stream=codec_name,start_time,nb_frames",
         "-of", "json", str(result.output)],
        check=True, capture_output=True, text=True,
    )  # fmt: skip
    streams = json.loads(shown.stdout)["streams"]
    assert [s["codec_name"] for s in streams] == ["h264", "ac3", "flac"]
    assert float(streams[0]["start_time"]) == pytest.approx(0, abs=0.05)
    assert [float(s["start_time"]) for s in streams[1:]] == pytest.approx([delay, delay], abs=0.05)
    if container == "mp4":
        assert streams[0]["nb_frames"] == "72"
    assert (job.job_dir / "chapters.qpf").read_text().split()[:2] == ["0", "K"]


# --- process.run on real subprocesses ---------------------------------------------


def py(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def test_process_run_drops_color_codes():
    lines: list[str] = []
    process.run([py(r"print('\x1b[32mImport results\x1b[0m'); print('\x1b[0m')")], lines.append)
    assert lines == ["[python] Import results"]  # the color-only line is gone too


def test_process_run_streams_lines():
    lines: list[str] = []
    process.run([py("print('a'); print('50%', end='\\r'); print('b')")], lines.append)
    assert [ln.split("] ", 1)[1] for ln in lines] == ["a", "50%", "b"]


def test_process_run_failure_raises_with_tail():
    with pytest.raises(ToolError, match="code 3"):
        process.run([py("import sys; print('boom'); sys.exit(3)")], lambda _l: None)


def test_process_run_pipe(tmp_path):
    out = tmp_path / "piped.bin"
    producer = py("import sys; sys.stdout.buffer.write(b'x' * 300000)")
    consumer = py(f"import sys; open(r'{out}', 'wb').write(sys.stdin.buffer.read())")
    process.run([producer, consumer], lambda _l: None)
    assert out.read_bytes() == b"x" * 300000


def test_process_run_pipe_blames_the_consumer():
    """The consumer quits on bad input; the producer then fails writing: the consumer leads the error."""
    producer = py("import sys\nfor _ in range(100): sys.stdout.buffer.write(b'x' * 65536); sys.stdout.flush()")
    consumer = py("import sys; print('unknown option -- bogus'); sys.exit(4)")
    with pytest.raises(ToolError) as e:
        process.run([producer, consumer], lambda _l: None)
    assert e.value.returncode == 4
    assert str(e.value).startswith(f"{Path(consumer[0]).stem} exited with code 4:\nunknown option -- bogus")
    assert "\n" + Path(producer[0]).stem + " exited with code" in str(e.value)  # the producer's failure follows


@pytest.mark.skipif(os.name != "nt", reason="exit codes are 0-255 on POSIX")
def test_process_run_negative_exit_code():
    with pytest.raises(ToolError) as e:
        process.run([py("import os; os._exit(-1)")], lambda _l: None)
    assert e.value.returncode == -1 and "code -1" in str(e.value)


def test_process_run_cancel():
    token = CancelToken()
    threading.Timer(0.3, token.cancel).start()
    with pytest.raises(Cancelled):
        process.run([py("import time; time.sleep(30)")], lambda _l: None, token)


@pytest.mark.skipif(os.name == "nt", reason="POSIX process groups (Windows: taskkill /T)")
def test_process_run_cancel_ends_the_tools_children(tmp_path):
    """DeeZy starts ffmpeg/DEE: a cancel ends the tool's whole process group, not just the tool."""
    pid_file = tmp_path / "child.pid"
    spawn = (
        "import subprocess, sys, time; "
        "c = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); "
        f"open({str(pid_file)!r}, 'w').write(str(c.pid)); time.sleep(30)"
    )
    token = CancelToken()
    threading.Thread(target=lambda: (_wait_for_file(pid_file), token.cancel()), daemon=True).start()
    with pytest.raises(Cancelled):
        process.run([py(spawn)], lambda _l: None, token)
    child = int(pid_file.read_text())
    for _ in range(50):
        try:
            os.kill(child, 0)  # still there (or a zombie waiting for init to reap it)
        except ProcessLookupError:
            return
        if Path(f"/proc/{child}/stat").is_file() and Path(f"/proc/{child}/stat").read_text().split()[2] == "Z":
            return
        time.sleep(0.1)
    raise AssertionError(f"the tool's child {child} outlived the cancel")


def _wait_for_file(path: Path) -> None:
    for _ in range(100):
        if path.is_file() and path.read_text():
            return
        time.sleep(0.05)


@pytest.mark.skipif(os.name != "nt", reason="Job Objects are Windows only")
def test_process_run_tools_die_with_a_hard_killed_server():
    """TerminateProcess on the process running run() ends the tool and the child it started."""
    import ctypes

    tool = (
        "import os, subprocess, sys, time\n"
        "c = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "print(os.getpid(), c.pid, flush=True)\n"
        "time.sleep(60)"
    )
    server = py(
        "import sys\nfrom videoforge.core.execute import process\n"
        f"process.run([[sys.executable, '-c', {tool!r}]], lambda line: print(line, flush=True))"
    )
    helper = subprocess.Popen(server, stdout=subprocess.PIPE, text=True)
    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    pids: list[int] = []
    handles: list[int] = []
    try:
        pids = [int(p) for p in helper.stdout.readline().split("] ", 1)[1].split()]
        handles = [kernel32.OpenProcess(0x100000, False, pid) for pid in pids]  # SYNCHRONIZE, before the kill
        assert all(handles)
        helper.kill()  # TerminateProcess: no Python cleanup runs
        helper.wait()
        assert [kernel32.WaitForSingleObject(h, 5000) for h in handles] == [0, 0]  # both ended
    finally:
        for h in handles:
            kernel32.CloseHandle(h)
        helper.kill()
        for pid in pids:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, check=False)


def test_progress_only_lines_are_logged_every_tenth(tmp_path: Path):
    from videoforge.core.pipeline.steps import Step, run_steps

    out = tmp_path / "index.ffindex"

    def runner(argvs, log, cancel):
        for pct in range(101):
            log(f"[ffindex] ffms2 index progress {pct}%")
        log("[ffindex] ffms2 index progress 100%")
        for pct in (0, 5, 50, 100):
            log(f"[mkvmerge] Progress: {pct}%")
        log("[x264] [50.0%] 120/240 frames, 30.00 fps")  # an encoder's first line is kept
        out.write_text("idx", encoding="utf-8")

    lines: list[str] = []
    fractions: list[float] = []
    step = Step("index", "Index", argvs=(("ffindex",),), outputs=(out,))
    run_steps([step], {}, log=lines.append, runner=runner, progress=lambda p: fractions.append(p.fraction))
    index_lines = [line for line in lines if "index progress" in line]
    assert [line.rsplit(" ", 1)[1] for line in index_lines] == [f"{n}%" for n in range(0, 101, 10)]
    assert [line for line in lines if "Progress:" in line] == [
        "[mkvmerge] Progress: 0%",
        "[mkvmerge] Progress: 50%",
        "[mkvmerge] Progress: 100%",
    ]
    assert any("[x264]" in line for line in lines)
    assert len(fractions) > 50  # the progress bar still sees every line


def test_encoder_progress_lines_are_logged_every_hundredth(tmp_path: Path):
    from videoforge.core.pipeline.steps import Step, run_steps

    out = tmp_path / "video.hevc"
    frames = 5000

    def runner(argvs, log, cancel):
        for n in range(1, frames + 1):
            log(f"[vspipe] Frame: {n}/{frames} ({n / 10:.1f} fps)")
            log(f"[x265] {n} frames: 6.63 fps, 2617.03 kb/s  ")  # no --frames: no fraction of its own
        log(f"[x265] encoded {frames} frames in 754.12s (6.63 fps), 2600.00 kb/s, Avg QP:30.12")
        out.write_text("hevc", encoding="utf-8")

    lines: list[str] = []
    fractions: list[float] = []
    step = Step("video", "Encode", argvs=(("vspipe",), ("x265",)), outputs=(out,))
    run_steps([step], {}, log=lines.append, runner=runner, progress=lambda p: fractions.append(p.fraction))
    vspipe = [line for line in lines if line.startswith("[vspipe]")]
    x265 = [line for line in lines if line.startswith("[x265]") and "encoded" not in line]
    assert len(vspipe) == 101 and len(x265) == 101  # 0%..100%, not 5000 each
    assert vspipe[0] == f"[vspipe] Frame: 1/{frames} (0.1 fps)" and x265[50].startswith("[x265] 2500 frames:")
    assert lines[-1].startswith("[x265] encoded")  # the summary isn't a progress line
    assert fractions[-1] == 1.0


def test_progress_carries_the_encoders_fps_and_eta(tmp_path: Path):
    from videoforge.core.pipeline.steps import Step, StepProgress, run_steps

    out = tmp_path / "video.264"

    def runner(argvs, log, cancel):
        log("[vspipe] Frame: 36/240 (40.0 fps)")  # it reads ahead of the encoder: its lines move the bar
        log("[x264] [ 10.0%] 24/240 frames, 30.00 fps, 900 kb/s, eta 0:00:08")  # behind: no event, figures kept
        log("[vspipe] Frame: 60/240 (41.0 fps)")
        log("[x264] [ 20.0%] 48/240 frames, 32.50 fps, 900 kb/s, eta 0:00:06")
        log("[vspipe] Frame: 72/240 (41.0 fps)")
        out.write_text("264", encoding="utf-8")

    events: list[StepProgress] = []
    step = Step("video", "Video", argvs=(("vspipe",), ("x264",)), outputs=(out,))
    run_steps([step], {}, log=lambda _line: None, runner=runner, progress=events.append)
    assert [(e.fraction, e.fps, e.eta) for e in events] == [
        (0.0, None, None),
        (0.15, None, None),
        (0.25, 30.0, 8),
        (0.3, 32.5, 6),
        (1.0, 32.5, 6),
    ]


def test_work_dir_is_next_to_the_source_and_separate_from_staxrip(tmp_path: Path):
    from videoforge.core.workdir import remove_work_dir, work_dir

    src = tmp_path / "Show.S01E01.mkv"
    assert work_dir(src) == tmp_path / "Show.S01E01.mkv_tmp"  # StaxRip's is Show.S01E01.mkv_temp
    assert remove_work_dir(src) is False
    (work_dir(src) / "sub").mkdir(parents=True)
    (work_dir(src) / "sub" / "a.ec3").write_bytes(b"x")
    assert remove_work_dir(src) is True and not work_dir(src).exists()


# --- HDR10+ ------------------------------------------------------------------------


def test_hdr10plus_is_carried_into_x265(profile, tmp_path, monkeypatch):
    plan = make_plan(tmp_path)
    assert plan.source.video is not None
    plan.source.video.hdr = VideoHdr(hdr10plus=True)
    job = video_job(plan, tmp_path)
    job.encoder = EncoderSettings(encoder=Encoder.X265, depth=10, preset="fast")
    out = tmp_path / "out" / "Show.S01E01.mkv"
    built = build_steps(job, plan, profile, APP, out)
    ids = [s.id for s in built.steps]
    assert ids.index("hdr10plus") < ids.index("hdr10plus.check") < ids.index("video")
    meta = job.work_dir / "hdr10plus.json"
    extract = next(s for s in built.steps if s.id == "hdr10plus")
    assert extract.argvs[0][-5:] == ("-bsf:v", "hevc_mp4toannexb", "-f", "hevc", "-")
    assert extract.argvs[1] == ("hdr10plus_tool", "extract", "-o", str(meta), "-")
    video = next(s for s in built.steps if s.id == "video").argvs[1]
    assert video[video.index("--dhdr10-info") + 1] == str(meta)

    monkeypatch.setattr(hdr, "script_frames", lambda *_: 240)
    monkeypatch.setattr(hdr, "hdr10plus_frames", lambda _p: 240)
    result = run_job(
        job, plan, profile, APP, state=JobState(), runner=FakeRunner(), prober=lambda *_: simulate_output(plan)
    )
    assert result.status is JobStatus.DONE, result.error

    # Explicitly replace the earlier test output, while checking validation.
    job.output_policy = OutputPolicy.REPLACE
    # the output lost it: invalid
    lost = replace(simulate_output(plan), video=replace(plan.source.video, hdr=VideoHdr()))
    result = run_job(job, plan, profile, APP, state=JobState(), runner=FakeRunner(), prober=lambda *_: lost)
    assert result.status is JobStatus.INVALID
    assert [i.code for i in result.issues] == ["hdr.hdr10plus_missing"]

    # a script with other frames than the metadata stops before the encode
    monkeypatch.setattr(hdr, "script_frames", lambda *_: 238)
    runner = FakeRunner()
    result = run_job(job, plan, profile, APP, state=JobState(), runner=runner, prober=lambda *_: simulate_output(plan))
    assert result.status is JobStatus.FAILED and "238 frames" in (result.error or "")
    assert "x265" not in tools_called(runner)


@pytest.mark.parametrize(
    ("encoder", "depth", "on", "codes"),
    [
        (Encoder.X264, 8, True, ["hdr.hdr10plus_x264"]),
        (Encoder.X265, 8, True, ["hdr.hdr10plus_depth"]),
        (Encoder.X265, 10, False, []),
        (Encoder.X265, 10, True, []),
    ],
)
def test_hdr10plus_plan(profile, tmp_path, encoder, depth, on, codes):
    plan = make_plan(tmp_path)
    assert plan.source.video is not None
    plan.source.video.hdr = VideoHdr(hdr10plus=True)
    job = video_job(plan, tmp_path)
    job.encoder = EncoderSettings(encoder=encoder, depth=depth, hdr10plus=on)
    tools = replace(APP.tools, hdr10plus_tool=fake_tool_files("hdr10plus_tool")["hdr10plus_tool"])
    assert [i.code for i in hdr.issues(plan.source.video, job.encoder, tools)] == codes
    built = build_steps(job, plan, profile, APP, tmp_path / "out" / "Show.S01E01.mkv")
    carried = encoder is Encoder.X265 and on
    assert ("hdr10plus" in [s.id for s in built.steps]) is carried
    missing = replace(APP.tools, hdr10plus_tool=str(tmp_path / "nope.exe"))
    found = [i.code for i in hdr.issues(plan.source.video, job.encoder, missing)]
    assert ("tools.missing" in found) is carried


# --- Dolby Vision ------------------------------------------------------------------


def dv_job(plan, tmp_path, **encoder):
    assert plan.source.video is not None
    plan.source.video.hdr = VideoHdr(dv_profile=8, dv_compat=1, dv_level=6, dv_layers="BL+RPU")
    plan.source.video.color = replace(plan.source.video.color, master_display="G(13250,34500)B(7500,3000)")
    job = video_job(plan, tmp_path)
    settings = {"encoder": Encoder.X265, "depth": 10, "options": {"vbv-maxrate": "40000", "vbv-bufsize": "40000"}}
    job.encoder = EncoderSettings(preset="fast", **(settings | encoder))
    return job


def test_dolby_vision_is_carried_into_x265(profile, tmp_path, monkeypatch):
    plan = make_plan(tmp_path)
    job = dv_job(plan, tmp_path)
    out = tmp_path / "out" / "Show.S01E01.mkv"
    built = build_steps(job, plan, profile, APP, out)
    ids = [s.id for s in built.steps]
    assert ids.index("dovi.rpu") < ids.index("dovi.edit") < ids.index("dovi.check") < ids.index("video")
    source_rpu, rpu = job.work_dir / "dv_source.bin", job.job_dir / "dv_rpu.bin"  # the source's; the job's crop
    extract = next(s for s in built.steps if s.id == "dovi.rpu")
    assert extract.argvs[1] == ("dovi_tool", "-m", "0", "extract-rpu", "-", "-o", str(source_rpu))
    video = next(s for s in built.steps if s.id == "video").argvs[1]
    i = video.index("--dolby-vision-profile")
    assert video[i : i + 4] == ("--dolby-vision-profile", "8.1", "--dolby-vision-rpu", str(rpu))

    edits = []

    def edit(_dovi, src, dst, video_settings, width, height, log, profile):
        edits.append((src, video_settings.crop, profile))
        dst.write_bytes(b"rpu")

    monkeypatch.setattr(hdr, "edit_rpu", edit)
    monkeypatch.setattr(hdr, "script_frames", lambda *_: 240)
    monkeypatch.setattr(hdr, "rpu_frames", lambda *_: 240)
    dv = replace(plan.source.video, hdr=VideoHdr(dv_profile=8, dv_compat=1))
    carried = replace(simulate_output(plan), video=dv)
    result = run_job(job, plan, profile, APP, state=JobState(), runner=FakeRunner(), prober=lambda *_: carried)
    assert result.status is JobStatus.DONE, result.error
    assert edits == [(source_rpu, job.video.crop, "8.1")]

    # Explicitly replace the earlier test output, while checking validation.
    job.output_policy = OutputPolicy.REPLACE
    # the output lost it: invalid
    lost = replace(simulate_output(plan), video=replace(plan.source.video, hdr=VideoHdr()))
    result = run_job(job, plan, profile, APP, state=JobState(), runner=FakeRunner(), prober=lambda *_: lost)
    assert result.status is JobStatus.INVALID
    assert [i.code for i in result.issues] == ["hdr.dv_missing"]

    # a script with other frames than the RPU stops before the encode
    monkeypatch.setattr(hdr, "script_frames", lambda *_: 238)
    runner = FakeRunner()
    result = run_job(job, plan, profile, APP, state=JobState(), runner=runner, prober=lambda *_: carried)
    assert result.status is JobStatus.FAILED and "238 frames" in (result.error or "")
    assert "x265" not in tools_called(runner)


def test_dolby_vision_profile_5_stays_profile_5(profile, tmp_path, monkeypatch):
    """A profile 5 source (no HDR10 layer, no mastering display) is written as profile 5, as StaxRip does: the RPU
    edited as it is (mode 0) but for its L5, and the output checked for profile 5."""
    plan = make_plan(tmp_path)
    job = dv_job(plan, tmp_path)
    video = plan.source.video
    video.hdr = VideoHdr(dv_profile=5, dv_level=9, dv_layers="BL+RPU")
    video.color = replace(video.color, master_display="", range="full")
    assert hdr.issues(video, job.encoder, None, job.video) == []
    built = build_steps(job, plan, profile, APP, tmp_path / "out" / "Show.S01E01.mkv")
    step = {s.id: s for s in built.steps}
    argv = step["video"].argvs[1]
    i = argv.index("--dolby-vision-profile")
    assert argv[i : i + 2] == ("--dolby-vision-profile", "5") and "--hdr10" not in argv
    assert step["dovi.edit"].label == "Dolby Vision RPU: crop, resize, profile 5"
    assert hdr.rpu_edit({}, job.video, 1920, 1080, "5") == {"mode": 0}

    edits = []

    def edit(_dovi, src, dst, video_settings, width, height, log, profile):
        edits.append(profile)
        dst.write_bytes(b"rpu")

    monkeypatch.setattr(hdr, "edit_rpu", edit)
    monkeypatch.setattr(hdr, "script_frames", lambda *_: 240)
    monkeypatch.setattr(hdr, "rpu_frames", lambda *_: 240)
    carried = replace(simulate_output(plan), video=replace(video, hdr=VideoHdr(dv_profile=5)))
    result = run_job(job, plan, profile, APP, state=JobState(), runner=FakeRunner(), prober=lambda *_: carried)
    assert result.status is JobStatus.DONE, result.error
    assert edits == ["5"]
    job.output_policy = OutputPolicy.REPLACE
    as_81 = replace(simulate_output(plan), video=replace(video, hdr=VideoHdr(dv_profile=8, dv_compat=1)))
    result = run_job(job, plan, profile, APP, state=JobState(), runner=FakeRunner(), prober=lambda *_: as_81)
    assert result.status is JobStatus.INVALID
    assert [i.message for i in result.issues] == ["The output has Dolby Vision 8.1, not 5"]


@pytest.mark.parametrize(
    ("hdr_info", "encoder", "codes"),
    [
        ({}, {}, []),
        ({}, {"dolby_vision": False}, []),
        ({}, {"encoder": Encoder.X264, "depth": 8}, ["hdr.dv_x264"]),
        ({}, {"depth": 8}, ["hdr.dv_depth"]),
        ({}, {"options": {}}, ["hdr.dv_vbv"]),
        ({}, {"options": {}, "extra": "--vbv-maxrate 1000 --vbv-bufsize=1000"}, []),
        ({}, {"options": {"level-idc": "5.1"}}, []),
        ({}, {"options": {"level-idc": "4.4"}}, ["hdr.dv_vbv"]),
        ({}, {"source_color": False}, ["hdr.dv_master"]),
        ({"dv_profile": 5, "dv_compat": None}, {}, []),
        ({"dv_profile": 5, "dv_compat": None}, {"source_color": False}, []),  # no HDR10 layer: no mastering display
        ({"dv_profile": 5, "dv_compat": None}, {"depth": 8}, ["hdr.dv_depth"]),
        ({"dv_profile": 5, "dv_compat": None}, {"dolby_vision": False}, ["hdr.dv_profile5"]),
        ({"dv_profile": 5, "dv_compat": None}, {"encoder": Encoder.X264, "depth": 10}, ["hdr.dv_profile5"]),
        ({"dv_compat": 4}, {}, ["hdr.dv_hlg"]),
        ({"dv_compat": 4}, {"dolby_vision": False}, []),
        ({"dv_profile": 7, "dv_compat": 6, "dv_el": "MEL"}, {}, []),
        ({"dv_profile": 7, "dv_compat": 6, "dv_el": "FEL"}, {}, []),
        ({"dv_profile": 7, "dv_compat": 6, "dv_el": ""}, {}, ["hdr.dv_el"]),
    ],
)
def test_dolby_vision_plan(profile, tmp_path, hdr_info, encoder, codes):
    plan = make_plan(tmp_path)
    job = dv_job(plan, tmp_path, **encoder)
    video = plan.source.video
    video.hdr = replace(video.hdr, **hdr_info)
    tools = replace(APP.tools, dovi_tool=fake_tool_files("dovi_tool")["dovi_tool"])
    assert [i.code for i in hdr.issues(video, job.encoder, tools, job.video)] == codes
    missing = replace(APP.tools, dovi_tool=str(tmp_path / "nope.exe"))
    assert ("tools.missing" in [i.code for i in hdr.issues(video, job.encoder, missing)]) is (
        hdr.keeps_dv(video, job.encoder)
    )


def test_dolby_vision_custom_script_blocks(tmp_path):
    plan = make_plan(tmp_path)
    job = dv_job(plan, tmp_path)
    job.video.custom = "clip = src"
    assert [i.code for i in hdr.issues(plan.source.video, job.encoder, None, job.video)] == ["hdr.dv_custom"]


def fel_job(plan, tmp_path, **encoder):
    job = dv_job(plan, tmp_path, **encoder)
    plan.source.video.hdr = VideoHdr(dv_profile=7, dv_compat=6, dv_level=6, dv_layers="BL+EL+RPU", dv_el="FEL")
    plan.source.video.color = replace(
        plan.source.video.color,
        master_display="G(13250,34500)B(7500,3000)R(34000,16000)WP(15635,16450)L(10000000,1)",
        max_cll=1000,
        max_fall=400,
    )
    return job


@pytest.mark.parametrize(("source_filter", "codes"), [(SourceFilter.FFMS2, []), (SourceFilter.LSMASH, []),
                                                      (SourceFilter.BESTSOURCE, ["hdr.dv_bake_bs"])])  # fmt: skip
def test_fel_bake_needs_ffms2_or_lsmas(tmp_path, source_filter, codes):
    plan = make_plan(tmp_path)
    job = fel_job(plan, tmp_path)
    job.video.source_filter = source_filter
    assert [i.code for i in hdr.issues(plan.source.video, job.encoder, None, job.video)] == codes


SUMMARY = """Summary:
  Frames: 240
  Profile: 7 (FEL)
  RPU mastering display: 0.0050/4000 nits
  RPU content light level (L1): MaxCLL: {l1} nits, MaxFALL: {l1f} nits
  L6 metadata: Mastering display: 0.0050/4000 nits. MaxCLL: 2573 nits, MaxFALL: 684 nits
"""


@pytest.mark.parametrize(("l1", "l1f", "cll"), [("1523.75", "301.20", (1523, 301)), ("0.01", "0.00", (2573, 684))])
def test_fel_color_from_the_rpu(l1, l1f, cll):
    source = VideoColor(
        master_display="G(13250,34500)B(7500,3000)R(34000,16000)WP(15635,16450)L(10000000,1)",
        max_cll=1000,
        max_fall=400,
    )
    got = hdr.fel_color(source, SUMMARY.format(l1=l1, l1f=l1f))
    assert got.master_display == "G(13250,34500)B(7500,3000)R(34000,16000)WP(15635,16450)L(40000000,50)"
    assert (got.max_cll, got.max_fall) == cll
    # no L1 or L6 light level: the source's
    bare = hdr.fel_color(source, "RPU mastering display: 0.0001/1000 nits")
    assert (bare.master_display.endswith("L(10000000,1)"), bare.max_cll, bare.max_fall) == (True, 1000, 400)


@pytest.mark.parametrize("source_filter", [SourceFilter.FFMS2, SourceFilter.LSMASH])
def test_fel_is_baked_into_the_encode(profile, tmp_path, monkeypatch, source_filter):
    plan = make_plan(tmp_path)
    job = fel_job(plan, tmp_path)
    job.video.source_filter = source_filter
    out = tmp_path / "out" / "Show.S01E01.mkv"
    built = build_steps(job, plan, profile, APP, out)
    ids = [s.id for s in built.steps]
    work = job.work_dir
    el, hevc = work / "dv_el.mkv", work / "dv_el.hevc"
    assert ids.index("script") < ids.index("dovi.el") < ids.index("dovi.el_mkv") < ids.index("index")
    assert ("dovi.el_index" in ids) is (source_filter is SourceFilter.FFMS2)
    step = {s.id: s for s in built.steps}
    assert step["dovi.el"].argvs[1] == ("dovi_tool", "demux", "--el-only", "-", "-e", str(hevc))
    assert step["dovi.el_mkv"].argvs[0][1:] == ("-o", str(el), "--default-duration", "0:41708333ns", str(hevc))
    text = (step["script"].key or "").splitlines()
    assert text.index("clip = src") < text.index("clip = core.fel.Bake(clip, _vf_el, no_resample=1)")
    assert "clip = core.std.SetFrameProps(clip, _Range=vs.RANGE_LIMITED)" in text
    assert any(line.startswith("_vf_el = core.") and repr(str(el)) in line for line in text)
    # before a run (no RPU yet) the encode shows the source's HDR10 values
    video = step["video"].argvs[1]
    assert video[video.index("--max-cll") + 1] == "1000,400"

    monkeypatch.setattr(hdr, "edit_rpu", lambda _d, _s, dst, *_a: dst.write_bytes(b"rpu"))
    monkeypatch.setattr(hdr, "script_frames", lambda *_: 240)
    monkeypatch.setattr(hdr, "rpu_frames", lambda *_: 240)
    monkeypatch.setattr(hdr, "rpu_summary", lambda *_: SUMMARY.format(l1="0.01", l1f="0.00"))
    runner = FakeRunner()
    carried = replace(simulate_output(plan), video=replace(plan.source.video, hdr=VideoHdr(dv_profile=8, dv_compat=1)))
    state = JobState()
    result = run_job(job, plan, profile, APP, state=state, runner=runner, prober=lambda *_: carried)
    assert result.status is JobStatus.DONE, result.error
    # the encode ran with the RPU's values (L6 here: L1 reads 0), and its Log tab line says so
    x265 = next(c[-1] for c in runner.calls if Path(c[-1][0]).stem == "x265")
    assert x265[x265.index("--max-cll") + 1] == "2573,684"
    assert x265[x265.index("--master-display") + 1].endswith("L(40000000,50)")
    assert "--max-cll 2573,684" in next(r.command for r in state.run if r.id == "video")
    # a rerun reuses the encode (its fingerprint has the RPU's values)
    runner = FakeRunner()
    result = run_job(job, plan, profile, APP, state=state, runner=runner, prober=lambda *_: carried)
    assert result.status is JobStatus.DONE, result.error
    assert "x265" not in tools_called(runner)


@pytest.mark.parametrize("policy", list(OutputPolicy))
def test_existing_output_policy(profile, tmp_path, policy):
    plan = make_plan(tmp_path)
    out = tmp_path / "out/Show.S01E01.mkv"
    out.parent.mkdir()
    out.write_bytes(b"previous good output")
    runner = FakeRunner()
    result = run_plan(
        plan, out.parent, profile, APP, output_policy=policy, runner=runner, prober=lambda *_: simulate_output(plan)
    )
    if policy in (OutputPolicy.STOP, OutputPolicy.SKIP):
        assert result.status is (JobStatus.FAILED if policy is OutputPolicy.STOP else JobStatus.SKIPPED)
        assert not runner.calls
    else:
        assert result.status is JobStatus.DONE, result.error
        assert result.output.name == ("Show.S01E01.2.mkv" if policy is OutputPolicy.RENAME else out.name)
    if policy is not OutputPolicy.REPLACE:
        assert out.read_bytes() == b"previous good output"


def test_invalid_replacement_preserves_good_output(profile, tmp_path):
    plan = make_plan(tmp_path)
    out = tmp_path / "out/Show.S01E01.mkv"
    out.parent.mkdir()
    out.write_bytes(b"previous good output")
    bad = simulate_output(plan)
    bad.subs[0].title = "Wrong"
    result = run_plan(
        plan, out.parent, profile, APP, output_policy=OutputPolicy.REPLACE, runner=FakeRunner(), prober=lambda *_: bad
    )
    assert result.status is JobStatus.INVALID
    assert out.read_bytes() == b"previous good output"
    assert result.output != out and result.output.is_file()
    assert ".unpublished-" in result.output.name


@pytest.mark.parametrize("existing", [False, True])
def test_output_changed_during_run_is_never_replaced(profile, tmp_path, existing):
    plan = make_plan(tmp_path)
    out = tmp_path / "out/Show.S01E01.mkv"
    out.parent.mkdir()
    if existing:
        out.write_bytes(b"old output")

    def probe_candidate(path, _tool):
        assert path.suffix == ".partial"
        out.write_bytes(b"another application's output")
        return simulate_output(plan)

    result = run_plan(
        plan, out.parent, profile, APP, output_policy=OutputPolicy.REPLACE, runner=FakeRunner(), prober=probe_candidate
    )
    assert result.status is JobStatus.FAILED and "changed during" in result.error
    assert out.read_bytes() == b"another application's output"
    assert result.output != out and result.output.is_file()
