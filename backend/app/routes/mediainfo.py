from pathlib import Path

from fastapi import APIRouter, Request

from app.schemas.mediainfo import MediaInfoResponse
from app.utils.file_utils import get_allowed_roots, is_under_allowed_roots
from app.utils.mediainfo import safe_get_mediainfo_async

router = APIRouter(prefix="/api/mediainfo", tags=["mediainfo"])


@router.post("", response_model=MediaInfoResponse)
async def get_mediainfo(request: Request):
    """Return MediaInfo for a file."""
    data = await request.json()
    file_path = data.get("path")
    include_raw = bool(data.get("include_raw", False))
    if not file_path:
        return {"ok": False, "error": "No path provided"}

    p = Path(file_path)
    roots = get_allowed_roots()
    if roots and not is_under_allowed_roots(p, roots):
        return {"ok": False, "error": "Path not under allowed roots"}

    if not p.exists():
        return {"ok": False, "error": "File not found"}

    try:
        media_info = await safe_get_mediainfo_async(p)

        result = {
            "ok": True,
            "path": str(p),
            "general": media_info.general_tracks[0].to_data()
            if media_info.general_tracks
            else None,
            "video_tracks": [x.to_data() for x in media_info.video_tracks],
            "audio_tracks": [x.to_data() for x in media_info.audio_tracks],
            "text_tracks": [x.to_data() for x in media_info.text_tracks],
        }
        if include_raw:
            result["mediainfo_data"] = media_info.to_data()
        print(result, flush=True)
        return result
    except Exception as e:
        print(f"MediaInfo parsing failed: {e}", flush=True)
        return {"ok": False, "error": f"Failed to parse media info: {str(e)}"}
