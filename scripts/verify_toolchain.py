"""Verify provisioned Windows tools without falling back to programs on PATH.

    uv run python scripts/verify_toolchain.py [--tools DIR] [--plugins DIR] [--smoke]

--smoke checks plugin/script imports, indexing and a preview frame, vspipe output,
H.264/HEVC/AV1 encodes, audio encoding, and MKV/MP4 muxing using tiny generated fixtures.
DEE and Apple's runtime are intentionally user supplied and are not required.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import sysconfig
import tempfile
import tomllib

from artifacts import ROOT
from fetch_tools import installed, load_manifest, require_windows


def clean_env(plugins: Path) -> dict[str, str]:
    env = dict(os.environ)
    for name in ("PYTHONPATH", "PYTHONHOME", "VAPOURSYNTH_EXTRA_PLUGIN_PATH"):
        env.pop(name, None)
    env["PATH"] = str(Path(env.get("SystemRoot", r"C:\Windows")) / "System32")
    env["VAPOURSYNTH_EXTRA_PLUGIN_PATH"] = str(plugins)
    return env


def run(argv: list, env: dict[str, str], *, codes: tuple[int, ...] = (0,)) -> str:
    result = subprocess.run(
        [str(a) for a in argv],
        capture_output=True,
        stdin=subprocess.DEVNULL,
        env=env,
        timeout=120,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    if result.returncode not in codes:
        raise ValueError(f"{Path(argv[0]).name} exited {result.returncode}:\n{output[-6000:]}")
    return output


def verify(manifest: dict, tools: Path, env: dict[str, str]) -> dict[str, Path]:
    paths = {}
    for tool in manifest["tool"]:
        if not installed(tool, tools):
            raise ValueError(f"{tool['name']}: missing or modified files; rerun scripts/fetch_tools.py")
        win = tool["windows"]
        for name, path in win["executables"].items():
            exe = tools / win["directory"] / path
            args = win.get("args", ["--version"])
            output = run([exe, *args], env, codes=(0, 1) if name == "qaac" else (0,))
            if not re.search(r"\d+\.\d+", output):
                raise ValueError(f"{name}: no version banner in {output[:500]!r}")
            paths[name] = exe
        print(f"OK {tool['name']}: {tool['version']}", flush=True)
    return paths


def smoke(paths: dict[str, Path], plugins: Path, env: dict[str, str]) -> None:
    with tempfile.TemporaryDirectory(prefix="VideoForge smoke ") as tmp:
        work = Path(tmp)
        # Prevent user settings/plugin directories from concealing a missing bundled dependency.
        env = {
            **env,
            "APPDATA": str(work / "appdata"),
            "LOCALAPPDATA": str(work / "localappdata"),
            "XDG_CONFIG_HOME": str(work / "config"),
            "VIDEOFORGE_ROOT": str(ROOT),
        }
        ffmpeg = paths["ffmpeg"]
        source = work / "source.mkv"
        run(
            [
                ffmpeg,
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=size=64x64:rate=24",
                "-frames:v",
                "4",
                "-c:v",
                "ffv1",
                source,
            ],
            env,
        )
        plugin_manifest = ROOT / "vsplugins" / "manifest.toml"
        manifest = tomllib.loads(plugin_manifest.read_text(encoding="utf-8"))
        for plugin in manifest["plugin"]:
            downloads = plugin["win64"]
            for artifact in downloads if isinstance(downloads, list) else [downloads]:
                names = artifact.get("files") or {artifact["url"].rsplit("/", 1)[-1]: ""}
                for name in names:
                    if not (plugins / name).is_file():
                        raise ValueError(f"missing plugin file: {plugins / name}")
        # A separate process initializes VapourSynth with exactly this plugin folder.
        code = (
            "import importlib, vapoursynth as vs\n"
            f"names = {[p['namespace'] for p in manifest['plugin']]!r}\n"
            "missing = [n for n in names if not hasattr(vs.core, n)]\n"
            "if missing: raise RuntimeError(f'plugins failed to load: {missing}')\n"
            "for name in ('havsfunc', 'mvsfunc', 'awsmfunc', 'vsutil', 'rekt', 'adjust', 'dfttest2'):\n"
            "    importlib.import_module(name)\n"
            "from pymediainfo import MediaInfo\n"
            f"info = MediaInfo.parse({str(source)!r})\n"
            "if not any(t.track_type == 'Video' for t in info.tracks): raise RuntimeError('MediaInfo failed')\n"
            f"clip = vs.core.ffms2.Source({str(source)!r}, cachefile={str(work / 'source.ffindex')!r})\n"
            "frame = clip.get_frame(0)\n"
            "if frame.width != 64 or frame.height != 64: raise RuntimeError('preview frame failed')\n"
        )
        run([sys.executable, "-c", code], env)
        print("OK plugins, Python filters, MediaInfo, source index and preview frame", flush=True)

        script = work / "source.vpy"
        script.write_text(
            "import vapoursynth as vs\n"
            f"vs.core.ffms2.Source({str(source)!r}, cachefile={str(work / 'source.ffindex')!r}).set_output()\n",
            encoding="utf-8",
        )
        vspipe = Path(sysconfig.get_path("scripts")) / "vspipe.exe"
        if not vspipe.is_file():
            vspipe = Path(sys.executable).with_name("vspipe.exe")
        if not vspipe.is_file():
            raise ValueError("vspipe is missing from this Python runtime")
        run([sys.executable, "-m", "vapoursynth", "config"], env)
        y4m = work / "source.y4m"
        run([vspipe, "-c", "y4m", script, y4m], env)
        h264, hevc, av1 = work / "video.h264", work / "video.hevc", work / "video.ivf"
        run([paths["x264"], "--preset", "ultrafast", "--demuxer", "y4m", "--output", h264, y4m], env)
        run(
            [
                paths["x265"],
                "--preset",
                "ultrafast",
                "--frame-threads",
                "1",
                "--pools",
                "1",
                "--output",
                hevc,
                "--y4m",
                "--input",
                y4m,
            ],
            env,
        )
        # HDR10+ and Dolby Vision: encoded in, then read back out. Not from --fullhelp: Patman's build takes
        # --dhdr10-info but leaves it out of its help.
        hdr10plus, rpu, dv_hevc = work / "hdr10plus.json", work / "rpu.bin", work / "dv.hevc"
        scene = {
            "BezierCurveData": {
                "Anchors": [102, 205, 307, 410, 512, 614, 717, 819, 922],
                "KneePointX": 0,
                "KneePointY": 0,
            },
            "LuminanceParameters": {
                "AverageRGB": 1200,
                "LuminanceDistributions": {
                    "DistributionIndex": [1, 5, 10, 25, 50, 75, 90, 95, 99],
                    "DistributionValues": [10, 50, 120, 400, 900, 2000, 6000, 9000, 20000],
                },
                "MaxScl": [30000, 28000, 26000],
            },
            "NumberOfWindows": 1,
            "TargetedSystemDisplayMaximumLuminance": 400,
            "SceneId": 0,
        }
        frames = [{**scene, "SceneFrameIndex": i, "SequenceFrameIndex": i} for i in range(4)]
        hdr10plus.write_text(
            json.dumps(
                {
                    "JSONInfo": {"HDR10plusProfile": "B", "Version": "1.0"},
                    "SceneInfo": frames,
                    "SceneInfoSummary": {"SceneFirstFrameIndex": [0], "SceneFrameNumbers": [4]},
                }
            ),
            encoding="utf-8",
        )
        generate = work / "rpu.json"
        generate.write_text(json.dumps({"cm_version": "V40", "length": 4}), encoding="utf-8")
        run([paths["dovi_tool"], "generate", "-j", generate, "-o", rpu], env)
        run(
            [
                paths["x265"],
                "--preset",
                "ultrafast",
                "--frame-threads",
                "1",
                "--pools",
                "1",
                "--output-depth",
                "10",
                "--vbv-bufsize",
                "20000",
                "--vbv-maxrate",
                "20000",
                "--master-display",
                "G(13250,34500)B(7500,3000)R(34000,16000)WP(15635,16450)L(10000000,1)",
                "--max-cll",
                "1000,400",
                "--dhdr10-info",
                hdr10plus,
                "--dolby-vision-profile",
                "8.1",
                "--dolby-vision-rpu",
                rpu,
                "--output",
                dv_hevc,
                "--y4m",
                "--input",
                y4m,
            ],
            env,
        )
        hdr10plus_out, rpu_out = work / "hdr10plus_out.json", work / "rpu_out.bin"
        run([paths["hdr10plus_tool"], "extract", dv_hevc, "-o", hdr10plus_out], env)
        if len(json.loads(hdr10plus_out.read_text(encoding="utf-8"))["SceneInfo"]) != 4:
            raise ValueError("x265 did not write HDR10+ metadata (--dhdr10-info)")
        run([paths["dovi_tool"], "extract-rpu", dv_hevc, "-o", rpu_out], env)
        if "Frames: 4" not in run([paths["dovi_tool"], "info", "-i", rpu_out, "-s"], env):
            raise ValueError("x265 did not write Dolby Vision RPUs (--dolby-vision-rpu)")
        run([paths["svtav1"], "--preset", "13", "--lp", "1", "-i", y4m, "-b", av1], env)
        for path in (h264, hevc, av1):
            run([ffmpeg, "-v", "error", "-i", path, "-f", "null", "-"], env)
        print("OK vspipe and H.264 / HEVC / AV1 encoding and decoding", flush=True)

        wav = work / "audio.wav"
        run(
            [
                ffmpeg,
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:duration=0.2",
                "-ar",
                "48000",
                "-ac",
                "2",
                wav,
            ],
            env,
        )
        for codec, ext in (("flac", "flac"), ("libopus", "opus"), ("aac", "m4a"), ("ac3", "ac3"), ("eac3", "eac3")):
            run([ffmpeg, "-v", "error", "-i", wav, "-c:a", codec, work / f"audio.{ext}"], env)
        run([paths["opusenc"], wav, work / "standalone.opus"], env)
        print("OK FFmpeg FLAC / Opus / AAC / AC-3 / E-AC-3 and standalone opusenc", flush=True)

        mkv = work / "output.mkv"
        run([paths["mkvmerge"], "-o", mkv, h264, work / "audio.flac"], env)
        run([paths["mkvpropedit"], mkv, "--edit", "info", "--set", "title=VideoForge smoke"], env)
        run([paths["mkvextract"], mkv, "tracks", f"0:{work / 'extracted.h264'}"], env)
        mp4 = work / "output.mp4"
        run([paths["mp4box"], "-add", f"{h264}:fps=24", "-add", work / "audio.m4a", "-new", mp4], env)
        for output in (mkv, mp4):
            probe = json.loads(run([paths["ffprobe"], "-v", "error", "-show_streams", "-of", "json", output], env))
            if {s["codec_type"] for s in probe["streams"]} != {"video", "audio"}:
                raise ValueError(f"{output.name}: muxed streams are incomplete")
            run([ffmpeg, "-v", "error", "-i", output, "-f", "null", "-"], env)
        print("OK MKV / MP4 muxing, metadata edits, extraction and output validation", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tools", type=Path, default=ROOT / "tools")
    ap.add_argument("--plugins", type=Path, help="defaults to <tools>/vs-plugins")
    ap.add_argument("--smoke", action="store_true", help="exercise the provisioned media pipeline")
    args = ap.parse_args()
    try:
        require_windows()
        plugins = (args.plugins or args.tools / "vs-plugins").resolve()
        env = clean_env(plugins)
        paths = verify(load_manifest(), args.tools.resolve(), env)
        if args.smoke:
            smoke(paths, plugins, env)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        ap.exit(1, f"Toolchain verification failed: {error}\n")
    print("Toolchain verified. DEE and Apple CoreAudioToolbox remain user supplied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
