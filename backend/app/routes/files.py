import platform
from pathlib import Path

from fastapi import APIRouter, Query, Request

from app.utils.file_utils import get_allowed_roots, is_under_allowed_roots

router = APIRouter()


@router.post("/mkdir")
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


@router.get("/list")
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
            if platform.system() == "Windows":
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
