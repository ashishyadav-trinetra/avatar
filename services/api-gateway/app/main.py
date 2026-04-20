"""
API Gateway — Main Application
────────────────────────────────
Single entry point for the React frontend.
Handles:
  POST /api/session/start   — upload photo, create avatar + LiveKit room
  GET  /api/session/{id}    — session status
  DELETE /api/session/{id}  — teardown
  GET  /api/livekit/token   — generate LiveKit JWT for browser
  GET  /health
"""
import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from typing import Optional

import aiohttp
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from pydantic import Field


# ── Config ────────────────────────────────────────────────────
class Settings(BaseSettings):
    REDIS_URL: str              = Field(default="redis://localhost:6379")
    LIVEKIT_URL: str            = Field(...)
    LIVEKIT_API_KEY: str        = Field(...)
    LIVEKIT_API_SECRET: str     = Field(...)
    WEBRTC_BRIDGE_URL: str      = Field(default="http://webrtc-bridge:8002")
    AVATAR_ENGINE_URL: str      = Field(default="http://avatar-engine:8001")
    UPLOAD_DIR: str             = Field(default="/tmp/uploads")
    LOG_LEVEL: str              = Field(default="info")

    class Config:
        env_file = ".env"

settings = Settings()
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)


# ── Pydantic models ───────────────────────────────────────────
class StartSessionResponse(BaseModel):
    session_id: str
    livekit_token: str
    livekit_url: str
    webrtc_offer_url: str
    status: str


class SessionStatusResponse(BaseModel):
    session_id: str
    status: str
    avatar_ready: bool


# ── LiveKit token generation ──────────────────────────────────
def generate_livekit_token(session_id: str, identity: str = "user") -> str:
    """Generate a LiveKit JWT for the browser to join the avatar room."""
    from livekit.api import AccessToken, VideoGrants
    token = (
        AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
        .with_identity(identity)
        .with_name(f"User-{identity}")
        .with_grants(
            VideoGrants(
                room_join=True,
                room=f"avatar-{session_id}",
                can_publish=True,
                can_subscribe=True,
            )
        )
        .to_jwt()
    )
    return token


# ── HTTP client helper ────────────────────────────────────────
_http_session: Optional[aiohttp.ClientSession] = None

async def get_http():
    global _http_session
    if _http_session is None or _http_session.closed:
        _http_session = aiohttp.ClientSession()
    return _http_session


# ── App ───────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("API Gateway starting")
    yield
    if _http_session and not _http_session.closed:
        await _http_session.close()
    logger.info("API Gateway shutdown")


app = FastAPI(title="Avatar API Gateway", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Routes ────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "service": "api-gateway"}


@app.post("/api/session/start", response_model=StartSessionResponse)
async def start_session(photo: UploadFile = File(...)):
    """
    Full session bootstrap:
    1. Forward photo to avatar-engine → get session_id
    2. Generate LiveKit token for browser
    3. Return everything the browser needs
    """
    http = await get_http()

    # ── Forward photo to avatar-engine ───────────────────────
    photo_bytes = await photo.read()
    form = aiohttp.FormData()
    form.add_field(
        "photo",
        photo_bytes,
        filename=photo.filename or "avatar.jpg",
        content_type=photo.content_type or "image/jpeg",
    )

    async with http.post(
        f"{settings.AVATAR_ENGINE_URL}/avatar/session",
        data=form,
    ) as resp:
        if resp.status != 200:
            body = await resp.text()
            raise HTTPException(502, f"Avatar engine error: {body}")
        engine_data = await resp.json()

    session_id = engine_data["session_id"]
    logger.info(f"Avatar engine session created: {session_id}")

    # ── Generate LiveKit token ────────────────────────────────
    try:
        lk_token = generate_livekit_token(session_id)
    except Exception as e:
        raise HTTPException(500, f"LiveKit token error: {e}")

    return StartSessionResponse(
        session_id=session_id,
        livekit_token=lk_token,
        livekit_url=settings.LIVEKIT_URL,
        webrtc_offer_url=f"{settings.WEBRTC_BRIDGE_URL}/webrtc/offer/{session_id}",
        status="ready",
    )


@app.delete("/api/session/{session_id}")
async def end_session(session_id: str):
    """Tear down avatar engine session + WebRTC peer connection."""
    http = await get_http()

    results = await asyncio.gather(
        http.delete(f"{settings.AVATAR_ENGINE_URL}/avatar/session/{session_id}"),
        http.delete(f"{settings.WEBRTC_BRIDGE_URL}/webrtc/session/{session_id}"),
        return_exceptions=True,
    )

    errors = [str(r) for r in results if isinstance(r, Exception)]
    if errors:
        logger.warning(f"Session teardown errors: {errors}")

    return {"status": "ended", "session_id": session_id}


@app.get("/api/session/{session_id}/status", response_model=SessionStatusResponse)
async def session_status(session_id: str):
    http = await get_http()
    try:
        async with http.get(f"{settings.AVATAR_ENGINE_URL}/health") as r:
            engine_ok = r.status == 200
    except Exception:
        engine_ok = False

    return SessionStatusResponse(
        session_id=session_id,
        status="active" if engine_ok else "degraded",
        avatar_ready=engine_ok,
    )


@app.get("/api/livekit/token")
async def livekit_token(session_id: str, identity: Optional[str] = "user"):
    """Generate a fresh LiveKit token (for reconnects)."""
    try:
        token = generate_livekit_token(session_id, identity)
        return {"token": token, "url": settings.LIVEKIT_URL}
    except Exception as e:
        raise HTTPException(500, str(e))
