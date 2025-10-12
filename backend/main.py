import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_database
from app.job_worker import init_worker, start_worker, stop_worker
from app.jobs import router as jobs_router
from app.routes.audio import router as audio_router
from app.routes.files import router as file_router
from app.routes.health import router as health_router
from app.routes.mediainfo import router as mi_router
from app.routes.presets.audio import router as audio_presets_router
from app.routes.presets.video import router as video_presets_router
from app.routes.vs import router as vs_router


class EndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Check if the log message contains the specific endpoint path
        # For example, to filter out logs for "/health" endpoint
        return record.getMessage().find("/api/jobs/list") == -1


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database and start job worker on startup.

    Note: Worker runs in manual mode - jobs must be explicitly started
    via the API (Start Next button). Worker only processes jobs with
    status='running'.
    """

    # TODO: get dynamically
    vs_pipe_path = r"C:\VapourSynth\VSPipe.exe"
    x264_path = r"D:\programming\video-forge\apps\x264.exe"

    print("🔧 Initializing database...", flush=True)
    init_database()
    print("✅ Database initialized successfully", flush=True)
    # TODO: put back later - FILTER THIS OUT FOR NOW
    logging.getLogger("uvicorn.access").addFilter(EndpointFilter())

    print("🔧 Initializing job worker (manual mode)...", flush=True)
    init_worker(vspipe_path=vs_pipe_path, x264_path=x264_path)
    start_worker()
    print("✅ Job worker started successfully", flush=True)

    yield

    # Cleanup on shutdown
    print("🛑 Shutting down job worker...", flush=True)
    stop_worker()
    print("✅ Job worker stopped", flush=True)


app = FastAPI(lifespan=lifespan)

# routers
app.include_router(health_router, prefix=settings.API_PREFIX)
app.include_router(audio_router, prefix=settings.API_PREFIX)
app.include_router(file_router, prefix=settings.API_PREFIX)
app.include_router(vs_router, prefix=settings.API_PREFIX)
app.include_router(video_presets_router, prefix=settings.API_PREFIX)
app.include_router(audio_presets_router, prefix=settings.API_PREFIX)
app.include_router(jobs_router, prefix=settings.API_PREFIX)
app.include_router(mi_router, prefix=settings.API_PREFIX)

# update middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
