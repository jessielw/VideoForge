from fastapi import FastAPI

app = FastAPI()


@app.get("/api/health")
async def health():
    """Minimal health endpoint for startup checks."""
    return {"status": "ok"}
