"""
Avatar session management endpoints.
POST /avatar/session   — create session from uploaded photo
DELETE /avatar/session/{session_id}
GET /avatar/sessions   — list active sessions
"""
import io
import numpy as np
import cv2

from fastapi import APIRouter, UploadFile, File, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()


class SessionResponse(BaseModel):
    session_id: str
    status: str
    face_detected: bool


class SessionsResponse(BaseModel):
    sessions: list[str]


@router.post("/session", response_model=SessionResponse)
async def create_session(request: Request, photo: UploadFile = File(...)):
    """
    Upload 1-5 photos (use the first/best one for now).
    Returns a session_id used by WebRTC bridge + LiveKit agent.
    """
    pipeline = request.app.state.pipeline

    # Read + decode image
    contents = await photo.read()
    nparr = np.frombuffer(contents, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if image is None:
        raise HTTPException(400, "Could not decode image")

    # Resize to reasonable input size (512 max dim, preserve aspect)
    h, w = image.shape[:2]
    max_dim = 512
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        image = cv2.resize(image, (int(w * scale), int(h * scale)))

    try:
        session_id = await pipeline.create_session(image)
    except ValueError as e:
        raise HTTPException(422, str(e))

    return SessionResponse(
        session_id=session_id,
        status="ready",
        face_detected=True,
    )


@router.delete("/session/{session_id}")
async def destroy_session(session_id: str, request: Request):
    pipeline = request.app.state.pipeline
    await pipeline.destroy_session(session_id)
    return {"status": "destroyed", "session_id": session_id}


@router.get("/sessions", response_model=SessionsResponse)
async def list_sessions(request: Request):
    pipeline = request.app.state.pipeline
    return SessionsResponse(sessions=list(pipeline._sessions.keys()))


@router.post("/session/{session_id}/motion")
async def set_motion(session_id: str, state: str, request: Request):
    """Manually set motion state for testing."""
    pipeline = request.app.state.pipeline
    session = pipeline._sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    session.set_motion_state(state)
    return {"status": "ok", "state": state}
