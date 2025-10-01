import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pymediainfo import MediaInfo
from fastapi.responses import Response
from PIL import Image
import io
import vapoursynth as vs
import sys
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


import subprocess
import tempfile


@app.post("/api/index")
async def index_file(request: Request):
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


# Endpoint to extract a single frame as PNG using vspipe
@app.get("/api/frame")
async def get_frame(path: str = Query(...), frame: int = Query(...)):
    print("PATH", path, flush=True)
    print("FRAME", frame, flush=True)
    if not path or not os.path.exists(path):
        return Response(content="File not found", status_code=404)
    try:
        # Load VapourSynth script in-process
        core = vs.core
        try:
            core.std.LoadPlugin(r"C:\VapourSynth\vs-plugins\LSMASHSource.dll")
        except Exception:
            # VapourSynth error: Plugin C:\VapourSynth\vs-plugins\LSMASHSource.dll already loaded (systems.innocent.lsmas) from C:/VapourSynth/vs-plugins/LSMASHSource.dll
            pass
        clip = core.lsmas.LWLibavSource(path)
        """
        This error means VapourSynth's resize filter can't automatically convert the input colorspace to RGB because the source's matrix, transfer, or primaries are "unspecified" (value 2). You need to manually specify these parameters when calling resize.

        Solution:
        Pass explicit matrix_in, transfer_in, and primaries_in arguments to core.resize.Bicubic based on the source video. For most Blu-ray/HD content, use:

        matrix_in=1 (BT.709)
        transfer_in=1 (BT.709)
        primaries_in=1 (BT.709)
        """
        clip = core.resize.Bicubic(
            clip, format=vs.RGB24, matrix_in_s="709"
            # matrix_in=1, transfer_in=1, primaries_in=1, # NOTE: we should auto detect proper colors
            # https://www.vapoursynth.com/doc/functions/video/resize.html
        )
        vs_frame = clip.get_frame(frame)
        width = vs_frame.width
        height = vs_frame.height
        # Modern API: get RGB planes as numpy arrays
        r = np.asarray(vs_frame[0])
        g = np.asarray(vs_frame[1])
        b = np.asarray(vs_frame[2])
        # Stack planes into (H, W, 3) RGB image
        rgb = np.stack([r, g, b], axis=-1)
        img = Image.fromarray(rgb, "RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        print("WE MADE IT HERE!", flush=True)
        return Response(content=buf.read(), media_type="image/png")
    except Exception as e:
        print("VapourSynth error:", str(e), flush=True)
        return Response(content=f"Frame extraction error: {e}", status_code=500)
