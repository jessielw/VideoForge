"""The preview worker (core/video/preview.py): VapourSynth in a child process. A crashing or hanging
script costs only the worker; the next request starts a new one."""

import time

import pytest

pytest.importorskip("vapoursynth")

from videoforge.core.video.preview import FrameError, Preview, PreviewError
from videoforge.core.video.vs import ScriptError

BLANK = "import vapoursynth as vs\nclip = vs.core.std.BlankClip(width=64, height=48, length={n}, color=[0, 0, 0])\n"


@pytest.fixture
def preview():
    p = Preview(frame_timeout=20, load_timeout=20)
    yield p
    p.close()


def test_preview_runs_scripts_in_a_worker(preview):
    info = preview.info(BLANK.format(n=10))
    assert (info.width, info.height, info.frames) == (64, 48, 10)
    image, _pict, frames = preview.frame(BLANK.format(n=10), 3, "png")
    assert image[:4] == b"\x89PNG" and frames == 10
    assert preview.check(BLANK.format(n=10)).format == "RGB24"
    boxed = ("import vapoursynth as vs\nclip = vs.core.std.BlankClip(format=vs.YUV420P8, width=60, height=40, length=5,"
             " color=[128, 128, 128]).std.AddBorders(left=2, right=2, top=4, bottom=4)\n")
    crop = preview.autocrop(boxed, 3)
    assert (crop.left, crop.top, crop.right, crop.bottom) == (2, 4, 2, 4)


def test_preview_reports_script_and_frame_errors(preview):
    with pytest.raises(ScriptError) as e:
        preview.info("x = 1\nclip = 1\n")
    assert "video clip" in e.value.message
    with pytest.raises(ScriptError) as e:
        preview.info("x = 1\ny = (\n")
    assert e.value.line == 2
    bad = BLANK.format(n=5) + "clip = clip.std.Expr('x undefined_word')\n"
    with pytest.raises((ScriptError, FrameError)):
        preview.check(bad)


def test_what_a_script_prints_does_not_break_the_replies(preview):
    noisy = "import sys, os\nprint('hello ' * 1000)\nos.write(1, b'raw bytes on fd 1')\n" + BLANK.format(n=4)
    assert preview.info(noisy).frames == 4
    assert preview.frame(noisy, 1)[2] == 4


def test_a_crashing_script_costs_only_the_worker(preview):
    assert preview.info(BLANK.format(n=7)).frames == 7
    first = preview._worker
    with pytest.raises(PreviewError, match="stopped"):
        preview.info("import os\nos._exit(3)\n")
    assert preview.info(BLANK.format(n=8)).frames == 8  # a new worker
    assert preview._worker is not first and first.proc.poll() == 3


def test_a_hanging_script_is_stopped_and_the_worker_restarted():
    p = Preview(frame_timeout=1, load_timeout=1)
    try:
        start = time.monotonic()
        with pytest.raises(PreviewError, match="restarted"):
            p.info("while True:\n    pass\n")
        assert time.monotonic() - start < 10
        assert p.info(BLANK.format(n=3)).frames == 3
    finally:
        p.close()


def test_requests_run_side_by_side(preview):
    """A slow script (a source being indexed) doesn't hold up another clip's frames."""
    import threading

    slow = "import time\ntime.sleep(3)\n" + BLANK.format(n=2)
    t = threading.Thread(target=preview.info, args=(slow,))
    preview.info(BLANK.format(n=9))  # the worker is up
    t.start()
    time.sleep(0.3)
    start = time.monotonic()
    assert preview.frame(BLANK.format(n=9), 2)[2] == 9
    assert time.monotonic() - start < 2
    t.join()


def test_close_ends_the_worker():
    p = Preview()
    p.info(BLANK.format(n=2))
    proc = p._worker.proc
    p.close()
    proc.wait(timeout=10)
    assert proc.poll() is not None
