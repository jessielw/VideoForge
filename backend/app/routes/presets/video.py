from datetime import datetime

from fastapi import APIRouter, HTTPException

from app.database import get_db
from app.schemas.presets.video import (
    VideoEncoderPresetCreate,
    VideoEncoderPresetResponse,
)

router = APIRouter(tags=["video_presets"])


@router.get("/presets/video", response_model=list[VideoEncoderPresetResponse])
async def get_presets(encoder: str | None = None):
    """Get all encoder presets, optionally filtered by encoder type."""
    with get_db() as conn:
        cursor = conn.cursor()

        if encoder:
            cursor.execute(
                """
                SELECT * FROM encoder_presets 
                WHERE encoder = ?
                ORDER BY is_builtin DESC, created_at DESC
            """,
                (encoder,),
            )
        else:
            cursor.execute("""
                SELECT * FROM encoder_presets 
                ORDER BY is_builtin DESC, created_at DESC
            """)

        rows = cursor.fetchall()

        presets = []
        for row in rows:
            presets.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "description": row["description"],
                    "encoder": row["encoder"],
                    "rate_control_mode": row["rate_control_mode"],
                    "crf": row["crf"],
                    "target_bitrate": row["target_bitrate"],
                    "preset": row["preset"],
                    "tune": row["tune"],
                    "custom_args": row["custom_args"],
                    "is_builtin": bool(row["is_builtin"]),
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            )

        return presets


@router.get("/presets/video/{preset_id}", response_model=VideoEncoderPresetResponse)
async def get_preset(preset_id: str):
    """Get a specific encoder preset by ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM encoder_presets WHERE id = ?", (preset_id,))
        row = cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Preset not found")

        return {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "encoder": row["encoder"],
            "rate_control_mode": row["rate_control_mode"],
            "crf": row["crf"],
            "target_bitrate": row["target_bitrate"],
            "preset": row["preset"],
            "tune": row["tune"],
            "custom_args": row["custom_args"],
            "is_builtin": bool(row["is_builtin"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


@router.post("/presets/video", response_model=VideoEncoderPresetResponse)
async def create_preset(preset: VideoEncoderPresetCreate):
    """Create a new custom encoder preset."""
    with get_db() as conn:
        cursor = conn.cursor()

        # Generate unique ID
        import random

        preset_id = (
            f"custom-{int(datetime.utcnow().timestamp())}-{random.randint(1000, 9999)}"
        )
        now = datetime.utcnow().isoformat()

        cursor.execute(
            """
            INSERT INTO encoder_presets 
            (id, name, description, encoder, rate_control_mode, crf, target_bitrate,
             preset, tune, custom_args, is_builtin, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
        """,
            (
                preset_id,
                preset.name,
                preset.description,
                preset.encoder,
                preset.rate_control_mode,
                preset.crf,
                preset.target_bitrate,
                preset.preset,
                preset.tune,
                preset.custom_args,
                now,
                now,
            ),
        )

        conn.commit()

        # Fetch and return the created preset
        cursor.execute("SELECT * FROM encoder_presets WHERE id = ?", (preset_id,))
        row = cursor.fetchone()

        return {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "encoder": row["encoder"],
            "rate_control_mode": row["rate_control_mode"],
            "crf": row["crf"],
            "target_bitrate": row["target_bitrate"],
            "preset": row["preset"],
            "tune": row["tune"],
            "custom_args": row["custom_args"],
            "is_builtin": bool(row["is_builtin"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


@router.delete("/presets/video/{preset_id}")
async def delete_preset(preset_id: str):
    """Delete a custom encoder preset (cannot delete built-in presets)."""
    with get_db() as conn:
        cursor = conn.cursor()

        # Check if preset exists and is not built-in
        cursor.execute(
            "SELECT is_builtin FROM encoder_presets WHERE id = ?", (preset_id,)
        )
        row = cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Preset not found")

        if row["is_builtin"]:
            raise HTTPException(status_code=403, detail="Cannot delete built-in preset")

        cursor.execute("DELETE FROM encoder_presets WHERE id = ?", (preset_id,))
        conn.commit()

        return {"ok": True, "message": "Preset deleted successfully"}
