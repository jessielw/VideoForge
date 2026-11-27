"""The field scan (core/video/fieldscan.py): its verdicts on generated clips of each kind (a white box crossing grey,
made with ffmpeg lavfi; skipped without ffmpeg and tools/vs-plugins), its chains run on them, and the classifier,
chains and report on their own."""

from __future__ import annotations

from dataclasses import replace
import io
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from videoforge.core.config import PROJECT_ROOT
from videoforge.core.job import JobSpec
from videoforge.core.models import JobInputs, VideoInfo
from videoforge.core.pipeline import build
from videoforge.core.video import fieldscan as fs, filters, vs as vsx
from videoforge.core.video.fieldscan import FieldScan, Verdict
from videoforge.core.video.filters import PRESETS, field_issues
from videoforge.core.video.script import build_script
from videoforge.core.video.settings import FilterCategory, FilterStep, SourceFilter, VideoSettings

TOOLS = PROJECT_ROOT / "tools"
PLUGINS = TOOLS / "vs-plugins"
FFMPEG = shutil.which("ffmpeg")
vsx.configure(PLUGINS)

needs_vs = pytest.mark.skipif(
    FFMPEG is None or not (PLUGINS / "vivtc.dll").exists(), reason="needs ffmpeg and tools/vs-plugins"
)

FILM, VIDEO, NTSC = "24000/1001", "60000/1001", "30000/1001"
_BOX = r"overlay=x='mod(t*200\,260)':y=50"
# Video moves faster: at 200 px/s a field moves the box 3 px, and VFM's 16x16 blocks see too few combed pixels
_FAST = r"overlay=x='mod(t*600\,260)':y=50"
_TFF = ["-flags", "+ildct+ilme", "-top", "1", "-x264-params", "tff=1"]
_BFF = ["-flags", "+ildct+ilme", "-top", "0", "-x264-params", "bff=1"]


def _box(rate: str, seconds: float) -> list[str]:
    """ffmpeg inputs for the box crossing grey: [0] the grey, [1] the box."""
    return [
        "-f", "lavfi", "-i", f"color=c=gray:size=320x180:rate={rate}:duration={seconds}",
        "-f", "lavfi", "-i", f"color=c=white:size=40x80:rate={rate}:duration={seconds}",
    ]  # fmt: skip


def _make(out: Path, inputs: list[str], graph: str, flags: list[str]) -> Path:
    subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", *inputs, "-filter_complex", graph,
         "-c:v", "libx264", "-crf", "16", *flags, "-pix_fmt", "yuv420p", "-y", str(out)],
        check=True,
    )  # fmt: skip
    return out


@pytest.fixture(scope="module")
def clips(tmp_path_factory) -> dict[str, Path]:
    """One clip per kind. Telecine and video are 6 s, enough combed frames for the 3:2 cadence to count."""
    if FFMPEG is None:
        pytest.skip("needs ffmpeg")
    d = tmp_path_factory.mktemp("fieldscan")
    telecine = "telecine=first_field=top:pattern=23,setfield=tff"
    weave = "tinterlace=mode=interleave_top"  # two 59.94 frames per frame: each field its own moment
    return {
        "progressive": _make(d / "progressive.mkv", _box(FILM, 6), f"[0][1]{_BOX}", []),
        "psf": _make(d / "psf.mkv", _box(FILM, 6), f"[0][1]{_BOX},setfield=tff", _TFF),
        "telecine_tff": _make(d / "telecine_tff.mkv", _box(FILM, 6), f"[0][1]{_BOX},{telecine}", _TFF),
        "telecine_bff": _make(
            d / "telecine_bff.mkv", _box(FILM, 6), f"[0][1]{_BOX},telecine=first_field=bottom:pattern=23,setfield=bff",
            _BFF,
        ),
        "interlaced_tff": _make(d / "interlaced_tff.mkv", _box(VIDEO, 6), f"[0][1]{_FAST},{weave},setfield=tff", _TFF),
        # Top field first, flagged bottom first: the stream's order is wrong
        "flagged_bff": _make(d / "flagged_bff.mkv", _box(VIDEO, 6), f"[0][1]{_FAST},{weave},setfield=bff", _BFF),
        # 5 s of telecine, then 1 s of video
        "hybrid": _make(
            d / "hybrid.mkv", _box(FILM, 5) + _box(VIDEO, 1),
            f"[0][1]{_BOX},{telecine},setpts=PTS-STARTPTS[a];[2][3]{_FAST},{weave},setfield=tff,setpts=PTS-STARTPTS[b];"
            "[a][b]concat=n=2:v=1,setfield=tff",
            _TFF,
        ),
        # 29.97 progressive with the bottom field a frame late: every moving frame combs, none repeats
        "shifted": _make(d / "shifted.mkv", _box(NTSC, 6), f"[0][1]{_BOX},phase=t,setfield=tff", _TFF),
        "still": _make(d / "still.mkv", _box(NTSC, 2), "[0]null", []),
    }  # fmt: skip


def _source(path: Path, work: Path, **settings):
    return vsx.load_clip(build_script(VideoSettings(**settings), path, work, stage="source"))


@needs_vs
@pytest.mark.parametrize(
    ("kind", "verdict", "order", "stream"),
    [
        ("progressive", Verdict.PROGRESSIVE, "", "progressive"),
        ("psf", Verdict.PROGRESSIVE, "", "tff"),  # stored as interlaced, nothing combs: today's warning was wrong
        ("telecine_tff", Verdict.TELECINE, "tff", "tff"),
        ("telecine_bff", Verdict.TELECINE, "bff", "bff"),
        ("interlaced_tff", Verdict.INTERLACED, "tff", "tff"),
        ("flagged_bff", Verdict.INTERLACED, "tff", "bff"),
        ("hybrid", Verdict.HYBRID, "tff", "tff"),
        ("shifted", Verdict.SHIFTED, "bff", "tff"),  # phase=t: the bottom field is the earlier one
        ("still", Verdict.UNKNOWN, "", "progressive"),
    ],
)
def test_scan_verdicts(clips, tmp_path, kind, verdict, order, stream):
    got = fs.scan(_source(clips[kind], tmp_path), out=io.StringIO())
    assert (got.verdict, got.order, got.stream_order) == (verdict, order, stream), got
    assert got.mismatch == (kind in ("flagged_bff", "shifted"))
    assert len(got.strip) == -(-got.frames // fs._CHUNK)
    if verdict is Verdict.TELECINE:
        assert got.cadence is not None and got.cadence > 0.95
        assert got.fallback == 0 and set(got.strip) <= {"T", "."}
    if verdict is Verdict.INTERLACED:
        assert got.jitter is not None and got.jitter > 1.1  # bobbed BFF jitters more: top field first
    if verdict is Verdict.HYBRID:
        assert got.strip.startswith("TTTT") and got.strip.endswith("I")  # the video second
        first, last, _ = got.stretches[-1]
        assert first >= 5 * 30 * 0.95 and last == got.frames - 1
    if verdict is Verdict.SHIFTED:
        assert got.cadence is not None and got.cadence < 0.6  # every frame combs, not 2 of 5


@needs_vs
def test_scan_runs_as_a_subprocess_and_reads_back(clips, tmp_path):
    script = tmp_path / "source.vpy"
    script.write_text(build_script(VideoSettings(), clips["telecine_bff"], tmp_path, stage="source"), encoding="utf-8")
    out = tmp_path / "fieldscan.json"
    run = subprocess.run(
        [sys.executable, "-m", "videoforge.core.video.fieldscan", str(script), str(out)],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert run.returncode == 0, run.stderr
    assert "Progress: 100%" in run.stdout
    assert run.stdout.strip().splitlines()[-1].startswith("Telecined film, bottom field first")
    report = fs.read(out)
    assert report is not None and report.verdict is Verdict.TELECINE and report.frames == 180
    assert not list(tmp_path.glob("*.partial"))

    bad = tmp_path / "bad.vpy"
    bad.write_text("clip = 1\n", encoding="utf-8")
    run = subprocess.run(
        [sys.executable, "-m", "videoforge.core.video.fieldscan", str(bad), str(tmp_path / "bad.json")],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert run.returncode == 1 and "clip" in run.stderr and not (tmp_path / "bad.json").exists()


def _run_chain(clip, lines: str):
    import vapoursynth as vs

    ns = {"vs": vs, "core": vs.core, "clip": clip}
    exec(lines, ns)  # noqa: S102 - the scan's own chains
    return ns["clip"]


def _combed(clip) -> int:
    import vapoursynth as vs

    matched = vs.core.vivtc.VFM(vs.core.std.SetFieldBased(clip, 2), order=1, micout=1)
    return sum(int(f.props["VFMMics"][1]) > fs._MI for f in matched.frames())  # pyright: ignore[reportIndexIssue, reportArgumentType]


@needs_vs
@pytest.mark.parametrize("kind", ["telecine_tff", "telecine_bff", "shifted", "interlaced_tff", "flagged_bff"])
def test_the_chains_clean_their_clips(clips, tmp_path, kind):
    """Each verdict's chain leaves nothing combed: IVTC gives 4 of every 5 frames, the shifted chain all of them,
    Bwdif all of them (at the scan's order, over a wrong flag)."""
    src = _source(clips[kind], tmp_path)
    got = fs.scan(src, out=io.StringIO())
    out = _run_chain(src, got.chain)
    frames = src.num_frames * 4 // 5 if got.verdict is Verdict.TELECINE else src.num_frames
    assert out.num_frames == frames
    assert _combed(out) == 0


@needs_vs
def test_hybrid_chain_deinterlaces_only_the_frames_left_combed(clips, tmp_path):
    """The fallback replaces the frames VFM leaves combed and no others (VFM's clip2 would give its fields to every
    frame). Skipped without havsfunc."""
    import vapoursynth as vs

    pytest.importorskip("havsfunc")
    src = _source(clips["hybrid"], tmp_path)
    got = fs.scan(src, out=io.StringIO())
    assert got.verdict is Verdict.HYBRID
    lines = got.chain.splitlines()
    assert lines[-1] == "clip = core.vivtc.VDecimate(clip)"
    ns = {"vs": vs, "core": vs.core, "clip": src}
    exec("\n".join(lines[:-1]), ns)  # noqa: S102 - up to the decimation
    fixed, fallback = ns["clip"], ns["fallback"]
    matched = vs.core.vivtc.VFM(vs.core.std.SetFieldBased(src, 2), order=1)
    to_fallback = vs.core.std.PlaneStats(fixed, fallback)
    to_matched = vs.core.std.PlaneStats(fixed, matched)
    replaced = 0
    for m, a, b in zip(matched.frames(), to_fallback.frames(), to_matched.frames(), strict=True):
        if m.props["_Combed"]:
            assert a.props["PlaneStatsDiff"] == 0
            replaced += 1
        else:
            assert b.props["PlaneStatsDiff"] == 0
    assert replaced == got.fallback > 0
    assert _combed(_run_chain(src, got.chain)) == 0


@needs_vs
def test_soft_pulldown_scans_as_telecine_with_the_flags_applied(tmp_path):
    """x264's pulldown flags, no field stored twice: the stored frames are progressive, BestSource with the flags
    applied gives telecine (the scan of a soft-telecined source needs Apply pulldown)."""
    x264 = TOOLS / "x264" / "x264.exe"
    if not x264.exists():
        pytest.skip(f"needs {x264}")
    frames = subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", *_box(FILM, 6),
         "-filter_complex", f"[0][1]{_BOX},format=yuv420p", "-f", "yuv4mpegpipe", "-"],
        check=True, capture_output=True,
    ).stdout  # fmt: skip
    soft = tmp_path / "soft.mkv"
    subprocess.run(
        [str(x264), "--quiet", "--demuxer", "y4m", "--pulldown", "32", "--fake-interlaced", "--crf", "16",
         "-o", str(soft), "-"],
        input=frames, check=True, capture_output=True,
    )  # fmt: skip
    progress = io.StringIO()
    stored = fs.scan(_source(soft, tmp_path, source_filter=SourceFilter.BESTSOURCE), out=progress)
    applied = fs.scan(_source(soft, tmp_path, source_filter=SourceFilter.BESTSOURCE, pulldown=True), out=progress)
    assert (stored.verdict, stored.frames) == (Verdict.PROGRESSIVE, 144)
    assert (applied.verdict, applied.order, applied.frames) == (Verdict.TELECINE, "tff", 180)
    assert applied.stream_order == ""  # BestSource with rff=1 tags no field order


# --- without VapourSynth ---------------------------------------------------------------


def _frames(pattern: str, repeat: int, order_left: str = "tff") -> fs._Frames:
    """Frames from a pattern per frame: "." still, "p" moving and clean, "c" combed as decoded and fixed by
    matching, "x" combed and left combed (at order_left; at the other order every combed frame stays combed)."""
    got = fs._Frames()
    other = "bff" if order_left == "tff" else "tff"
    for ch in pattern * repeat:
        got.moving.append(ch != ".")
        got.combed.append(ch in "cx")
        got.left[order_left].append(ch == "x")
        got.left[other].append(ch in "cx")
    return got


@pytest.mark.parametrize(
    ("pattern", "verdict", "order"),
    [
        ("ppppp", Verdict.PROGRESSIVE, ""),
        ("ppccp", Verdict.TELECINE, "tff"),  # 2 of 5 combed, matched: 3:2
        ("ccccc", Verdict.SHIFTED, "tff"),  # every frame combed and matched: no cadence
        ("ppcxp" * 4 + "ppccp" * 6, Verdict.HYBRID, "tff"),  # 10% left
        ("xxxxx", Verdict.INTERLACED, "tff"),
        (".....", Verdict.UNKNOWN, ""),
    ],
)
def test_classify(pattern, verdict, order):
    got, order_found, *_ = fs.classify(_frames(pattern, 60))
    assert (got, order_found) == (verdict, order)


def test_classify_takes_the_order_that_leaves_less_combing():
    assert fs.classify(_frames("ppccp", 60, order_left="bff"))[:2] == (Verdict.TELECINE, "bff")


def test_cadence_is_counted_per_section():
    """An edit shifts the 3:2 phase: per section, each phase still lands on 2 of 5 positions."""
    got = _frames("ppccp", fs._CADENCE_SECTION // 5)
    shifted = _frames("pccpp", fs._CADENCE_SECTION // 5)
    for name in ("moving", "combed"):
        getattr(got, name).extend(getattr(shifted, name))
    assert fs._cadence(got) == 1.0
    assert fs._cadence(_frames("ppccp", 5)) is None  # 10 combed frames: too few to say


def test_stretches_join_close_frames():
    left = [False] * 200
    for i in (10, 12, 30, 100, 101, 102):
        left[i] = True
    assert fs._stretches(left) == [(10, 30, 3), (100, 102, 3)]


def test_chains():
    assert fs.chain(Verdict.PROGRESSIVE, "") == fs.chain(Verdict.UNKNOWN, "") == ""
    telecine = fs.chain(Verdict.TELECINE, "bff").splitlines()
    assert telecine[0].startswith("clip = core.std.SetFieldBased(clip, 1)")
    assert telecine[1:] == ["clip = core.vivtc.VFM(clip, order=0)", "clip = core.vivtc.VDecimate(clip)"]
    assert fs.chain(Verdict.SHIFTED, "tff").splitlines()[1:] == ["clip = core.vivtc.VFM(clip, order=1)"]
    assert fs.chain(Verdict.INTERLACED, "tff").splitlines()[1:] == ["clip = core.bwdif.Bwdif(clip, field=1)"]
    hybrid = fs.chain(Verdict.HYBRID, "tff")
    assert "TFF=True" in hybrid and "clip2" not in hybrid.split("#")[0] and "FrameEval" in hybrid
    for v in Verdict:
        compile(fs.chain(v, "tff"), "<chain>", "exec")


def test_report_round_trip_and_summary(tmp_path):
    report = FieldScan(
        verdict=Verdict.HYBRID, order="tff", stream_order="bff", frames=41928, fps_num=30000, fps_den=1001,
        moving=13280, combed=5064, left_tff=1267, left_bff=4963, fallback=2146, cadence=0.69,
        jitter=1.45, strip="TTI.", stretches=[(144, 154, 5)], seconds=84.8,
    )  # fmt: skip
    path = tmp_path / "fieldscan.json"
    path.write_text(fs.to_json(report), encoding="utf-8")
    assert fs.read(path) == report
    assert report.mismatch
    assert fs.summary(report) == (
        "Telecined film with combed parts, top field first (2146 frames left combed); the stream says BFF"
    )
    path.write_text('{"version": 0}', encoding="utf-8")
    assert fs.read(path) is None
    assert fs.read(tmp_path / "missing.json") is None


# --- the scan in a job: issues, Apply, the index lane's steps -------------------------------------------------


def _report(verdict: Verdict, order: str = "tff", stream: str = "tff", fallback: int = 0) -> FieldScan:
    return FieldScan(
        verdict=verdict, order=order if verdict not in (Verdict.PROGRESSIVE, Verdict.UNKNOWN) else "",
        stream_order=stream, frames=1000, fps_num=30000, fps_den=1001, moving=500, combed=200, left_tff=0,
        left_bff=200, fallback=fallback, cadence=1.0, jitter=None, strip="T",
    )  # fmt: skip


def _preset(family: str) -> FilterStep:
    return next(p for p in PRESETS if p.family == family).step()


def _codes(video: VideoInfo, scan: FieldScan, *steps: FilterStep, **settings) -> list[str]:
    return [i.code for i in field_issues(video, VideoSettings(filters=list(steps), **settings), scan)]


BLURAY = VideoInfo(1920, 1080, scan_type="MBAFF", scan_order="TFF")
DVD = VideoInfo(720, 480, scan_type="Progressive", scan_order="2:3 Pulldown")


def test_the_scan_replaces_mediainfos_warning():
    """Progressive video stored as fields (PsF) no longer warns; the verdict's chain is what to add; a Field step of
    the wrong kind says why; the scan's own chain leaves nothing to say. Without a verdict, MediaInfo's warning."""
    ivtc, bwdif = _preset("IVTC (VIVTC)"), _preset("Bwdif")
    progressive, telecine = _report(Verdict.PROGRESSIVE), _report(Verdict.TELECINE)
    assert _codes(BLURAY, progressive) == []
    unneeded = field_issues(BLURAY, VideoSettings(filters=[ivtc]), progressive)
    assert [i.code for i in unneeded] == ["video.field_unneeded"]
    assert "stored as fields" in unneeded[0].message and "VDecimate drops real frames" in unneeded[0].message
    assert "softens" in field_issues(BLURAY, VideoSettings(filters=[bwdif]), progressive)[0].message

    missing = field_issues(BLURAY, VideoSettings(), telecine)
    assert [i.code for i in missing] == ["video.field"]
    assert "telecined film, top field first" in missing[0].message and "IVTC (VFM + VDecimate)" in missing[0].message
    assert _codes(BLURAY, telecine, ivtc) == []
    assert _codes(BLURAY, telecine, bwdif) == ["video.field_kind"]  # deinterlacing film

    shifted = FilterStep(FilterCategory.FIELD, "VFM", fs.chain(Verdict.SHIFTED, "tff"))
    kind = field_issues(BLURAY, VideoSettings(filters=[shifted]), telecine)[0]
    assert kind.code == "video.field_kind" and "no VDecimate" in kind.message
    video = field_issues(BLURAY, VideoSettings(filters=[ivtc]), _report(Verdict.INTERLACED))[0]
    assert video.code == "video.field_kind" and "VDecimate drops real frames" in video.message
    assert (
        "repeats no frames" in field_issues(BLURAY, VideoSettings(filters=[ivtc]), _report(Verdict.SHIFTED))[0].message
    )
    hybrid = _report(Verdict.HYBRID, fallback=2146)
    leftover = field_issues(BLURAY, VideoSettings(filters=[ivtc]), hybrid)[0]
    assert leftover.code == "video.field_kind" and "2146 frames combed" in leftover.message
    assert _codes(BLURAY, _report(Verdict.UNKNOWN)) == ["video.interlaced"]  # MediaInfo's, as before

    for verdict in Verdict:
        scan = _report(verdict, fallback=10)
        fix = filters.field_fix(scan, BLURAY, VideoSettings(filters=[bwdif]))
        if verdict is Verdict.UNKNOWN:
            assert fix is None
            continue
        assert fix is not None
        assert field_issues(BLURAY, fix.apply(VideoSettings(filters=[bwdif])), scan) == [], verdict


def test_the_scan_checks_the_field_order_the_step_gets():
    """The Field step follows the stream's flag (or, with no flag, its own argument) unless an override line sets
    one: a flag or an argument that isn't the content's order warns, as does an override set to the other one."""
    ivtc, qtgmc = _preset("IVTC (VIVTC)"), next(p for p in PRESETS if p.name == "QTGMC Fast").step()
    flagged_wrong = _report(Verdict.TELECINE, order="tff", stream="bff")
    issue = field_issues(BLURAY, VideoSettings(filters=[ivtc]), flagged_wrong)[0]
    assert issue.code == "video.field_order" and "flagged bottom field first" in issue.message
    assert "clip = core.std.SetFieldBased(clip, 2)" in issue.message

    def override(step: FilterStep, value: int) -> FilterStep:
        line = "# clip = core.std.SetFieldBased(clip, 2)"
        return replace(step, script=step.script.replace(line, f"clip = core.std.SetFieldBased(clip, {value})"))

    assert _codes(BLURAY, flagged_wrong, override(ivtc, 2)) == []
    assert (
        "sets bottom field first"
        in field_issues(BLURAY, VideoSettings(filters=[override(ivtc, 1)]), flagged_wrong)[0].message
    )
    untagged = _report(Verdict.TELECINE, order="bff", stream="")  # BestSource applying pulldown tags no order
    assert "gives no field order" in field_issues(DVD, VideoSettings(filters=[ivtc]), untagged)[0].message
    bottom = replace(ivtc, script=ivtc.script.replace("order=1", "order=0"))
    assert _codes(DVD, untagged, bottom, source_filter=SourceFilter.BESTSOURCE, pulldown=True) == []
    # QTGMC's preset tags only untagged frames (an indented line): a bottom-first flag is followed
    assert _codes(BLURAY, _report(Verdict.INTERLACED, order="bff", stream="bff"), qtgmc) == []


def test_apply_on_a_soft_telecined_source_turns_on_pulldown():
    """The scan's frames have the pulldown flags applied: Apply turns Apply pulldown on, and an FFMS2 job moves to
    BestSource (whose index the scan made). The Field steps make way for the scan's, first in the chain."""
    hybrid = _report(Verdict.HYBRID, stream="", fallback=2146)
    issue = field_issues(DVD, VideoSettings(), hybrid)[0]
    assert issue.code == "video.field" and "turns on Apply pulldown" in issue.message and "2146 frames" in issue.message
    settings = VideoSettings(filters=[_preset("Bwdif"), *VideoSettings().filters, INVERT_STEP])
    fix = filters.field_fix(hybrid, DVD, settings)
    assert fix is not None and fix.step is not None
    assert (fix.pulldown, fix.source_filter, fix.step.name) == (
        True,
        SourceFilter.BESTSOURCE,
        "Field scan: IVTC + QTGMC",
    )
    assert not fix.applied(settings)
    applied = fix.apply(settings)
    assert [s.name for s in applied.filters] == ["Field scan: IVTC + QTGMC", "Crop", "Resize", "Invert"]
    assert fix.applied(applied) and field_issues(DVD, applied, hybrid) == []
    lsmash = filters.field_fix(hybrid, DVD, VideoSettings(source_filter=SourceFilter.LSMASH))
    assert lsmash is not None and lsmash.source_filter is SourceFilter.LSMASH  # it can apply them already
    gone = filters.field_fix(_report(Verdict.PROGRESSIVE), BLURAY, settings)
    assert gone is not None and gone.step is None and not gone.pulldown
    assert [s.name for s in gone.apply(settings).filters] == ["Crop", "Resize", "Invert"]


INVERT_STEP = FilterStep(FilterCategory.CUSTOM, "Invert", "clip = clip.std.Invert()")


def _job(source: Path, video: VideoSettings | None = None) -> JobSpec:
    return JobSpec(inputs=JobInputs(source), rule_set="manual", video=video or VideoSettings())


def test_field_scan_steps(tmp_path):
    """A source stored as fields or with pulldown flags gets the scan after its index; its script decodes as the job
    does, flags applied (BestSource for an FFMS2 job, whose index the scan then makes)."""
    source = tmp_path / "E01.mkv"
    assert build.field_scan_steps(_job(source), VideoInfo(1920, 1080, scan_type="Progressive")) == []
    assert build.field_scan_steps(_job(source), None) == []
    reused = JobSpec(inputs=JobInputs(source, encode=tmp_path / "enc.mkv"), rule_set="manual")
    assert build.field_scan_steps(reused, BLURAY) == []

    spec = _job(source)
    script, scan = build.field_scan_steps(spec, BLURAY)
    assert script.outputs == (spec.work_dir / fs.SCRIPT,) and "ffms2.Source" in script.key
    assert scan.argvs[0][1:] == (
        "-m",
        "videoforge.core.video.fieldscan",
        str(script.outputs[0]),
        str(spec.work_dir / fs.REPORT),
    )
    assert scan.reads == (build.index_key(source, SourceFilter.FFMS2),) and scan.owns == ()
    assert scan.inputs == (source,) and "ffms2" not in scan.key  # a new source filter doesn't scan again

    script, scan = build.field_scan_steps(spec, DVD)
    assert "bs.VideoSource" in script.key and "rff=1" in script.key
    assert scan.owns == (build.index_key(source, SourceFilter.BESTSOURCE),) and scan.reads == ()
    lsmash = build.field_scan_steps(_job(source, VideoSettings(source_filter=SourceFilter.LSMASH)), DVD)
    assert "repeat=1" in lsmash[0].key and lsmash[1].reads == (build.index_key(source, SourceFilter.LSMASH),)


@needs_vs
def test_the_lanes_scan_steps_write_the_report_the_plan_reads(clips, tmp_path):
    """The scan's steps run (as the index lane runs them) and job.field_scan reads what they wrote."""
    from videoforge.core.job import field_scan
    from videoforge.core.pipeline.steps import run_steps

    source = tmp_path / "Telecined.mkv"
    shutil.copy(clips["telecine_bff"], source)
    spec = _job(source)
    assert field_scan(spec) is None
    spec.work_dir.mkdir()  # the lane's log makes it
    records: dict = {}
    run_steps(build.field_scan_steps(spec, BLURAY), records, log=lambda _line: None)
    report = field_scan(spec)
    assert report is not None and (report.verdict, report.order) == (Verdict.TELECINE, "bff")
    assert [i.code for i in field_issues(BLURAY, spec.video, report)] == ["video.field"]
    lines: list[str] = []
    run_steps(build.field_scan_steps(spec, BLURAY), records, log=lines.append)
    assert any("reused" in line for line in lines)  # done once per source
