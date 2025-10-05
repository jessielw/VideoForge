"""
Database schema and connection management for Video-Forge
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

DB_PATH = Path(__file__).parent.parent / "data.db"


def get_db_connection() -> sqlite3.Connection:
    """Get a database connection (caller must close it)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Enable column access by name
    return conn


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Context manager for database connections."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Enable column access by name
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_database():
    """Initialize database with schema."""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Drop existing tables
        cursor.execute("DROP TABLE IF EXISTS jobs")
        cursor.execute("DROP TABLE IF EXISTS encoder_presets")
        cursor.execute("DROP TABLE IF EXISTS source_cache")
        
        # Encoder Presets Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS encoder_presets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                encoder TEXT NOT NULL,
                rate_control_mode TEXT NOT NULL,
                crf INTEGER,
                target_bitrate INTEGER,
                preset TEXT,
                tune TEXT,
                custom_args TEXT,
                is_builtin INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        
        # Create index on encoder type for faster queries
        cursor.execute("""
            CREATE INDEX idx_encoder_presets_encoder 
            ON encoder_presets(encoder)
        """)
        
        # Audio Presets Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audio_presets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                config TEXT NOT NULL,
                is_builtin INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        
        # Create index on audio preset name
        # cursor.execute("""
        #     CREATE INDEX idx_audio_presets_name 
        #     ON audio_presets(name)
        # """)
        
        # Jobs Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                status TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                enabled INTEGER NOT NULL DEFAULT 1,
                source_path TEXT NOT NULL,
                output_path TEXT NOT NULL,
                
                -- Configuration stored as JSON
                video_config TEXT,
                audio_config TEXT,
                output_config TEXT,
                
                -- VapourSynth script
                vs_script TEXT,
                
                -- Progress tracking
                progress REAL DEFAULT 0.0,
                current_frame INTEGER,
                total_frames INTEGER,
                fps REAL,
                eta REAL,
                
                -- File sizes
                source_size INTEGER,
                output_size INTEGER,
                
                -- Error handling
                error_message TEXT,
                
                -- Timestamps
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT
            )
        """)
        
        # Create indexes for job queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_jobs_status 
            ON jobs(status)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_jobs_position 
            ON jobs(position)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_jobs_created_at 
            ON jobs(created_at DESC)
        """)
        
        # Source Cache Table (optional - for caching mediainfo results)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS source_cache (
                path TEXT PRIMARY KEY,
                mediainfo_json TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                modified_at TEXT NOT NULL,
                cached_at TEXT NOT NULL
            )
        """)
        
        # Insert built-in encoder presets
        builtin_presets = [
            {
                'id': 'x264-balanced',
                'name': 'Balanced (x264)',
                'description': 'Good quality and reasonable file size',
                'encoder': 'x264',
                'rate_control_mode': 'crf',
                'crf': 23,
                'preset': 'medium',
                'tune': 'none',
            },
            {
                'id': 'x264-quality',
                'name': 'High Quality (x264)',
                'description': 'Maximum quality, larger files',
                'encoder': 'x264',
                'rate_control_mode': 'crf',
                'crf': 18,
                'preset': 'slow',
                'tune': 'none',
            },
            {
                'id': 'x264-fast',
                'name': 'Fast Encode (x264)',
                'description': 'Quick encoding, lower quality',
                'encoder': 'x264',
                'rate_control_mode': 'crf',
                'crf': 26,
                'preset': 'veryfast',
                'tune': 'none',
            },
            {
                'id': 'x265-balanced',
                'name': 'Balanced (x265)',
                'description': 'Good quality with HEVC compression',
                'encoder': 'x265',
                'rate_control_mode': 'crf',
                'crf': 28,
                'preset': 'medium',
                'tune': 'none',
            },
            {
                'id': 'x265-quality',
                'name': 'High Quality (x265)',
                'description': 'Maximum quality HEVC encode',
                'encoder': 'x265',
                'rate_control_mode': 'crf',
                'crf': 22,
                'preset': 'slow',
                'tune': 'none',
            },
        ]
        
        from datetime import datetime
        now = datetime.utcnow().isoformat()
        
        for preset in builtin_presets:
            cursor.execute("""
                INSERT INTO encoder_presets 
                (id, name, description, encoder, rate_control_mode, crf, 
                 preset, tune, custom_args, is_builtin, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """, (
                preset['id'],
                preset['name'],
                preset['description'],
                preset['encoder'],
                preset['rate_control_mode'],
                preset['crf'],
                preset['preset'],
                preset['tune'],
                '',
                now,
                now,
            ))
        
        conn.commit()


if __name__ == "__main__":
    print(f"Initializing database at: {DB_PATH}")
    init_database()
    print("✅ Database initialized successfully!")
