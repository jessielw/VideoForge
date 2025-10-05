"""
Audio preset management routes
"""

import json
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .database import get_db_connection

router = APIRouter(prefix="/api/audio-presets", tags=["audio-presets"])


class AudioPresetCreate(BaseModel):
    name: str
    description: str = ""
    config: dict  # AudioEncoderConfig as JSON


@router.get("")
async def list_audio_presets():
    """Get all audio presets."""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT id, name, description, config, is_builtin, created_at, updated_at
            FROM audio_presets
            ORDER BY is_builtin DESC, name ASC
            """
        )

        rows = cursor.fetchall()
        presets = []

        for row in rows:
            presets.append(
                {
                    "id": row[0],
                    "name": row[1],
                    "description": row[2],
                    "config": json.loads(row[3]),
                    "isBuiltin": bool(row[4]),
                    "createdAt": row[5],
                    "updatedAt": row[6],
                }
            )

        return {"ok": True, "presets": presets}

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to list presets: {str(e)}"
        )
    finally:
        conn.close()


@router.post("")
async def create_audio_preset(preset: AudioPresetCreate):
    """Create a new audio preset."""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        preset_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        cursor.execute(
            """
            INSERT INTO audio_presets (
                id, name, description, config, is_builtin, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                preset_id,
                preset.name,
                preset.description,
                json.dumps(preset.config),
                0,  # Not builtin
                now,
                now,
            ),
        )
        conn.commit()

        return {"ok": True, "presetId": preset_id, "message": "Preset created successfully"}

    except Exception as e:
        conn.rollback()
        raise HTTPException(
            status_code=500, detail=f"Failed to create preset: {str(e)}"
        )
    finally:
        conn.close()


@router.delete("/{preset_id}")
async def delete_audio_preset(preset_id: str):
    """Delete an audio preset."""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Check if preset is builtin
        cursor.execute("SELECT is_builtin FROM audio_presets WHERE id = ?", (preset_id,))
        row = cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Preset not found")

        if row[0]:  # is_builtin
            raise HTTPException(
                status_code=400, detail="Cannot delete built-in presets"
            )

        cursor.execute("DELETE FROM audio_presets WHERE id = ?", (preset_id,))
        conn.commit()

        return {"ok": True, "message": "Preset deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(
            status_code=500, detail=f"Failed to delete preset: {str(e)}"
        )
    finally:
        conn.close()
