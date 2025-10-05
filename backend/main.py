import io
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import numpy as np
import vapoursynth as vs
from dotenv import load_dotenv
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from PIL import Image
from pydantic import BaseModel
from pymediainfo import MediaInfo

from app.audio_presets import router as audio_presets_router
from app.database import init_database
from app.job_worker import init_worker, start_worker, stop_worker
from app.jobs import router as jobs_router
from app.presets import router as presets_router

# os.environ["VAPOURSYNTH_PLUGIN_PATH"] = r"C:\VapourSynth\vs-plugins"

import logging

class EndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Check if the log message contains the specific endpoint path
        # For example, to filter out logs for "/health" endpoint
        return record.getMessage().find("/api/jobs/list") == -1

load_dotenv()

vs_pipe_path = r"C:\VapourSynth\VSPipe.exe"
x264_path = r"D:\programming\video-forge\apps\x264.exe"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database and start job worker on startup.

    Note: Worker runs in manual mode - jobs must be explicitly started
    via the API (Start Next button). Worker only processes jobs with
    status='running'.
    """
    print("🔧 Initializing database...", flush=True)
    init_database()
    print("✅ Database initialized successfully", flush=True)
    logging.getLogger("uvicorn.access").addFilter(EndpointFilter())

    print("🔧 Initializing job worker (manual mode)...", flush=True)
    init_worker(vspipe_path=vs_pipe_path, x264_path=x264_path)
    start_worker()
    print("✅ Job worker started successfully", flush=True)

    yield

    # Cleanup on shutdown
    print("🛑 Shutting down job worker...", flush=True)
    stop_worker()
    print("✅ Job worker stopped", flush=True)


app = FastAPI(lifespan=lifespan)


# Include routers
app.include_router(presets_router)
app.include_router(audio_presets_router)
app.include_router(jobs_router)

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Frame-Meta"],
)


def get_allowed_roots():
    """Get configured media roots for file browsing.

    Returns a list of Path objects representing allowed root directories.
    If no roots are configured, returns None (allowing unrestricted access).

    This is primarily for UI browsing organization, not strict security enforcement.
    In a desktop application, we trust the user's configured paths.
    """
    roots = os.environ.get("media")
    if roots:
        return [Path(p).resolve() for p in roots.split(";") if p]
    # For desktop app: If no roots configured, allow browsing from system roots
    # The file browser will show drive letters on Windows or root on Unix
    return None


def is_under_allowed_roots(p: Path, roots):
    """Check if a path is under allowed roots.

    If roots is None or empty, always returns True (permissive mode for desktop app).
    This provides a convenience check for file browser organization without
    being overly restrictive.
    """
    # No roots configured = trust everything
    if not roots:
        return True

    try:
        rp = p.resolve()
    except Exception:
        return False

    for r in roots:
        try:
            if r in rp.parents or rp == r:
                return True
        except Exception:
            continue
    return False


# VapourSynth initialization helper
VS_INITIALIZED = False
# TODO: we need to figure out where the plugins will be and how this will be implemented
# PLUGIN_PATH = os.environ.get(r'C:\VapourSynth\vs-plugins')
PLUGIN_PATH = r"C:\VapourSynth\vs-plugins"


def init_vapoursynth():
    """Initialize VapourSynth core and load plugins once."""
    global VS_INITIALIZED
    core = vs.core

    if VS_INITIALIZED:
        return core

    # try to load plugins from configured path (if provided)
    if PLUGIN_PATH:
        try:
            core.std.LoadAllPlugins(str(PLUGIN_PATH))
        except Exception:
            pass

    VS_INITIALIZED = True
    return core


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/mkdir")
async def create_directory(request: Request):
    """Create a new directory.

    Request JSON: { path: string }
    Response: { ok: bool, path?: string, error?: string }

    The path should be an absolute path. If a relative path is provided,
    it will be rejected to avoid creating folders in unexpected locations.
    """
    data = await request.json()
    dir_path = data.get("path")

    print(f"📁 mkdir request received: {dir_path}", flush=True)

    if not dir_path:
        return {"ok": False, "error": "No path provided"}

    # Convert to Path and resolve to absolute path
    p = Path(dir_path)
    print(f"📁 Path object: {p}", flush=True)
    print(f"📁 Is absolute: {p.is_absolute()}", flush=True)
    print(f"📁 Current working dir: {Path.cwd()}", flush=True)

    # If the path isn't absolute, try to make it absolute
    # This handles both Windows (C:/) and Unix (/) absolute paths
    if not p.is_absolute():
        return {"ok": False, "error": f"Path must be absolute. Received: {dir_path}"}

    # Resolve the path (handles .. and symlinks)
    try:
        p_resolved = p.resolve()
    except Exception as e:
        return {"ok": False, "error": f"Invalid path: {str(e)}"}

    # Check if directory already exists
    if p_resolved.exists():
        if p_resolved.is_dir():
            return {"ok": False, "error": "Directory already exists"}
        else:
            return {"ok": False, "error": "A file with that name already exists"}

    try:
        # Create the directory and all parent directories if needed
        p_resolved.mkdir(parents=True, exist_ok=False)
        print(f"✅ Created directory: {p_resolved}", flush=True)
        return {"ok": True, "path": str(p_resolved)}
    except PermissionError:
        return {"ok": False, "error": "Permission denied - check folder permissions"}
    except FileExistsError:
        return {"ok": False, "error": "Directory already exists"}
    except Exception as e:
        return {"ok": False, "error": f"Failed to create directory: {str(e)}"}


@app.get("/api/list")
async def file_list(path: str = Query(None)):
    """List files/folders under allowed roots. If no path, return roots or system drives.

    For desktop applications with configured media paths, we start browsing from those roots.
    If no media paths are configured, we show system drives (Windows) or root (Unix).
    """
    roots = get_allowed_roots()

    if not path:
        # If roots are configured, return them as starting points
        if roots:
            entries = []
            for r in roots:
                try:
                    stat = r.stat()
                    entries.append(
                        {
                            "name": str(r),
                            "is_dir": True,
                            "normalized": str(r),
                            "size": stat.st_size if r.exists() else None,
                            "mtime": stat.st_mtime if r.exists() else None,
                        }
                    )
                except Exception:
                    entries.append(
                        {"name": str(r), "is_dir": True, "normalized": str(r)}
                    )
            return {"ok": True, "entries": entries, "path": None}
        else:
            # No roots configured - show system drives on Windows, root on Unix
            entries = []
            if os.name == "nt":
                # Windows: list available drives
                import string

                for letter in string.ascii_uppercase:
                    drive = Path(f"{letter}:/")
                    if drive.exists():
                        try:
                            entries.append(
                                {
                                    "name": f"{letter}:/",
                                    "is_dir": True,
                                    "normalized": str(drive),
                                }
                            )
                        except Exception:
                            pass
            else:
                # Unix: start at root
                entries.append(
                    {
                        "name": "/",
                        "is_dir": True,
                        "normalized": "/",
                    }
                )
            return {"ok": True, "entries": entries, "path": None}

    p = Path(path)

    # Check if path is accessible (permissive check when roots=None)
    if not is_under_allowed_roots(p, roots):
        # Path not under allowed roots - redirect to roots if configured
        if roots:
            entries = []
            for r in roots:
                try:
                    stat = r.stat()
                    entries.append(
                        {
                            "name": str(r),
                            "is_dir": True,
                            "normalized": str(r),
                            "size": stat.st_size if r.exists() else None,
                            "mtime": stat.st_mtime if r.exists() else None,
                        }
                    )
                except Exception:
                    entries.append(
                        {"name": str(r), "is_dir": True, "normalized": str(r)}
                    )
            return {"ok": True, "entries": entries, "path": None}
        # If no roots, this shouldn't happen due to permissive is_under_allowed_roots
        # but handle gracefully anyway

    if not p.exists():
        return {"ok": False, "reason": "Path does not exist"}
    if not p.is_dir():
        # If it's a file, return its parent directory
        p = p.parent

    # Resolve to absolute path for consistency
    p = p.resolve()

    entries = []
    try:
        for child in sorted(
            p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())
        ):
            try:
                st = child.stat()
                if child.is_file() and child.suffix not in (".mkv", ".mp4"):
                    continue
                entries.append(
                    {
                        "name": child.name,
                        "is_dir": child.is_dir(),
                        "normalized": str(child.resolve()),
                        "size": st.st_size,
                        "mtime": st.st_mtime,
                    }
                )
            except Exception:
                entries.append(
                    {
                        "name": child.name,
                        "is_dir": child.is_dir(),
                        "normalized": str(child),
                    }
                )
    except Exception as e:
        return {"ok": False, "reason": f"Could not list directory: {e}"}

    # Return absolute path
    return {"ok": True, "entries": entries, "path": str(p)}


@app.post("/api/mediainfo")
async def mediainfo_file(request: Request):
    """Return MediaInfo for a file. This endpoint only runs MediaInfo parsing and returns track info.
    VapourSynth probing (frame count/size/fps) is handled by /api/vs/probe which uses the VapourSynth API directly.
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

    try:
        media_info = MediaInfo.parse(str(p), legacy_stream_display=True)
        raw_data = media_info.to_data()

        # Parse tracks into structured format for frontend
        tracks = raw_data.get("tracks", [])

        # Extract general info
        general_track = next(
            (t for t in tracks if t.get("track_type") == "General"), {}
        )

        # Extract video tracks
        video_tracks = [
            {
                "track_id": t.get("track_id"),
                "format": t.get("format"),
                "format_profile": t.get("format_profile"),
                "format_level": t.get("format_level"),
                "width": t.get("width"),
                "height": t.get("height"),
                "display_aspect_ratio": t.get("display_aspect_ratio"),
                "pixel_aspect_ratio": t.get("pixel_aspect_ratio"),
                "frame_rate": t.get("frame_rate"),
                "frame_count": t.get("frame_count"),
                "bit_rate": t.get("bit_rate"),
                "bit_depth": t.get("bit_depth"),
                "chroma_subsampling": t.get("chroma_subsampling"),
                "color_space": t.get("color_space"),
                "scan_type": t.get("scan_type"),
                "codec_id": t.get("codec_id"),
            }
            for t in tracks
            if t.get("track_type") == "Video"
        ]

        # Extract audio tracks
        audio_tracks = [
            {
                "track_id": t.get("track_id"),
                "format": t.get("format"),
                "format_profile": t.get("format_profile"),
                "codec_id": t.get("codec_id"),
                "channels": t.get(
                    "channel_s"
                ),  # Note: pymediainfo uses "channel_s" not "channels"
                "channel_layout": t.get("channel_layout"),
                "sampling_rate": t.get("sampling_rate"),
                "bit_rate": t.get("bit_rate"),
                "bit_depth": t.get("bit_depth"),
                "language": t.get("language"),
                "title": t.get("title"),
                "default": t.get("default"),
                "forced": t.get("forced"),
                "compression_mode": t.get("compression_mode"),
            }
            for t in tracks
            if t.get("track_type") == "Audio"
        ]

        # Extract subtitle tracks
        subtitle_tracks = [
            {
                "track_id": t.get("track_id"),
                "format": t.get("format"),
                "codec_id": t.get("codec_id"),
                "language": t.get("language"),
                "title": t.get("title"),
                "default": t.get("default"),
                "forced": t.get("forced"),
            }
            for t in tracks
            if t.get("track_type") in ("Text", "Subtitle")
        ]

        result = {
            "ok": True,
            "path": str(p),
            "general": {
                "filename": general_track.get("file_name"),
                "format": general_track.get("format"),
                "file_size": general_track.get("file_size"),
                "duration": general_track.get("duration"),
                "overall_bitrate": general_track.get("overall_bit_rate"),
                "format_profile": general_track.get("format_profile"),
                "writing_application": general_track.get("writing_application"),
                "writing_library": general_track.get("writing_library"),
            },
            "video_tracks": video_tracks,
            "audio_tracks": audio_tracks,
            "subtitle_tracks": subtitle_tracks,
            "mediainfo": raw_data,  # Keep raw data for MediaInfoPanel compatibility
        }
        return result
    except Exception as e:
        print(f"MediaInfo parsing failed: {e}", flush=True)
        return {"ok": False, "error": f"Failed to parse media info: {str(e)}"}


@app.post("/api/vs/probe")
async def vapoursynth_probe_file(request: Request):
    """Probe a file using VapourSynth directly to get frame count, width, height, and fps.

    Returns a combined result with MediaInfo + VapourSynth probing when possible.
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

    vs_info = {}
    try:
        core = init_vapoursynth()

        # Use LWLibavSource if available, otherwise try ffms2
        clip = None
        try:
            clip = core.lsmas.LWLibavSource(str(p))
        except Exception:
            try:
                clip = core.ffms2.Source(str(p))
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

    return {
        "ok": True,
        "path": str(p),
        "vapoursynth": vs_info,
    }


# Pydantic models for API requests
class ScriptValidationRequest(BaseModel):
    script: str


class ScriptValidationResponse(BaseModel):
    valid: bool
    error: str | None = None


@app.post("/api/script/validate", response_model=ScriptValidationResponse)
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


@app.get("/api/frame")
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
        core = vs.core
        core.std.LoadAllPlugins(
            r"C:\VapourSynth\vs-plugins"
        )  # TODO: this shouldn't need to be called every time
        # try:
        #     core.std.LoadPlugin(r"C:\VapourSynth\vs-plugins\LSMASHSource.dll")
        # except Exception:
        #     # Plugin already loaded
        #     pass

        # If no script provided, use default loading
        if not script or script.strip() == "":
            clip = core.lsmas.LWLibavSource(str(p.absolute()))
            # Convert to RGB24 with proper matrix
            clip = core.resize.Bicubic(clip, format=vs.RGB24, matrix_in_s="709")
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
        core = vs.core

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
        vs_globals = {"vs": vs, "core": core}
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
            rgb_clip = core.resize.Bicubic(clip, format=vs.RGB24, matrix_in_s="709")
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


@app.post("/api/auto-crop")
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

        core = init_vapoursynth()

        # Try to open source with L-Smash then FFMS2
        clip = None
        try:
            clip = core.lsmas.LWLibavSource(str(p))
        except Exception:
            try:
                clip = core.ffms2.Source(str(p))
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
        rgb_clip = core.resize.Bicubic(clip, format=vs.RGB24, matrix_in_s="709")

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


# @app.get("/api/frame/meta")
# async def get_frame_meta(
#     path: str = Query(..., description="Path to the video file"),
#     frame: int = Query(0, description="Frame number to inspect"),
#     script: str = Query(None, description="Optional VapourSynth script to apply"),
# ):
#     """Return metadata for a frame produced by the script/clip: format name, width, height, fps, frame type."""
#     try:
#         p = Path(path)
#         roots = get_allowed_roots()

#         if roots and not is_under_allowed_roots(p, roots):
#             return {"ok": False, "error": "File path not allowed"}

#         if not p.exists():
#             return {"ok": False, "error": "File not found"}

#         core = init_vapoursynth()

#         # If no script provided, create a default loader
#         if not script or script.strip() == "":
#             try:
#                 clip = core.lsmas.LWLibavSource(str(p.absolute()))
#             except Exception:
#                 clip = core.ffms2.Source(str(p.absolute()))

#             # Try to collect fps
#             fps_val = None
#             try:
#                 fps_val = float(clip.fps)
#             except Exception:
#                 try:
#                     fps_val = float(int(clip.fps.numerator) / int(clip.fps.denominator))
#                 except Exception:
#                     fps_val = None

#             # bound frame
#             if frame >= clip.num_frames:
#                 frame = clip.num_frames - 1

#             vs_frame = clip.get_frame(frame)

#             pict = None
#             try:
#                 pict = vs_frame.props.get("_PictType")
#             except Exception:
#                 pict = None

#             fmt = None
#             try:
#                 fmt = vs_frame.format.name
#             except Exception:
#                 fmt = None

#             return {
#                 "ok": True,
#                 "format": fmt,
#                 "width": int(vs_frame.width),
#                 "height": int(vs_frame.height),
#                 "fps": fps_val,
#                 "frame_type": pict,
#             }

#         # If a script is provided, execute it like in get_frame_with_script but return metadata
#         core = vs.core

#         preview_script = script
#         # ensure clip variable exists and convert to RGB only when needed for logic; metadata doesn't require RGB
#         if "set_output()" not in script:
#             preview_script += "\n\n# Set output\nclip.set_output()"

#         vs_globals = {"vs": vs, "core": core}
#         exec(preview_script, vs_globals)

#         if "clip" not in vs_globals:
#             return {"ok": False, "error": "Script did not define a 'clip' variable"}

#         clip = vs_globals["clip"]

#         if frame >= clip.num_frames:
#             frame = clip.num_frames - 1

#         vs_frame = clip.get_frame(frame)

#         pict = None
#         try:
#             pict = vs_frame.props.get("_PictType")
#         except Exception:
#             pict = None

#         fmt = None
#         try:
#             fmt = vs_frame.format.name
#         except Exception:
#             fmt = None

#         fps_val = None
#         try:
#             fps_val = float(clip.fps)
#         except Exception:
#             try:
#                 fps_val = float(int(clip.fps.numerator) / int(clip.fps.denominator))
#             except Exception:
#                 fps_val = None

#         return {
#             "ok": True,
#             "format": fmt,
#             "width": int(vs_frame.width),
#             "height": int(vs_frame.height),
#             "fps": fps_val,
#             "frame_type": pict,
#         }

#     except Exception as e:
#         print(f"Frame meta extraction error: {e}", flush=True)
#         return {"ok": False, "error": str(e)}
