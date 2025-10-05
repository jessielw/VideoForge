"""
Job management routes - Phase 3
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .database import get_db_connection
from .job_worker import get_worker

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


# Pydantic models for job API
class VideoConfigModel(BaseModel):
    encoder: str
    mode: str
    crf: Optional[int] = None
    bitrate: Optional[int] = None
    preset: Optional[str] = None
    tune: Optional[str] = None
    customArgs: Optional[str] = None


class AudioTrackConfig(BaseModel):
    """Configuration for a single audio track."""
    sourceTrack: int  # Which source track to use (0, 1, 2...)
    encoder: str      # "aac", "copy", "opus", etc.
    bitrate: Optional[int] = 192  # kbps (ignored for copy mode)
    language: Optional[str] = None  # Language tag (e.g., "eng", "jpn")
    name: Optional[str] = None      # Track name/title


class AudioConfigModel(BaseModel):
    """Audio processing configuration supporting multiple tracks."""
    tracks: list[AudioTrackConfig] = []  # List of audio tracks to process


class SubtitleTrackConfig(BaseModel):
    """Configuration for a single subtitle track."""
    sourceTrack: int  # Which source track to use (0, 1, 2...)
    mode: str         # "copy", "extract", "burn"
    language: Optional[str] = None  # Language tag (e.g., "eng", "jpn")
    name: Optional[str] = None      # Track name/title
    forced: Optional[bool] = False  # Forced subtitle flag
    default: Optional[bool] = False # Default subtitle flag


class SubtitleConfigModel(BaseModel):
    """Subtitle processing configuration supporting multiple tracks."""
    tracks: list[SubtitleTrackConfig] = []  # List of subtitle tracks to process


class OutputConfigModel(BaseModel):
    outputPath: str
    container: str
    muxer: Optional[str] = None
    fastStart: Optional[bool] = False
    overwrite: Optional[bool] = False


class JobConfigModel(BaseModel):
    sourcePath: str
    vsScript: str
    videoConfig: VideoConfigModel
    audioConfig: AudioConfigModel
    subtitleConfig: Optional[SubtitleConfigModel] = None
    outputConfig: OutputConfigModel
    name: Optional[str] = None


class SubmitJobRequest(BaseModel):
    config: JobConfigModel


@router.post("/submit")
async def submit_job(request: SubmitJobRequest):
    """Submit a new encoding job to the queue."""
    config = request.config

    # Validate paths
    source_path = Path(config.sourcePath)
    if not source_path.exists():
        raise HTTPException(status_code=400, detail="Source file not found")

    # Generate job name if not provided
    job_name = config.name
    if not job_name:
        source_filename = source_path.stem
        job_name = f"{source_filename} → {config.outputConfig.container.upper()}"

    # Store job in database
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Get the max position to add this job at the end
        cursor.execute("SELECT COALESCE(MAX(position), -1) FROM jobs")
        max_position = cursor.fetchone()[0]
        new_position = max_position + 1
        
        cursor.execute(
            """
            INSERT INTO jobs (
                name, status, position, enabled,
                source_path, output_path,
                video_config, audio_config, output_config,
                vs_script,
                progress, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_name,
                "queued",
                new_position,
                1,  # enabled by default
                str(source_path),
                config.outputConfig.outputPath,
                json.dumps(config.videoConfig.dict()),
                json.dumps(config.audioConfig.dict()),
                json.dumps(config.outputConfig.dict()),
                config.vsScript,
                0.0,
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        job_id = cursor.lastrowid

        return {
            "ok": True,
            "jobId": job_id,
            "message": f"Job '{job_name}' added to queue",
        }

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create job: {str(e)}")
    finally:
        conn.close()


@router.get("/list")
async def list_jobs():
    """Get all jobs from the queue."""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT
                id, name, status, position, enabled,
                source_path, output_path,
                video_config, audio_config, output_config,
                vs_script,
                progress, current_frame, total_frames, fps, eta,
                created_at, started_at, completed_at,
                error_message,
                source_size, output_size
            FROM jobs
            ORDER BY position ASC
            """
        )

        rows = cursor.fetchall()
        jobs = []

        for row in rows:
            job = {
                "id": row[0],
                "name": row[1],
                "status": row[2],
                "position": row[3],
                "enabled": bool(row[4]),
                "sourcePath": row[5],
                "outputPath": row[6],
                "videoConfig": json.loads(row[7]) if row[7] else {},
                "audioConfig": json.loads(row[8]) if row[8] else {},
                "outputConfig": json.loads(row[9]) if row[9] else {},
                "vsScript": row[10],
                "progress": row[11] or 0.0,
                "currentFrame": row[12],
                "totalFrames": row[13],
                "fps": row[14],
                "eta": row[15],
                "createdAt": row[16],
                "startedAt": row[17],
                "completedAt": row[18],
                "errorMessage": row[19],
                "sourceSize": row[20],
                "outputSize": row[21],
            }
            jobs.append(job)

        return {"ok": True, "jobs": jobs}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list jobs: {str(e)}")
    finally:
        conn.close()


@router.post("/start-next")
async def start_next_job():
    """Start the next enabled job in the queue.
    
    Only one job can run at a time. If a job is already running,
    this will return an error.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Check if there's already a running job
        cursor.execute("SELECT id, name FROM jobs WHERE status = 'running'")
        running_job = cursor.fetchone()
        
        if running_job:
            return {
                "ok": False, 
                "message": f"Job {running_job[0]} ({running_job[1]}) is already running"
            }
        
        # Get next enabled queued job
        try:
            worker = get_worker()
            next_job_id = worker.get_next_enabled_job()
        except RuntimeError:
            raise HTTPException(status_code=500, detail="Job worker not initialized")
        
        if not next_job_id:
            return {"ok": False, "message": "No enabled jobs in queue"}
        
        # Start that job (atomic check-and-set)
        # Only update if status is still 'queued' and enabled=1
        cursor.execute(
            """
            UPDATE jobs 
            SET status = ?, started_at = ? 
            WHERE id = ? AND status = 'queued' AND enabled = 1
            """,
            ("running", datetime.now().isoformat(), next_job_id),
        )
        
        if cursor.rowcount == 0:
            # Job status or enabled changed between our check and update
            cursor.execute("SELECT status, enabled FROM jobs WHERE id = ?", (next_job_id,))
            current_state = cursor.fetchone()
            if current_state:
                status, enabled = current_state
                if not enabled:
                    return {"ok": False, "message": f"Job {next_job_id} was disabled"}
                else:
                    return {"ok": False, "message": f"Job {next_job_id} status changed to '{status}'"}
            else:
                return {"ok": False, "message": f"Job {next_job_id} not found"}
        
        conn.commit()
        
        return {"ok": True, "jobId": next_job_id, "message": f"Job {next_job_id} started"}
        
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to start next job: {str(e)}")
    finally:
        conn.close()


@router.post("/{job_id}/start")
async def start_job(job_id: int):
    """Start a specific job.
    
    Only one job can run at a time.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Check if there's already a running job
        cursor.execute("SELECT id, name FROM jobs WHERE status = 'running'")
        running_job = cursor.fetchone()
        
        if running_job:
            raise HTTPException(
                status_code=400, 
                detail=f"Job {running_job[0]} ({running_job[1]}) is already running"
            )
        
        # Check if job exists and is queued
        cursor.execute("SELECT status, enabled FROM jobs WHERE id = ?", (job_id,))
        row = cursor.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Job not found")
        
        if row[0] != "queued":
            raise HTTPException(status_code=400, detail=f"Job status is '{row[0]}', cannot start")
        
        if not row[1]:
            raise HTTPException(status_code=400, detail="Job is disabled")
        
        # Update status to running (atomic check-and-set)
        # Only update if status is still 'queued' to prevent race conditions
        cursor.execute(
            """
            UPDATE jobs 
            SET status = ?, started_at = ? 
            WHERE id = ? AND status = 'queued'
            """,
            ("running", datetime.now().isoformat(), job_id),
        )
        
        if cursor.rowcount == 0:
            # Job status changed between our check and update (race condition)
            cursor.execute("SELECT status FROM jobs WHERE id = ?", (job_id,))
            current_status = cursor.fetchone()
            if current_status:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Job status changed to '{current_status[0]}' while trying to start"
                )
            else:
                raise HTTPException(status_code=404, detail="Job not found")
        
        conn.commit()

        return {"ok": True, "message": f"Job {job_id} started"}

    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to start job: {str(e)}")
    finally:
        conn.close()


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: int):
    """Cancel a job."""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Signal the worker to cancel if job is running
        try:
            worker = get_worker()
            worker.cancel_job(job_id)
        except RuntimeError:
            # Worker not initialized (e.g., during testing)
            pass
        
        # Update database
        cursor.execute(
            "UPDATE jobs SET status = ?, completed_at = ? WHERE id = ?",
            ("cancelled", datetime.now().isoformat(), job_id),
        )
        conn.commit()

        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Job not found")

        return {"ok": True, "message": f"Job {job_id} cancelled"}

    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to cancel job: {str(e)}")
    finally:
        conn.close()


@router.delete("/{job_id}")
async def delete_job(job_id: int):
    """Delete a job from the queue."""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Check if job is running
        cursor.execute("SELECT status FROM jobs WHERE id = ?", (job_id,))
        row = cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Job not found")

        if row[0] == "running":
            raise HTTPException(
                status_code=400, detail="Cannot delete a running job. Cancel it first."
            )

        cursor.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        conn.commit()

        return {"ok": True, "message": f"Job {job_id} deleted"}

    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete job: {str(e)}")
    finally:
        conn.close()


class ReorderJobsRequest(BaseModel):
    jobIds: list[int]


@router.post("/reorder")
async def reorder_jobs(request: ReorderJobsRequest):
    """Reorder jobs by updating their positions."""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Update position for each job in the new order
        for idx, job_id in enumerate(request.jobIds):
            cursor.execute(
                "UPDATE jobs SET position = ? WHERE id = ?",
                (idx, job_id)
            )
        
        conn.commit()
        return {"ok": True, "message": "Jobs reordered"}

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to reorder jobs: {str(e)}")
    finally:
        conn.close()


@router.post("/{job_id}/toggle")
async def toggle_job_enabled(job_id: int):
    """Toggle the enabled status of a job."""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Get current enabled status
        cursor.execute("SELECT enabled FROM jobs WHERE id = ?", (job_id,))
        row = cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Job not found")

        # Toggle the status
        new_enabled = 0 if row[0] else 1
        cursor.execute(
            "UPDATE jobs SET enabled = ? WHERE id = ?",
            (new_enabled, job_id)
        )
        conn.commit()

        return {"ok": True, "enabled": bool(new_enabled)}

    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to toggle job: {str(e)}")
    finally:
        conn.close()
