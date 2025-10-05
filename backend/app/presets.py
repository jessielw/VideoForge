"""
API routes for encoder preset management
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .database import get_db

router = APIRouter(prefix="/api/presets", tags=["presets"])


class EncoderPresetCreate(BaseModel):
    """Request model for creating a preset."""
    name: str
    description: Optional[str] = None
    encoder: str
    rate_control_mode: str
    crf: Optional[int] = None
    target_bitrate: Optional[int] = None
    preset: Optional[str] = None
    tune: Optional[str] = None
    custom_args: Optional[str] = None


class EncoderPresetResponse(BaseModel):
    """Response model for a preset."""
    id: str
    name: str
    description: Optional[str]
    encoder: str
    rate_control_mode: str
    crf: Optional[int]
    target_bitrate: Optional[int]
    preset: Optional[str]
    tune: Optional[str]
    custom_args: Optional[str]
    is_builtin: bool
    created_at: str
    updated_at: str


@router.get("", response_model=List[EncoderPresetResponse])
async def get_presets(encoder: Optional[str] = None):
    """Get all encoder presets, optionally filtered by encoder type."""
    with get_db() as conn:
        cursor = conn.cursor()
        
        if encoder:
            cursor.execute("""
                SELECT * FROM encoder_presets 
                WHERE encoder = ?
                ORDER BY is_builtin DESC, created_at DESC
            """, (encoder,))
        else:
            cursor.execute("""
                SELECT * FROM encoder_presets 
                ORDER BY is_builtin DESC, created_at DESC
            """)
        
        rows = cursor.fetchall()
        
        presets = []
        for row in rows:
            presets.append({
                'id': row['id'],
                'name': row['name'],
                'description': row['description'],
                'encoder': row['encoder'],
                'rate_control_mode': row['rate_control_mode'],
                'crf': row['crf'],
                'target_bitrate': row['target_bitrate'],
                'preset': row['preset'],
                'tune': row['tune'],
                'custom_args': row['custom_args'],
                'is_builtin': bool(row['is_builtin']),
                'created_at': row['created_at'],
                'updated_at': row['updated_at'],
            })
        
        return presets


@router.get("/{preset_id}", response_model=EncoderPresetResponse)
async def get_preset(preset_id: str):
    """Get a specific encoder preset by ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM encoder_presets WHERE id = ?", (preset_id,))
        row = cursor.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Preset not found")
        
        return {
            'id': row['id'],
            'name': row['name'],
            'description': row['description'],
            'encoder': row['encoder'],
            'rate_control_mode': row['rate_control_mode'],
            'crf': row['crf'],
            'target_bitrate': row['target_bitrate'],
            'preset': row['preset'],
            'tune': row['tune'],
            'custom_args': row['custom_args'],
            'is_builtin': bool(row['is_builtin']),
            'created_at': row['created_at'],
            'updated_at': row['updated_at'],
        }


@router.post("", response_model=EncoderPresetResponse)
async def create_preset(preset: EncoderPresetCreate):
    """Create a new custom encoder preset."""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Generate unique ID
        import random
        preset_id = f"custom-{int(datetime.utcnow().timestamp())}-{random.randint(1000, 9999)}"
        now = datetime.utcnow().isoformat()
        
        cursor.execute("""
            INSERT INTO encoder_presets 
            (id, name, description, encoder, rate_control_mode, crf, target_bitrate,
             preset, tune, custom_args, is_builtin, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
        """, (
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
        ))
        
        conn.commit()
        
        # Fetch and return the created preset
        cursor.execute("SELECT * FROM encoder_presets WHERE id = ?", (preset_id,))
        row = cursor.fetchone()
        
        return {
            'id': row['id'],
            'name': row['name'],
            'description': row['description'],
            'encoder': row['encoder'],
            'rate_control_mode': row['rate_control_mode'],
            'crf': row['crf'],
            'target_bitrate': row['target_bitrate'],
            'preset': row['preset'],
            'tune': row['tune'],
            'custom_args': row['custom_args'],
            'is_builtin': bool(row['is_builtin']),
            'created_at': row['created_at'],
            'updated_at': row['updated_at'],
        }


@router.delete("/{preset_id}")
async def delete_preset(preset_id: str):
    """Delete a custom encoder preset (cannot delete built-in presets)."""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Check if preset exists and is not built-in
        cursor.execute("SELECT is_builtin FROM encoder_presets WHERE id = ?", (preset_id,))
        row = cursor.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Preset not found")
        
        if row['is_builtin']:
            raise HTTPException(status_code=403, detail="Cannot delete built-in preset")
        
        cursor.execute("DELETE FROM encoder_presets WHERE id = ?", (preset_id,))
        conn.commit()
        
        return {"ok": True, "message": "Preset deleted successfully"}
