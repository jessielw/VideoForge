

from fastapi import APIRouter

router = APIRouter(tags=["mediainfo"])


@router.get("/health")
async def health():
    return {"status": "ok"}

