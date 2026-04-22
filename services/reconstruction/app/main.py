"""
Reconstruction service — FastAPI application.
Handles photo upload, quality gating, and 3D avatar reconstruction.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import health, reconstruct
from .core.config import config
from .core.pipeline import ReconstructionPipeline

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

pipeline = ReconstructionPipeline()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize pipeline on startup, cleanup on shutdown."""
    logger.info("Starting reconstruction service...")
    await pipeline.initialize()

    # Wire pipeline into route handlers
    reconstruct.set_pipeline(pipeline)
    health.set_pipeline(pipeline)

    logger.info("Reconstruction service ready")
    yield

    logger.info("Shutting down reconstruction service...")
    await pipeline.shutdown()


app = FastAPI(
    title="Avatar Reconstruction Service",
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
app.include_router(reconstruct.router)
