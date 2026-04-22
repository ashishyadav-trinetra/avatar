"""
API Gateway — Session Orchestration for FLAME Avatar Pipeline
──────────────────────────────────────────────────────────────
Coordinates across reconstruction and coefficient-engine services.

Endpoints:
  POST /api/session/start     — upload photos, reconstruct avatar, start coeff session
  POST /api/session/validate  — validate photos without reconstruction
  GET  /api/session/{id}      — session status
  DELETE /api/session/{id}    — teardown
  GET  /api/avatar/{id}/glb   — download reconstructed GLB
  GET  /health
"""

import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from typing import Optional

import aiohttp
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# ── Config ────────────────────────────────────────────────────
class Settings(BaseSettings):
    REDIS_URL: str              = Field(default="redis://localhost:6379")
    LIVEKIT_URL: str            = Field(default="wss://localhost:7880")
    LIVEKIT_API_KEY: str        = Field(default="devkey")
    LIVEKIT_API_SECRET: str     = Field(default="devsecret")
    RECONSTRUCTION_URL: str     = Field(default="http://reconstruction:8002")
    COEFFICIENT_ENGINE_URL: str = Field(default="http://coefficient-engine:8003")
    GLB_OUTPUT_DIR: str         = Field(default="/app/outputs")
    LOG_LEVEL: str              = Field(default="info")

    class Config:
        env_file = ".env"

settings = Settings()


# ── Response models ──────────────────────────────────────────
class StartSessionResponse(BaseModel):
    session_id: str
    livekit_token: str
    livekit_url: str
    glb_url: str
    coefficient_ws_url: str
    reconstruction_time_ms: int
    model: str
    status: str


class ValidateResponse(BaseModel):
    all_passed: bool
    results: dict


class SessionStatusResponse(BaseModel):
    session_id: str
    status: str
    avatar_ready: bool


# ── LiveKit token generation ─────────────────────────────────
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


# ── HTTP client ──────────────────────────────────────────────
_http_session: Optional[aiohttp.ClientSession] = None

async def get_http():
    global _http_session
    if _http_session is None or _http_session.closed:
        _http_session = aiohttp.ClientSession()
    return _http_session


# ── App ──────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("API Gateway starting (FLAME pipeline)")
    yield
    if _http_session and not _http_session.closed:
        await _http_session.close()
    logger.info("API Gateway shutdown")


app = FastAPI(title="Avatar API Gateway", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Routes ───────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "api-gateway"}


@app.post("/api/session/start", response_model=StartSessionResponse)
async def start_session(
    front_neutral: UploadFile = File(...),
    left_quarter: UploadFile = File(None),
    right_quarter: UploadFile = File(None),
    front_mouth_open: UploadFile = File(None),
    front_smile: UploadFile = File(None),
    skip_quality_check: bool = Form(False),
):
    """
    Full session bootstrap:
    1. Forward photos to reconstruction service → GLB with morph targets
    2. Create coefficient streaming session
    3. Generate LiveKit token for voice pipeline
    4. Return everything the frontend needs
    """
    session_id = str(uuid.uuid4())
    http = await get_http()

    # ── Step 1: Reconstruct avatar ───────────────────────────
    logger.info(f"[{session_id}] Starting reconstruction...")

    form = aiohttp.FormData()
    form.add_field("session_id", session_id)
    form.add_field("skip_quality_check", str(skip_quality_check).lower())

    # Forward all uploaded photos
    uploads = {
        "front_neutral": front_neutral,
        "left_quarter": left_quarter,
        "right_quarter": right_quarter,
        "front_mouth_open": front_mouth_open,
        "front_smile": front_smile,
    }
    for name, upload in uploads.items():
        if upload is not None:
            data = await upload.read()
            if data:
                form.add_field(
                    name,
                    data,
                    filename=upload.filename or f"{name}.jpg",
                    content_type=upload.content_type or "image/jpeg",
                )

    try:
        async with http.post(
            f"{settings.RECONSTRUCTION_URL}/reconstruct",
            data=form,
            timeout=aiohttp.ClientTimeout(total=60),
        ) as resp:
            if resp.status != 200:
                error = await resp.text()
                logger.error(f"[{session_id}] Reconstruction failed: {error}")
                raise HTTPException(resp.status, f"Reconstruction failed: {error}")
            recon_data = await resp.json()
    except aiohttp.ClientError as e:
        logger.error(f"[{session_id}] Reconstruction service unreachable: {e}")
        raise HTTPException(503, f"Reconstruction service unreachable: {e}")

    logger.info(
        f"[{session_id}] Reconstruction complete: "
        f"{recon_data['model']}, {recon_data['reconstruction_time_ms']}ms"
    )

    # ── Step 2: Create coefficient session ───────────────────
    try:
        async with http.post(
            f"{settings.COEFFICIENT_ENGINE_URL}/sessions",
            json={"session_id": session_id},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status != 200:
                error = await resp.text()
                raise HTTPException(resp.status, f"Coefficient session failed: {error}")
            coeff_data = await resp.json()
    except aiohttp.ClientError as e:
        raise HTTPException(503, f"Coefficient engine unreachable: {e}")

    logger.info(f"[{session_id}] Coefficient session created")

    # ── Step 3: Generate LiveKit token ───────────────────────
    livekit_token = generate_livekit_token(session_id)

    return StartSessionResponse(
        session_id=session_id,
        livekit_token=livekit_token,
        livekit_url=settings.LIVEKIT_URL,
        glb_url=f"/api/avatar/{session_id}/glb",
        coefficient_ws_url=f"ws://localhost:8003/coefficients/ws/{session_id}",
        reconstruction_time_ms=recon_data["reconstruction_time_ms"],
        model=recon_data["model"],
        status="ready",
    )


@app.post("/api/session/validate", response_model=ValidateResponse)
async def validate_photos(
    front_neutral: UploadFile = File(None),
    left_quarter: UploadFile = File(None),
    right_quarter: UploadFile = File(None),
    front_mouth_open: UploadFile = File(None),
    front_smile: UploadFile = File(None),
):
    """Validate photos against quality gates without reconstruction."""
    http = await get_http()

    form = aiohttp.FormData()
    uploads = {
        "front_neutral": front_neutral,
        "left_quarter": left_quarter,
        "right_quarter": right_quarter,
        "front_mouth_open": front_mouth_open,
        "front_smile": front_smile,
    }
    for name, upload in uploads.items():
        if upload is not None:
            data = await upload.read()
            if data:
                form.add_field(name, data, filename=f"{name}.jpg", content_type="image/jpeg")

    try:
        async with http.post(
            f"{settings.RECONSTRUCTION_URL}/validate",
            data=form,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status != 200:
                error = await resp.text()
                raise HTTPException(resp.status, error)
            return await resp.json()
    except aiohttp.ClientError as e:
        raise HTTPException(503, f"Reconstruction service unreachable: {e}")


@app.get("/api/avatar/{session_id}/glb")
async def get_avatar_glb(session_id: str):
    """Serve the reconstructed GLB file."""
    glb_path = os.path.join(settings.GLB_OUTPUT_DIR, f"{session_id}.glb")
    if not os.path.exists(glb_path):
        raise HTTPException(404, "Avatar GLB not found")
    return FileResponse(
        glb_path,
        media_type="model/gltf-binary",
        filename=f"avatar_{session_id}.glb",
    )


@app.delete("/api/session/{session_id}")
async def end_session(session_id: str):
    """Teardown a session: stop coefficient streaming."""
    http = await get_http()

    # Stop coefficient session
    try:
        async with http.delete(
            f"{settings.COEFFICIENT_ENGINE_URL}/sessions/{session_id}",
            timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            pass
    except Exception as e:
        logger.warning(f"[{session_id}] Error stopping coefficient session: {e}")

    # Clean up GLB file
    glb_path = os.path.join(settings.GLB_OUTPUT_DIR, f"{session_id}.glb")
    if os.path.exists(glb_path):
        try:
            os.remove(glb_path)
        except Exception:
            pass

    return {"session_id": session_id, "status": "ended"}
