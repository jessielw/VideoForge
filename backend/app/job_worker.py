"""
Job Worker - Background service that processes the job queue

This module runs as a background thread monitoring the job queue
and executing jobs using the JobExecutor.
"""

import threading
from typing import Optional

from .database import get_db_connection
from .job_executor import JobExecutor


class JobWorker:
    """Background worker that processes jobs from the queue."""
    
    def __init__(
        self,
        vspipe_path: str = r"D:\programming\video-forge\apps\VapourSynth\VSPipe.exe",
        x264_path: str = r"D:\programming\video-forge\apps\x264.exe",
        ffmpeg_path: str = "ffmpeg",
        mkvmerge_path: str = "mkvmerge",
        check_interval: float = 2.0,
    ):
        """Initialize the job worker.
        
        Args:
            vspipe_path: Path to vspipe executable
            x264_path: Path to x264 executable
            ffmpeg_path: Path to ffmpeg executable (or command if in PATH)
            mkvmerge_path: Path to mkvmerge executable (or command if in PATH)
            check_interval: How often to check for queued jobs (seconds)
        """
        self.vspipe_path = vspipe_path
        self.x264_path = x264_path
        self.ffmpeg_path = ffmpeg_path
        self.mkvmerge_path = mkvmerge_path
        self.check_interval = check_interval
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.current_executor: Optional[JobExecutor] = None
        self.current_job_id: Optional[int] = None
        
    def start(self):
        """Start the worker thread."""
        if self.running:
            print("⚠️ Job worker is already running", flush=True)
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.thread.start()
        print("✅ Job worker started", flush=True)
    
    def stop(self):
        """Stop the worker thread."""
        if not self.running:
            return
        
        print("🛑 Stopping job worker...", flush=True)
        self.running = False
        
        # Cancel current job if any
        if self.current_executor:
            print(f"⚠️ Cancelling job {self.current_job_id}...", flush=True)
            self.current_executor.cancel()
        
        if self.thread:
            self.thread.join(timeout=5.0)
        
        print("✅ Job worker stopped", flush=True)
    
    def _worker_loop(self):
        """Main worker loop - runs in background thread.
        
        Note: This worker does NOT auto-start jobs. Jobs must be manually
        started via the API. The worker only executes jobs that are in
        'running' status.
        """
        print("🔄 Job worker loop started (manual start mode)", flush=True)
        
        while self.running:
            try:
                # Check for running job (manually started via API)
                job_id = self._get_running_job()
                
                if job_id:
                    self._execute_job(job_id)
                else:
                    # No jobs running, wait before checking again
                    threading.Event().wait(self.check_interval)
                    
            except Exception as e:
                print(f"❌ Error in job worker loop: {e}", flush=True)
                import traceback
                traceback.print_exc()
                # Wait before retrying
                threading.Event().wait(self.check_interval)
    
    def _get_running_job(self) -> Optional[int]:
        """Get a job that has been manually set to 'running' status.
        
        Returns:
            Job ID if found, None otherwise
        """
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Get the first running job (should only be one at a time)
            cursor.execute(
                """
                SELECT id FROM jobs
                WHERE status = 'running'
                LIMIT 1
                """
            )
            
            row = cursor.fetchone()
            return row[0] if row else None
            
        finally:
            conn.close()
    
    def get_next_enabled_job(self) -> Optional[int]:
        """Get the next enabled, queued job in position order.
        
        This is used when manually starting jobs to find the next job
        that should be processed.
        
        Returns:
            Job ID if found, None otherwise
        """
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Get first enabled queued job in position order
            cursor.execute(
                """
                SELECT id FROM jobs
                WHERE status = 'queued' AND enabled = 1
                ORDER BY position ASC
                LIMIT 1
                """
            )
            
            row = cursor.fetchone()
            return row[0] if row else None
            
        finally:
            conn.close()
    
    def _execute_job(self, job_id: int):
        """Execute a job.
        
        Args:
            job_id: ID of the job to execute
        """
        print(f"\n{'='*60}")
        print(f"🚀 Job worker starting job {job_id}")
        print(f"{'='*60}\n")
        
        try:
            # Create executor
            self.current_executor = JobExecutor(
                job_id=job_id,
                vspipe_path=self.vspipe_path,
                x264_path=self.x264_path,
                ffmpeg_path=self.ffmpeg_path,
                mkvmerge_path=self.mkvmerge_path,
            )
            self.current_job_id = job_id
            
            # Run the job (this blocks until completion)
            self.current_executor.run()
            
            print(f"\n✅ Job {job_id} completed successfully\n")
            
        except Exception as e:
            print(f"\n❌ Job {job_id} failed: {e}\n")
            import traceback
            traceback.print_exc()
            
        finally:
            self.current_executor = None
            self.current_job_id = None
    
    def cancel_job(self, job_id: int) -> bool:
        """Cancel a specific job if it's currently running.
        
        Args:
            job_id: ID of the job to cancel
            
        Returns:
            True if job was cancelled, False if not currently running
        """
        if self.current_job_id == job_id and self.current_executor:
            print(f"⚠️ Cancelling job {job_id}...", flush=True)
            self.current_executor.cancel()
            return True
        return False


# Global worker instance
_worker: Optional[JobWorker] = None


def get_worker() -> JobWorker:
    """Get the global worker instance."""
    global _worker
    if _worker is None:
        raise RuntimeError("Job worker not initialized")
    return _worker


def init_worker(
    vspipe_path: str = r"D:\programming\video-forge\apps\VapourSynth\VSPipe.exe",
    x264_path: str = r"D:\programming\video-forge\apps\x264.exe",
    ffmpeg_path: str = "ffmpeg",
    mkvmerge_path: str = "mkvmerge",
) -> JobWorker:
    """Initialize the global worker instance."""
    global _worker
    if _worker is not None:
        print("⚠️ Job worker already initialized", flush=True)
        return _worker
    
    _worker = JobWorker(
        vspipe_path=vspipe_path,
        x264_path=x264_path,
        ffmpeg_path=ffmpeg_path,
        mkvmerge_path=mkvmerge_path,
    )
    return _worker


def start_worker():
    """Start the global worker."""
    worker = get_worker()
    worker.start()


def stop_worker():
    """Stop the global worker."""
    global _worker
    if _worker:
        _worker.stop()
        _worker = None
