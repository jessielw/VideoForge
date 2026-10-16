"""The pipeline: steps with a fake tool runner (order, resume, failures), a real job end to end,
and process.run on real subprocesses."""

from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading

from conftest import audio, plan_for, simulate_output, source, sub
import pytest

from videoforge.core.config import PROJECT_ROOT, AppConfig, Tools
from videoforge.core.execute import process
from videoforge.core.execute.process import Cancelled, CancelToken, ToolError
from videoforge.core.job import JobSpec, JobState, JobStatus, StepStatus
from videoforge.core.models import (
    AudioAction,
    AudioCodec as C,
    Issue,
    JobInputs,
    Layout,
    Plan,
    Severity,
    SubFormat as F,
    VideoInfo,
)
from videoforge.core.pipeline.build import build_steps
from videoforge.core.pipeline.run import run_job, run_plan
from videoforge.core.video.settings import Crop, EncoderSettings, RateControl, SourceFilter


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
    )
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
        for flag in ("-o", "--output", "--stats"):
            if flag in last and last[last.index(flag) + 1] != os.devnull:
                Path(last[last.index(flag) + 1]).write_bytes(b"out")
        log(f"[{Path(last[0]).stem}] [ 50.0%] 1/2 frames")


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
    work = tmp_path / "Show.S01E01.mkv_tmp"  # the encodes stay in <source>_tmp for fix mode
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
    again = run_plan(plan, tmp_path / "out", profile, APP, runner=lambda *_: None)  # no state: nothing reused
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
    assert [s.id for s in built.steps] == ["script", "index", "video.pass1", "video.pass2", "audio.1", "audio.2", "mux"]
    pass1, pass2 = built.steps[2], built.steps[3]
    assert pass1.argvs[0][:4] == ("vspipe", "-c", "y4m", "-p")
    assert "--pass" in pass1.argvs[1] and os.devnull in pass1.argvs[1]
    assert pass2.argvs[1][-3:] == ("--output", str(job.video_output), "-")
    assert job.work_dir / "video.stats" in pass2.inputs  # pass 1 again means pass 2 again

    runner = FakeRunner()
    state = JobState()
    result = run_job(job, plan, profile, APP, state=state, runner=runner, prober=lambda *_: simulate_output(plan))
    assert result.status is JobStatus.DONE, result.error
    assert "core.std.Crop(clip, left=0, right=0, top=140, bottom=140)" in (job.work_dir / "video.vpy").read_text()
    # FFMS2 (the default) is indexed by core/video/ffindex.py, with progress
    assert tools_called(runner) == ["python", "x264", "x264", "qaac64", "deezy", "mkvmerge"]
    assert runner.calls[0][0][1:3] == ["-m", "videoforge.core.video.ffindex"]

    (job.work_dir / "Show.S01E01.mkv.ffindex").write_bytes(b"index")  # what the real one leaves
    job.video.crop = Crop(0, 138, 0, 138)  # a new crop: script and video again; the index and audio reused
    again = FakeRunner()
    run_job(job, plan, profile, APP, state=state, runner=again, prober=lambda *_: simulate_output(plan))
    assert tools_called(again) == ["x264", "x264", "mkvmerge"]

    job.video.source_filter = SourceFilter.LSMASH  # another filter: its own index, by opening the script
    third = FakeRunner()
    run_job(job, plan, profile, APP, state=state, runner=third, prober=lambda *_: simulate_output(plan))
    assert tools_called(third) == ["vspipe", "x264", "x264", "mkvmerge"]


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
    assert plan.encode_path == job.video_output and plan.chapters_path == job.work_dir / "chapters_chapters.txt"

    lines: list[str] = []
    result = run_job(job, plan, profile, app, log=lines.append)
    assert result.status is JobStatus.DONE, (result.error, result.issues, lines[-15:])
    out = probe(result.output, app.tools.mkvmerge)
    assert (out.video.width, out.video.height) == (320, 136)
    assert [a.language for a in out.audio] == ["en"] and len(out.subs) == 1 and out.has_chapters
    qpf = (job.work_dir / "chapters.qpf").read_text().split()
    assert qpf[:2] == ["0", "K"] and "36" in qpf  # chapter 2 at 1.5 s = frame 36


@needs_tools
@pytest.mark.skipif(shutil.which("MP4Box") is None, reason="needs MP4Box (GPAC) on PATH")
def test_real_mp4_job_end_to_end(tmp_path):
    """The same kind of source muxed to MP4: the source's chapters converted, an SRT as timed text."""
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
    srt.write_text("1\n00:00:00,500 --> 00:00:02,000\nHello\n", encoding="utf-8")

    job = JobSpec(
        inputs=JobInputs(src, subtitles=[srt]),
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
    assert (job.work_dir / "chapters_mp4.txt").read_text().splitlines()[2:4] == [
        "CHAPTER02=00:00:01.500",
        "CHAPTER02NAME=Middle",
    ]
    assert out.has_chapters


# --- process.run on real subprocesses ---------------------------------------------


def py(code: str) -> list[str]:
    return [sys.executable, "-c", code]


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
        log("[x264] [50.0%] 120/240 frames, 30.00 fps")  # an encoder's line says more: always kept
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
