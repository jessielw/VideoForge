from pathlib import Path

from fastapi import APIRouter, Request

from app.utils.file_utils import get_allowed_roots, is_under_allowed_roots
from app.utils.mediainfo import safe_get_mediainfo_async

router = APIRouter(prefix="/api/mediainfo", tags=["mediainfo"])


@router.post("")
async def get_mediainfo(request: Request):
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
        media_info = await safe_get_mediainfo_async(p)
        raw_data = (
            media_info.to_data()
        )  # TODO: just use direct mediainfo instead of doing all of this below

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
        print(result, flush=True)
        return result
    except Exception as e:
        print(f"MediaInfo parsing failed: {e}", flush=True)
        return {"ok": False, "error": f"Failed to parse media info: {str(e)}"}
