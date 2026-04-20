"""
Avatar Engine — Main FastAPI Application
Handles: photo ingestion, landmark extraction, frame generation pipeline
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.core.config import settings
from app.core.pipeline import AvatarPipeline
from app.api import health, avatar, frames


# ── Global pipeline instance ─────────────────────────────────
pipeline: AvatarPipeline | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: load models. Shutdown: clean up."""
    global pipeline
    logger.info("Avatar Engine starting up...")
    logger.info(f"Device: {settings.DEVICE} | FPS target: {settings.FPS_TARGET}")

    pipeline = AvatarPipeline(settings)
    await pipeline.initialize()
    app.state.pipeline = pipeline

    logger.info("Avatar Engine ready ✓")
    yield

    logger.info("Avatar Engine shutting down...")
    if pipeline:
        await pipeline.cleanup()


# ── App ───────────────────────────────────────────────────────
app = FastAPI(
    title="Avatar Engine",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(avatar.router, prefix="/avatar")
app.include_router(frames.router, prefix="/frames")
