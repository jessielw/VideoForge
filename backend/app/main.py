import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pymediainfo import MediaInfo

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
