"""
Coefficient Engine — FastAPI application.
Streams FLAME coefficients (lip-sync + behavior) to frontend via WebSocket.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import health, sessions, stream
from .core.config import config
from .core.engine import CoefficientEngine

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

engine = CoefficientEngine()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize engine on startup, cleanup on shutdown."""
    logger.info("Starting coefficient engine...")
    await engine.initialize()

    # Wire engine into handlers
    health.set_engine(engine)
    sessions.set_engine(engine)
    stream.set_sessions(engine._sessions)

    logger.info("Coefficient engine ready")
    yield

    logger.info("Shutting down coefficient engine...")
    await engine.shutdown()


app = FastAPI(
    title="Avatar Coefficient Engine",
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
app.include_router(sessions.router)
app.include_router(stream.router)
