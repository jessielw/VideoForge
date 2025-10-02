import os
import subprocess
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pymediainfo import MediaInfo
from fastapi.responses import Response
from pydantic import BaseModel
from PIL import Image
import io
import vapoursynth as vs
import numpy as np

# os.environ["VAPOURSYNTH_PLUGIN_PATH"] = r"C:\VapourSynth\vs-plugins"

load_dotenv()

app = FastAPI()

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
)


def get_allowed_roots():
    roots = os.environ.get("media")
    if roots:
        return [Path(p).resolve() for p in roots.split(";") if p]
    # Default to /media for Docker/Linux, or C:/media for Windows
    # if os.name == 'nt':
    #     return [Path("C:/media").resolve()]
    # else:
    # return [Path("/media").resolve()]


def is_under_allowed_roots(p: Path, roots):
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


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/list")
async def list(path: str = Query(None)):
    """List files/folders under allowed roots. If no path, return roots."""
    roots = get_allowed_roots()
    if not roots:
        return {"ok": False, "reason": "No allowed roots configured"}

    if not path:
        # Return roots as entries
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
                entries.append({"name": str(r), "is_dir": True, "normalized": str(r)})
        return {"ok": True, "entries": entries, "path": None}

    p = Path(path)
    if not is_under_allowed_roots(p, roots):
        # If not under allowed roots, just return roots list
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
                entries.append({"name": str(r), "is_dir": True, "normalized": str(r)})
        return {"ok": True, "entries": entries, "path": None}
    if not p.exists():
        return {"ok": False, "reason": "Path does not exist"}
    if not p.is_dir():
        # If it's a file, return its parent directory
        p = p.parent

    entries = []
    try:
        for child in sorted(
            p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())
        ):
            try:
                st = child.stat()
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

    return {"ok": True, "entries": entries, "path": str(p)}


@app.get("/api/details")
async def details(path: str = Query(...)):
    """Return media info for a file."""
    roots = get_allowed_roots()
    p = Path(path)
    if not is_under_allowed_roots(p, roots):
        return {"ok": False, "reason": "Path not under allowed roots"}
    if not p.exists() or not p.is_file():
        return {"ok": False, "reason": "File does not exist"}
    try:
        media_info = MediaInfo.parse(str(p), legacy_stream_display=True)
        return {"ok": True, "mediainfo": media_info.to_data()}
    except Exception as e:
        return {"ok": False, "reason": f"Failed to parse: {e}"}


@app.post("/api/index")
async def index_file(request: Request):
    print("IN REQUEST", flush=True)
    data = await request.json()
    print("DATA", data, flush=True)
    file_path = data.get("path")
    print("Path:", file_path, flush=True)
    if not file_path or not os.path.exists(file_path):
        return {"ok": False, "error": "File not found"}

    try:
        # Use MediaInfo to get comprehensive media information
        media_info = MediaInfo.parse(file_path)
        
        result = {
            "ok": True,
            "path": file_path,
            "general": {},
            "video_tracks": [],
            "audio_tracks": [],
            "subtitle_tracks": [],
            "menu_tracks": []
        }
        
        # Extract general information
        for track in media_info.tracks:
            if track.track_type == "General":
                result["general"] = {
                    "filename": track.file_name,
                    "format": track.format,
                    "file_size": track.file_size,
                    "duration": track.duration,
                    "overall_bitrate": track.overall_bit_rate,
                    "format_profile": track.format_profile,
                    "encoded_date": track.encoded_date,
                    "writing_application": track.writing_application,
                    "writing_library": track.writing_library
                }
            
            elif track.track_type == "Video":
                video_info = {
                    "track_id": track.track_id,
                    "format": track.format,
                    "format_profile": track.format_profile,
                    "format_level": track.format_level,
                    "width": track.width,
                    "height": track.height,
                    "display_aspect_ratio": track.display_aspect_ratio,
                    "pixel_aspect_ratio": track.pixel_aspect_ratio,
                    "frame_rate": track.frame_rate,
                    "frame_count": track.frame_count,
                    "bit_rate": track.bit_rate,
                    "bit_depth": track.bit_depth,
                    "chroma_subsampling": track.chroma_subsampling,
                    "color_space": track.color_space,
                    "color_range": track.color_range,
                    "color_primaries": track.color_primaries,
                    "transfer_characteristics": track.transfer_characteristics,
                    "matrix_coefficients": track.matrix_coefficients,
                    "scan_type": track.scan_type,
                    "scan_order": track.scan_order,
                    "codec_id": track.codec_id,
                    "encoded_library_name": track.encoded_library_name,
                    "encoded_library_version": track.encoded_library_version,
                    "encoded_library_settings": track.encoded_library_settings
                }
                result["video_tracks"].append(video_info)
            
            elif track.track_type == "Audio":
                audio_info = {
                    "track_id": track.track_id,
                    "format": track.format,
                    "format_profile": track.format_profile,
                    "codec_id": track.codec_id,
                    "channels": track.channel_s,
                    "channel_layout": track.channel_layout,
                    "sampling_rate": track.sampling_rate,
                    "bit_rate": track.bit_rate,
                    "bit_depth": track.bit_depth,
                    "language": track.language,
                    "title": track.title,
                    "default": track.default,
                    "forced": track.forced,
                    "compression_mode": track.compression_mode,
                    "encoded_library_name": track.encoded_library_name,
                    "encoded_library_version": track.encoded_library_version
                }
                result["audio_tracks"].append(audio_info)
            
            elif track.track_type == "Text":
                subtitle_info = {
                    "track_id": track.track_id,
                    "format": track.format,
                    "codec_id": track.codec_id,
                    "language": track.language,
                    "title": track.title,
                    "default": track.default,
                    "forced": track.forced
                }
                result["subtitle_tracks"].append(subtitle_info)
            
            elif track.track_type == "Menu":
                menu_info = {
                    "track_id": track.track_id,
                    "format": track.format,
                    "duration": track.duration
                }
                result["menu_tracks"].append(menu_info)
        
        # Also get VapourSynth frame information for accuracy
        try:
            vpy_script = f"""
import vapoursynth as vs
core = vs.core
clip = core.lsmas.LWLibavSource(r'''{file_path}''')
print('VS_FRAME_COUNT:', clip.num_frames)
print('VS_WIDTH:', clip.width)
print('VS_HEIGHT:', clip.height)
print('VS_FPS_NUM:', clip.fps.numerator)
print('VS_FPS_DEN:', clip.fps.denominator)
"""
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=".vpy", mode="w", encoding="utf-8"
            ) as f:
                f.write(vpy_script)
                script_path = f.name

            vs_result = subprocess.run(
                ["vspipe", "--info", script_path, "-"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            vs_info = {}
            for line in vs_result.stdout.splitlines():
                if "VS_FRAME_COUNT:" in line:
                    vs_info["frames"] = int(line.split(":", 1)[1].strip())
                elif "VS_WIDTH:" in line:
                    vs_info["width"] = int(line.split(":", 1)[1].strip())
                elif "VS_HEIGHT:" in line:
                    vs_info["height"] = int(line.split(":", 1)[1].strip())
                elif "VS_FPS_NUM:" in line:
                    vs_info["fps_num"] = int(line.split(":", 1)[1].strip())
                elif "VS_FPS_DEN:" in line:
                    vs_info["fps_den"] = int(line.split(":", 1)[1].strip())
            
            if vs_info.get("fps_num") and vs_info.get("fps_den"):
                vs_info["fps"] = vs_info["fps_num"] / vs_info["fps_den"]
            
            result["vapoursynth"] = vs_info
            
            os.remove(script_path)
        except Exception as e:
            print(f"VapourSynth probe failed: {e}", flush=True)
            result["vapoursynth"] = {"error": str(e)}
        
        return result
        
    except Exception as e:
        print(f"MediaInfo parsing failed: {e}", flush=True)
        return {"ok": False, "error": f"Failed to parse media info: {str(e)}"}


# Legacy endpoint for backward compatibility
@app.post("/api/index_legacy")
async def index_file_legacy(request: Request):
    print("IN REQUEST", flush=True)
    data = await request.json()
    print("DATA", data, flush=True)
    file_path = data.get("path")
    print("Path:", file_path, flush=True)
    if not file_path or not os.path.exists(file_path):
        return {"ok": False, "error": "File not found"}

    # Create a temporary VapourSynth script to probe the file
    vpy_script = f"""
import vapoursynth as vs
core = vs.core
clip = core.lsmas.LWLibavSource(r'''{file_path}''')
print('FRAME_COUNT:', clip.num_frames)
print('WIDTH:', clip.width)
print('HEIGHT:', clip.height)
"""
    with tempfile.NamedTemporaryFile(
        delete=False, suffix=".vpy", mode="w", encoding="utf-8"
    ) as f:
        f.write(vpy_script)
        script_path = f.name

    try:
        # Run vspipe to execute the script and capture output
        result = subprocess.run(
            ["vspipe", "--info", script_path, "-"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        output = result.stdout
        print("Output:", output, flush=True)
        # Parse output for frame count, width, height
        frame_count = None
        width = None
        height = None
        for line in output.splitlines():
            if "FRAME_COUNT:" in line:
                frame_count = int(line.split(":", 1)[1].strip())
            elif "WIDTH:" in line:
                width = int(line.split(":", 1)[1].strip())
            elif "HEIGHT:" in line:
                height = int(line.split(":", 1)[1].strip())
        info = {
            "ok": True if frame_count and width and height else False,
            "frame_count": frame_count,
            "width": width,
            "height": height,
            "output": output if not (frame_count and width and height) else None,
        }
        return info
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        try:
            os.remove(script_path)
        except Exception:
            pass


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
            compile(script, '<string>', 'exec')
        except SyntaxError as e:
            return ScriptValidationResponse(valid=False, error=f"Syntax error: {e}")
        
        # Basic VapourSynth validation - check for required components
        if "import vapoursynth" not in script and "import vs" not in script:
            return ScriptValidationResponse(valid=False, error="Script must import vapoursynth")
        
        # Note: set_output() is no longer required since it gets auto-appended for preview
        
        # TODO: More thorough validation by actually running the script in a sandbox
        return ScriptValidationResponse(valid=True)
        
    except Exception as e:
        return ScriptValidationResponse(valid=False, error=f"Validation error: {str(e)}")


@app.get("/api/frame")
async def get_frame_with_script(
    path: str = Query(..., description="Path to the video file"),
    frame: int = Query(0, description="Frame number to extract"),
    script: str = Query(None, description="Optional VapourSynth script to apply")
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
        try:
            core.std.LoadPlugin(r"C:\VapourSynth\vs-plugins\LSMASHSource.dll")
        except Exception:
            # Plugin already loaded
            pass
        
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
            
            return Response(content=buf.read(), media_type="image/png")
        
        # Apply the VapourSynth script
        core = vs.core
        
        # The script should already have the file loaded with lsmas.LWLibavSource
        # Auto-append required lines for preview
        preview_script = script
        
        # Check if the script already has RGB conversion and set_output
        if "format=vs.RGB24" not in script:
            preview_script += "\n\n# Convert to RGB for preview (remove this line for final output)"
            preview_script += "\nclip = core.resize.Bicubic(clip, format=vs.RGB24, matrix_in_s=\"709\")"
        
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
        if 'clip' not in vs_globals:
            return Response(content="Script did not define a 'clip' variable", status_code=400)
        
        clip = vs_globals['clip']
        
        if frame >= clip.num_frames:
            frame = clip.num_frames - 1
        
        # Get the frame
        vs_frame = clip.get_frame(frame)
        
        # Get frame format info
        format_name = vs_frame.format.name
        print(f"🎨 Frame format: {format_name}, Size: {vs_frame.width}x{vs_frame.height}")
        
        # Convert to RGB based on the format
        if format_name == 'RGB24':
            # RGB24 format - planes are R, G, B
            r = np.asarray(vs_frame[0])
            g = np.asarray(vs_frame[1])
            b = np.asarray(vs_frame[2])
        elif format_name.startswith('YUV'):
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
        
        return Response(content=buf.read(), media_type="image/png")
        
    except Exception as e:
        print(f"Script frame extraction error: {str(e)}", flush=True)
        return Response(content=f"Script frame extraction error: {e}", status_code=500)
