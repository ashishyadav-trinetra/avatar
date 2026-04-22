"""Health check endpoint."""

from fastapi import APIRouter

router = APIRouter()

_pipeline = None


def set_pipeline(p):
    global _pipeline
    _pipeline = p


@router.get("/health")
async def health():
    ready = _pipeline is not None and _pipeline.is_ready()
    return {
        "status": "ok" if ready else "initializing",
        "service": "reconstruction",
        "ready": ready,
    }
