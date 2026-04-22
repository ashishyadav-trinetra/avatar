"""Health check endpoint."""

from fastapi import APIRouter

router = APIRouter()
_engine = None


def set_engine(e):
    global _engine
    _engine = e


@router.get("/health")
async def health():
    ready = _engine is not None and _engine.is_ready()
    return {
        "status": "ok" if ready else "initializing",
        "service": "coefficient-engine",
        "ready": ready,
        "active_sessions": len(_engine._sessions) if _engine else 0,
    }
