"""Audio normalize: the measure step, the filter the encode applies, and the steps that run them."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading

from conftest import audio
import pytest

from videoforge.core.config import Tools
from videoforge.core.execute import loudness
from videoforge.core.execute.audio import (
    AudioSettings,
    audio_command,
    measure_argv,
    measure_path,
    needs_measure,
    normalize_filter,
)
from videoforge.core.models import AudioAction as A, AudioCodec as C, Layout, PlannedAudio
from videoforge.core.pipeline.steps import Step, run_steps

TOOLS = Tools(mkvmerge="mkvmerge", deezy="deezy", dee="dee", truehdd="truehdd", qaac="qaac64", ffmpeg="ffmpeg")
SRC = Path("Movie.mkv")
LOUDNORM = {"input_i": -30.5, "input_tp": -9.25, "input_lra": 6.1, "input_thresh": -40.71, "target_offset": 0.33}


def planned(action: A, layout: str = "2.0", out: str | None = None, **options: str) -> PlannedAudio:
    track = audio(C.FLAC, layout, index=1)
    track.sample_rate = 44100
    return PlannedAudio(
        source=track,
        action=action,
        out_codec=C.FLAC,
        out_layout=Layout.parse(out or layout),
        out_atmos=False,
        bitrate_kbps=None if action in (A.FLAC, A.AAC) else 256,
        upmix_50=False,
        language="en",
        title="",
        default=True,
        options=options,
    )


def af(argv: tuple[str, ...]) -> str:
    return argv[argv.index("-af") + 1]


def test_off_by_default_and_never_for_deezy():
    assert normalize_filter(planned(A.FLAC), None) == ""
    assert not needs_measure(planned(A.FLAC)) and not needs_measure(planned(A.COPY))
    assert not needs_measure(planned(A.DDP, normalize="loudnorm"))  # DEE measures its own dialogue level
    (argv,) = audio_command(planned(A.FLAC), 1, SRC, Path("w"), AudioSettings(), TOOLS).argvs
    assert af(argv) == "aformat=channel_layouts=stereo"


def test_dynaudnorm_is_one_pass():
    p = planned(A.FLAC, normalize="dynaudnorm")
    assert not needs_measure(p)
    (argv,) = audio_command(p, 1, SRC, Path("w"), AudioSettings(), TOOLS).argvs
    assert af(argv) == "aformat=channel_layouts=stereo,dynaudnorm"


def test_peak_raises_to_0_db():
    p = planned(A.OPUS, normalize="peak")
    assert needs_measure(p)
    assert normalize_filter(p, None) == ""  # nothing measured yet
    assert normalize_filter(p, {"max_volume": -3.47}) == "volume=3.5dB"
    assert normalize_filter(p, {"max_volume": 0.0}) == ""  # already peaks at 0 dB
    assert normalize_filter(p, {}) == ""  # silence


def test_loudnorm_second_pass_takes_the_measured_values():
    p = planned(A.FLAC, normalize="loudnorm", loudnorm_i="-16", loudnorm_tp="-1.5")
    assert needs_measure(p)
    assert normalize_filter(p, None) == "loudnorm=I=-16:TP=-1.5:LRA=7,aresample=44100"  # until measured: one pass
    assert normalize_filter(p, LOUDNORM) == (
        "loudnorm=I=-16:TP=-1.5:LRA=7:measured_I=-30.50:measured_TP=-9.25:measured_LRA=6.10:"
        "measured_thresh=-40.71:offset=0.33:linear=true,aresample=44100"
    )
    assert normalize_filter(p, {}) == ""  # silence: no loudness to set
    (argv,) = audio_command(p, 1, SRC, Path("w"), AudioSettings(), TOOLS, LOUDNORM).argvs
    assert af(argv).startswith("aformat=channel_layouts=stereo,loudnorm=I=-16:")


def test_measure_reads_what_the_encode_will():
    p = planned(A.EAC3, "7.1", "5.1", normalize="loudnorm")
    argv = measure_argv(p, SRC, Path("w/m.json"), TOOLS)
    assert argv[:6] == (sys.executable, "-m", "videoforge.core.execute.loudness", str(Path("w/m.json")), "0", "ffmpeg")
    assert argv[argv.index("-map") + 1] == "0:a:1" and argv[-3:] == ("-f", "null", "-")
    assert af(argv) == "aformat=channel_layouts=5.1,loudnorm=I=-24:TP=-2:LRA=7:print_format=json"
    p.options["normalize"] = "peak"
    p.source.duration_ms = 5000
    argv = measure_argv(p, SRC, Path("m.json"), TOOLS)
    assert af(argv) == "aformat=channel_layouts=5.1,volumedetect" and argv[4] == "5000"
    assert measure_path(p, 2, Path("w")) == Path("w/audio2_en.loudness.json")


def test_qaac_normalizes_after_its_downmix():
    down = planned(A.AAC, "5.1", "2.0", normalize="loudnorm")
    ffmpeg, _ = audio_command(down, 1, SRC, Path("w"), AudioSettings(), TOOLS, LOUDNORM).argvs
    assert af(ffmpeg).startswith("aformat=channel_layouts=stereo,loudnorm=")
    assert af(measure_argv(down, SRC, Path("m"), TOOLS)).startswith("aformat=channel_layouts=stereo,loudnorm=")
    same = planned(A.AAC, "2.0", normalize="peak")  # -ac keeps the source's layout: no aformat
    ffmpeg, _ = audio_command(same, 1, SRC, Path("w"), AudioSettings(), TOOLS, {"max_volume": -1.0}).argvs
    assert af(ffmpeg) == "volume=1.0dB" and af(measure_argv(same, SRC, Path("m"), TOOLS)) == "volumedetect"
    ffmpeg, _ = audio_command(planned(A.AAC, "5.1", "2.0"), 1, SRC, Path("w"), AudioSettings(), TOOLS).argvs
    assert "-af" not in ffmpeg  # not normalizing: as before


def test_parse_ffmpeg_output():
    assert loudness.parse("[Parsed_volumedetect_0 @ 0x1] mean_volume: -20.1 dB\n[...] max_volume: -3.2 dB") == {
        "max_volume": -3.2
    }
    assert loudness.parse("max_volume: -inf dB") == {}
    block = json.dumps({k: str(v) for k, v in LOUDNORM.items()} | {"output_i": "-24.0", "normalization_type": "x"})
    assert loudness.parse(f"[Parsed_loudnorm_0 @ 0x1]\n{block}\n[out#0/null] size=N/A") == LOUDNORM
    silent = json.dumps({"input_i": "-inf", "input_tp": "-inf", "input_lra": "0.00", "input_thresh": "-inf"})
    assert loudness.parse(silent) == {"input_lra": 0.0}
    assert loudness.parse("nothing here") is None


def test_measure_beside_the_video(tmp_path):
    """The measure and the encode run on their own threads; the video doesn't wait for the measure, and the encode
    takes what the measure wrote (refreshed on its thread, after it)."""
    found, encoded, video = tmp_path / "m.json", tmp_path / "a.flac", tmp_path / "v.hevc"
    video_started = threading.Event()
    calls: list[tuple[str, ...]] = []

    def runner(argvs, log, cancel):
        (argv,) = argvs
        calls.append(tuple(argv))
        if argv[0] == "measure":
            assert video_started.wait(5)  # the video runs while this does
            found.write_text(json.dumps({"max_volume": -6.0}))
        elif argv[0] == "video":
            video_started.set()
            video.write_bytes(b"v")
        else:
            encoded.write_bytes(b"a")

    def refreshed() -> Step:
        gain = loudness.read(found)
        return replace(encode, argvs=(("encode", f"gain={gain}"),))

    encode = Step("audio.1", "Encode", argvs=(("encode", "before"),), outputs=(encoded,), inputs=(found,),
                  background=True)  # fmt: skip
    encode = replace(encode, refresh=refreshed)
    steps = [
        Step("audio.1.measure", "Measure", argvs=(("measure",),), outputs=(found,), background=True),
        encode,
        Step("video", "Video", argvs=(("video",),), outputs=(video,)),
    ]
    run_steps(steps, {}, log=lambda _: None, runner=runner, parallel=2)
    assert ("encode", "gain={'max_volume': -6.0}") in calls


FFMPEG = shutil.which("ffmpeg")


def _measured_i(ffmpeg: str, path: Path) -> tuple[float, str]:
    out = subprocess.run(
        [ffmpeg, "-hide_banner", "-nostdin", "-i", str(path), "-af", "loudnorm=print_format=summary", "-f", "null",
         "-"], capture_output=True, text=True, check=True,
    ).stderr  # fmt: skip
    rate = re.search(r"Audio: \w+, (\d+) Hz", out)
    i = re.search(r"Input Integrated:\s*(-?[\d.]+)", out)
    assert i is not None and rate is not None
    return float(i.group(1)), rate.group(1)


@pytest.mark.skipif(FFMPEG is None, reason="needs ffmpeg")
@pytest.mark.parametrize(("lra", "target"), [("20", "-16"), ("7", "-24")])  # linear, then loudnorm's dynamic mode
def test_loudnorm_for_real(tmp_path, lra, target):
    assert FFMPEG is not None
    src = tmp_path / "src.wav"
    subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "anoisesrc=d=12:c=pink:a=0.05:r=44100",
                    "-af", "volume=enable='between(t,4,8)':volume=3", "-ac", "2", "-c:a", "pcm_s24le", str(src)],
                   check=True)  # fmt: skip
    p = planned(A.FLAC, normalize="loudnorm", loudnorm_i=target, loudnorm_lra=lra)
    p.source.index, p.source.duration_ms = 0, 12000
    tools = replace(TOOLS, ffmpeg=FFMPEG)
    found = measure_path(p, 1, tmp_path)
    measure = subprocess.run(measure_argv(p, src, found, tools), capture_output=True, text=True, check=False)
    assert measure.returncode == 0, measure.stdout
    assert "Progress: 100%" in measure.stdout and "time=" not in measure.stdout
    cmd = audio_command(p, 1, src, tmp_path, AudioSettings(), tools, loudness.read(found))
    assert cmd is not None
    subprocess.run(cmd.argvs[0], check=True)
    i, rate = _measured_i(FFMPEG, cmd.output)
    assert abs(i - float(target)) < 1.0 and rate == "44100"
