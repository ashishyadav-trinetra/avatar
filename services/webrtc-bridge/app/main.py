"""
WebRTC Bridge — Main Application
Handles WebRTC signaling (offer/answer) and streams
avatar frames from the avatar-engine into the browser.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.config import settings
from app.signaling import router as signaling_router
from app.health import router as health_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"WebRTC Bridge starting — STUN: {settings.STUN_SERVER}")
    yield
    logger.info("WebRTC Bridge shutting down")


app = FastAPI(title="WebRTC Bridge", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(signaling_router, prefix="/webrtc")
