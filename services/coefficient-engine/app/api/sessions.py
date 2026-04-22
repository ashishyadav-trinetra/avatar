"""
Session management API — create/destroy coefficient streaming sessions.
"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()

_engine = None


def set_engine(e):
    global _engine
    _engine = e


class CreateSessionRequest(BaseModel):
    session_id: str


class CreateSessionResponse(BaseModel):
    session_id: str
    ws_url: str
    status: str


@router.post("/sessions", response_model=CreateSessionResponse)
async def create_session(req: CreateSessionRequest):
    """Create a new coefficient streaming session."""
    if not _engine or not _engine.is_ready():
        raise HTTPException(503, "Engine not ready")

    session = await _engine.create_session(req.session_id)
    return CreateSessionResponse(
        session_id=session.session_id,
        ws_url=f"/coefficients/ws/{session.session_id}",
        status="active",
    )


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Stop and remove a coefficient streaming session."""
    if not _engine:
        raise HTTPException(503, "Engine not ready")

    await _engine.remove_session(session_id)
    return {"session_id": session_id, "status": "removed"}
