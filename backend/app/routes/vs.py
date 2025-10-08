import io
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import vapoursynth as vs
from fastapi import APIRouter, Query, Request, Response
from PIL import Image

from app.schemas.vs import (
    ScriptValidationRequest,
    ScriptValidationResponse,
    VsProbeModel,
    VsResponse,
)
from app.utils.file_utils import get_allowed_roots, is_under_allowed_roots
from app.utils.vs import vs_core

router = APIRouter()


@router.post("/vs/info", response_model=VsResponse)
async def vapoursynth_info(request: Request):
    """
    Probe a file using VapourSynth directly to get frame count, width, height, and fps.

    Returns VapourSynth data.
    """
    data = await request.json()
    file_path = data.get("path")
    if not file_path:
        return {"ok": False, "error": "No path provided"}

    p = Path(file_path)
    roots = get_allowed_roots()
    if roots and not is_under_allowed_roots(p, roots):
        return {"ok": False, "error": "Path not under allowed roots"}

    if not p.exists():
        return {"ok": False, "error": "File not found"}

    vs_info: dict[str, Any] = {}
    try:
        # Use LWLibavSource if available, otherwise try ffms2
        clip = None
        try:
            clip = vs_core.lsmas.LWLibavSource(str(p))
        except Exception:
            try:
                clip = vs_core.ffms2.Source(str(p))
            except Exception as e:
                raise RuntimeError(f"No suitable source filter available: {e}")

        # Collect frame info
        vs_info["frames"] = int(clip.num_frames)
        vs_info["width"] = int(clip.width)
        vs_info["height"] = int(clip.height)
        try:
            vs_info["fps_num"] = int(clip.fps.numerator)
            vs_info["fps_den"] = int(clip.fps.denominator)
            vs_info["fps"] = vs_info["fps_num"] / vs_info["fps_den"]
        except Exception:
            # Some sources may not expose fps as a rational
            try:
                vs_info["fps"] = float(clip.fps)
            except Exception:
                pass

    except Exception as e:
        print(f"VapourSynth probe failed: {e}", flush=True)
        vs_info = {"error": str(e)}

    probe_model = None
    if vs_info:
        probe_model = VsProbeModel(
            frames=vs_info.get("frames"),
            width=vs_info.get("width"),
            height=vs_info.get("height"),
            fps=vs_info.get("fps"),
            fps_num=vs_info.get("fps_num"),
            fps_den=vs_info.get("fps_den"),
            error=vs_info.get("error"),
        )

    return VsResponse(ok=True, path=str(p), vapoursynth=probe_model)


@router.post("/vs/script/validate", response_model=ScriptValidationResponse)
async def validate_script(request: ScriptValidationRequest):
    """Validate a VapourSynth script without executing it."""
    try:
        # Create a temporary script with basic validation
        script = request.script.strip()
        if not script:
            return ScriptValidationResponse(valid=False, error="Script is empty")

        # Try to compile the script to check for syntax errors
        try:
            compile(script, "<string>", "exec")
        except SyntaxError as e:
            return ScriptValidationResponse(valid=False, error=f"Syntax error: {e}")

        # Basic VapourSynth validation - check for required components
        if "import vapoursynth" not in script and "import vs" not in script:
            return ScriptValidationResponse(
                valid=False, error="Script must import vapoursynth"
            )

        # Note: set_output() is no longer required since it gets auto-appended for preview

        # TODO: More thorough validation by actually running the script in a sandbox
        return ScriptValidationResponse(valid=True)

    except Exception as e:
        return ScriptValidationResponse(
            valid=False, error=f"Validation error: {str(e)}"
        )


@router.get("/vs/frame")
async def get_frame_with_script(
    path: str = Query(..., description="Path to the video file"),
    frame: int = Query(0, description="Frame number to extract"),
    script: str = Query(None, description="Optional VapourSynth script to apply"),
):
    """Extract a frame with optional VapourSynth script applied."""
    try:
        p = Path(path)
        roots = get_allowed_roots()

        if roots and not is_under_allowed_roots(p, roots):
            return Response(content="File path not allowed", status_code=403)

        if not p.exists():
            return Response(content="File not found", status_code=404)

        # Load VapourSynth script in-process for default frame extraction
        # core = vs.core
        # core.std.LoadAllPlugins(
        #     r"C:\VapourSynth\vs-plugins"
        # )  # TODO: this shouldn't need to be called every time
        # try:
        #     core.std.LoadPlugin(r"C:\VapourSynth\vs-plugins\LSMASHSource.dll")
        # except Exception:
        #     # Plugin already loaded
        #     pass

        # If no script provided, use default loading
        if not script or script.strip() == "":
            clip = vs_core.lsmas.LWLibavSource(str(p.absolute()))
            # Convert to RGB24 with proper matrix
            clip = vs_core.resize.Bicubic(clip, format=vs_core.RGB24, matrix_in_s="709")
            vs_frame = clip.get_frame(frame)

            # Convert to RGB - RGB24 format has planes in order R, G, B
            r = np.asarray(vs_frame[0])
            g = np.asarray(vs_frame[1])
            b = np.asarray(vs_frame[2])
            rgb = np.stack([r, g, b], axis=-1)
            img = Image.fromarray(rgb, "RGB")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)

            # Prepare metadata for this frame
            try:
                fps_val = None
                try:
                    fps_val = float(clip.fps)
                except Exception:
                    try:
                        fps_val = float(
                            int(clip.fps.numerator) / int(clip.fps.denominator)
                        )
                    except Exception:
                        fps_val = None

                frame_type = None
                try:
                    frame_type = vs_frame.props.get("_PictType")
                    # Convert bytes to string if necessary
                    if isinstance(frame_type, (bytes, bytearray)):
                        frame_type = frame_type.decode("utf-8", errors="replace")
                    else:
                        frame_type = str(frame_type) if frame_type is not None else None
                except Exception:
                    frame_type = None

                fmt_name = None
                try:
                    fmt_name = (
                        vs_frame.format.name if vs_frame and vs_frame.format else None
                    )
                    if isinstance(fmt_name, (bytes, bytearray)):
                        fmt_name = fmt_name.decode("utf-8", errors="replace")
                except Exception:
                    fmt_name = None

                meta = {
                    "format": fmt_name,
                    "width": int(vs_frame.width) if vs_frame else None,
                    "height": int(vs_frame.height) if vs_frame else None,
                    "fps": float(fps_val) if fps_val is not None else None,
                    "frame_type": frame_type,
                }
            except Exception:
                meta = {
                    "format": None,
                    "width": None,
                    "height": None,
                    "fps": None,
                    "frame_type": None,
                }

            print("META", meta, flush=True)

            return Response(
                content=buf.read(),
                media_type="image/png",
                headers={"X-Frame-Meta": json.dumps(meta)},
            )

        # Apply the VapourSynth script
        # core = vs.core

        # The script should already have the file loaded with lsmas.LWLibavSource
        # Auto-append required lines for preview
        preview_script = script

        # Check if the script already has RGB conversion and set_output
        if "format=vs.RGB24" not in script:
            preview_script += (
                "\n\n# Convert to RGB for preview (remove this line for final output)"
            )
            preview_script += (
                '\nclip = core.resize.Bicubic(clip, format=vs.RGB24, matrix_in_s="709")'
            )

        if "set_output()" not in script:
            preview_script += "\n\n# Set output"
            preview_script += "\nclip.set_output()"

        print("🎬 EXECUTING VAPOURSYNTH SCRIPT:")
        print(f"📁 File path: {p.absolute()}")
        print(f"📜 Original Script: {script}")
        print(f"📜 Preview Script: {preview_script}")

        # Execute the preview script and extract the clip variable
        vs_globals = {"vs": vs, "core": vs_core}
        exec(preview_script, vs_globals)

        # Get the clip from the namespace
        if "clip" not in vs_globals:
            return Response(
                content="Script did not define a 'clip' variable", status_code=400
            )

        clip = vs_globals["clip"]

        if frame >= clip.num_frames:
            frame = clip.num_frames - 1

        # Get the frame
        vs_frame = clip.get_frame(frame)

        # Get frame format info
        format_name = vs_frame.format.name
        print(
            f"🎨 Frame format: {format_name}, Size: {vs_frame.width}x{vs_frame.height}"
        )

        # Convert to RGB based on the format
        if format_name == "RGB24":
            # RGB24 format - planes are R, G, B
            r = np.asarray(vs_frame[0])
            g = np.asarray(vs_frame[1])
            b = np.asarray(vs_frame[2])
        elif format_name.startswith("YUV"):
            # YUV format - convert to RGB
            y_array = np.array(vs_frame[0], copy=False)
            u_array = np.array(vs_frame[1], copy=False)
            v_array = np.array(vs_frame[2], copy=False)

            # Basic YUV to RGB conversion (simplified)
            y = y_array.astype(np.float32)
            u = u_array.astype(np.float32) - 128
            v = v_array.astype(np.float32) - 128

            r = np.clip(y + 1.402 * v, 0, 255).astype(np.uint8)
            g = np.clip(y - 0.344136 * u - 0.714136 * v, 0, 255).astype(np.uint8)
            b = np.clip(y + 1.772 * u, 0, 255).astype(np.uint8)
        else:
            # Unknown format - try to use resize to convert to RGB24
            rgb_clip = vs_core.resize.Bicubic(clip, format=vs.RGB24, matrix_in_s="709")
            rgb_frame = rgb_clip.get_frame(frame)
            r = np.asarray(rgb_frame[0])
            g = np.asarray(rgb_frame[1])
            b = np.asarray(rgb_frame[2])

        # Stack planes into (H, W, 3) RGB image
        rgb = np.stack([r, g, b], axis=-1)
        img = Image.fromarray(rgb, "RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        # Prepare metadata
        try:
            fps_val = None
            try:
                fps_val = float(clip.fps)
            except Exception:
                try:
                    fps_val = float(int(clip.fps.numerator) / int(clip.fps.denominator))
                except Exception:
                    fps_val = None

        except Exception:
            fps_val = None

        frame_type = None
        try:
            frame_type = vs_frame.props.get("_PictType")
            if isinstance(frame_type, (bytes, bytearray)):
                frame_type = frame_type.decode("utf-8", errors="replace")
            else:
                frame_type = str(frame_type) if frame_type is not None else None
        except Exception:
            frame_type = None

        fmt_name = None
        try:
            fmt_name = format_name
            if isinstance(fmt_name, (bytes, bytearray)):
                fmt_name = fmt_name.decode("utf-8", errors="replace")
        except Exception:
            fmt_name = None

        meta = {
            "format": fmt_name,
            "width": int(vs_frame.width) if vs_frame else None,
            "height": int(vs_frame.height) if vs_frame else None,
            "fps": float(fps_val) if fps_val is not None else None,
            "frame_type": frame_type,
        }
        print("META", meta, flush=True)
        return Response(
            content=buf.read(),
            media_type="image/png",
            headers={"X-Frame-Meta": json.dumps(meta)},
        )

    except Exception as e:
        print(f"Script frame extraction error: {str(e)}", flush=True)
        return Response(content=f"Script frame extraction error: {e}", status_code=500)


@router.post("/vs/auto-crop")
async def auto_crop(request: Request):
    """Server-side auto-crop: sample frames and detect crop values server-side.

    Request JSON: { path: string, sample_count?: number }
    Response JSON: { ok: True, path, detections: [{frame, crop:{left,top,right,bottom}}], recommendedCrop }
    """
    data = await request.json()
    path = data.get("path")
    sample_count = int(data.get("sample_count", 20)) if data.get("sample_count") else 20

    if not path:
        return {"ok": False, "error": "No path provided"}

    def round_down_even(n: int) -> int:
        r = int(n or 0)
        return r if r % 2 == 0 else max(0, r - 1)

    try:
        p = Path(path)
        roots = get_allowed_roots()

        if roots and not is_under_allowed_roots(p, roots):
            return {"ok": False, "error": "File path not allowed"}

        if not p.exists():
            return {"ok": False, "error": "File not found"}

        # Try to open source with L-Smash then FFMS2
        clip = None
        try:
            clip = vs_core.lsmas.LWLibavSource(str(p))
        except Exception:
            try:
                clip = vs_core.ffms2.Source(str(p))
            except Exception as e:
                return {
                    "ok": False,
                    "error": f"No suitable source filter available: {e}",
                }

        total_frames = int(clip.num_frames)

        # No fast-path plugin usage; use pure VapourSynth frame extraction and analysis below

        # Determine sample frames evenly across the clip
        n = max(5, min(50, sample_count))
        step = max(1, total_frames // n)
        sample_frames = [min(i * step, total_frames - 1) for i in range(n)]

        # Convert clip to RGB24 once for consistent frame extraction
        rgb_clip = vs_core.resize.Bicubic(clip, format=vs.RGB24, matrix_in_s="709")

        # Extract frames as RGB numpy arrays (sequential for simplicity)
        frames_rgb = []
        for frame_no in sample_frames:
            try:
                fn = min(frame_no, clip.num_frames - 1)
                rgb_frame = rgb_clip.get_frame(fn)
                # Stack RGB planes directly
                rgb = np.stack(
                    [
                        np.asarray(rgb_frame[0]),
                        np.asarray(rgb_frame[1]),
                        np.asarray(rgb_frame[2]),
                    ],
                    axis=-1,
                )
                frames_rgb.append(rgb)
            except Exception as e:
                print(f"Failed to extract frame {frame_no}: {e}", flush=True)

        # Analyze frames in parallel
        import concurrent.futures

        def analyze_numpy_frame(rgb_arr):
            """StaxRip-like AutoCrop detection using HSL lightness."""
            h, w = rgb_arr.shape[:2]

            # Compute HSL lightness: L = (max(R,G,B) + min(R,G,B)) / 2 / 255
            lum = (rgb_arr.max(axis=2) + rgb_arr.min(axis=2)) / 510.0
            lum_threshold = 0.06

            # Sample 21 positions along each axis (matches StaxRip)
            xValues = [int(w * x / 21) for x in range(21)]
            yValues = [int(h * y / 21) for y in range(21)]

            quarter_h = max(1, h // 4)
            quarter_w = max(1, w // 4)

            # Scan columns for top/bottom
            top_samples = []
            bottom_samples = []
            for xv in xValues:
                # Scan from top
                top_val = 0
                for y in range(quarter_h):
                    if lum[y, xv] < lum_threshold:
                        top_val = y + 1
                    else:
                        break
                top_samples.append(top_val)

                # Scan from bottom
                bottom_val = 0
                for y in range(h - 1, h - 1 - quarter_h, -1):
                    if lum[y, xv] < lum_threshold:
                        bottom_val = h - y
                    else:
                        break
                bottom_samples.append(bottom_val)

            # Scan rows for left/right
            left_samples = []
            right_samples = []
            for yv in yValues:
                # Scan from left
                left_val = 0
                for x in range(quarter_w):
                    if lum[yv, x] < lum_threshold:
                        left_val = x + 1
                    else:
                        break
                left_samples.append(left_val)

                # Scan from right
                right_val = 0
                for x in range(w - 1, w - 1 - quarter_w, -1):
                    if lum[yv, x] < lum_threshold:
                        right_val = w - x
                    else:
                        break
                right_samples.append(right_val)

            return {
                "left_samples": left_samples,
                "top_samples": top_samples,
                "right_samples": right_samples,
                "bottom_samples": bottom_samples,
            }

        # Analyze all frames in parallel
        all_samples = []
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(8, os.cpu_count() or 4)
        ) as ex:
            all_samples = list[dict[str, list[Any]]](
                ex.map(analyze_numpy_frame, frames_rgb)
            )

        all_left = []
        all_top = []
        all_right = []
        all_bottom = []

        for samples in all_samples:
            all_left.extend(samples["left_samples"])
            all_top.extend(samples["top_samples"])
            all_right.extend(samples["right_samples"])
            all_bottom.extend(samples["bottom_samples"])

        recommended = {
            "left": round_down_even(min(all_left) if all_left else 0),
            "top": round_down_even(min(all_top) if all_top else 0),
            "right": round_down_even(min(all_right) if all_right else 0),
            "bottom": round_down_even(min(all_bottom) if all_bottom else 0),
        }

        return {"ok": True, "path": str(p), "recommendedCrop": recommended}

    except Exception as e:
        print(f"Auto-crop failed: {e}", flush=True)
        return {"ok": False, "error": str(e)}
