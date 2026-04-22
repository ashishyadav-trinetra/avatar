"""
Coefficient Engine — manages lip-sync model, sessions, and Redis audio subscription.
"""

import asyncio
import logging
from typing import Dict, Optional

import numpy as np
import redis.asyncio as aioredis

from .config import config
from .lipsync_base import LipSyncModel
from .session import CoefficientSession

logger = logging.getLogger(__name__)


def _load_lipsync(model_name: str) -> LipSyncModel:
    """Factory: load the configured lip-sync model."""
    if model_name == "stub":
        from .stub_lipsync import StubLipSync
        return StubLipSync()
    elif model_name == "faceformer":
        raise NotImplementedError("FaceFormer not yet implemented — use stub for dev")
    elif model_name == "codetalker":
        raise NotImplementedError("CodeTalker not yet implemented — use stub for dev")
    else:
        raise ValueError(f"Unknown lip-sync model: {model_name}")


class CoefficientEngine:
    """
    Top-level engine. Manages:
    - Lip-sync model (shared across sessions)
    - Per-session coefficient generation
    - Redis subscription for audio from LiveKit agent
    """

    def __init__(self):
        self._lipsync: Optional[LipSyncModel] = None
        self._sessions: Dict[str, CoefficientSession] = {}
        self._redis: Optional[aioredis.Redis] = None
        self._audio_tasks: Dict[str, asyncio.Task] = {}
        self._ready = False

    async def initialize(self):
        """Load models and connect to Redis."""
        logger.info(f"Initializing coefficient engine (lipsync={config.LIPSYNC_MODEL}, device={config.DEVICE})")

        # Load lip-sync model
        self._lipsync = _load_lipsync(config.LIPSYNC_MODEL)
        await self._lipsync.initialize(config.MODEL_DIR, config.DEVICE)

        # Connect to Redis
        self._redis = aioredis.from_url(config.REDIS_URL, decode_responses=False)
        await self._redis.ping()
        logger.info("Connected to Redis")

        self._ready = True
        logger.info("Coefficient engine ready")

    async def shutdown(self):
        """Clean up all sessions and connections."""
        for sid in list(self._sessions.keys()):
            await self.remove_session(sid)

        if self._lipsync:
            await self._lipsync.shutdown()

        if self._redis:
            await self._redis.close()

        self._ready = False

    def is_ready(self) -> bool:
        return self._ready and self._lipsync is not None and self._lipsync.is_ready()

    async def create_session(self, session_id: str) -> CoefficientSession:
        """Create and start a new coefficient session."""
        if session_id in self._sessions:
            logger.warning(f"Session {session_id} already exists, reusing")
            return self._sessions[session_id]

        session = CoefficientSession(
            session_id=session_id,
            lipsync=self._lipsync,
        )
        await session.start()
        self._sessions[session_id] = session

        # Start Redis audio subscriber for this session
        task = asyncio.create_task(self._audio_subscriber(session_id))
        self._audio_tasks[session_id] = task

        logger.info(f"Created session {session_id} (total: {len(self._sessions)})")
        return session

    async def remove_session(self, session_id: str):
        """Stop and remove a session."""
        session = self._sessions.pop(session_id, None)
        if session:
            await session.stop()

        task = self._audio_tasks.pop(session_id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        logger.info(f"Removed session {session_id}")

    async def _audio_subscriber(self, session_id: str):
        """
        Subscribe to Redis channel for TTS audio published by the LiveKit agent.
        Audio format: raw PCM float32 mono 16kHz.
        Channel: avatar:audio:{session_id}
        """
        channel_name = f"avatar:audio:{session_id}"
        logger.info(f"[{session_id}] Subscribing to {channel_name}")

        try:
            pubsub = self._redis.pubsub()
            await pubsub.subscribe(channel_name)

            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue

                session = self._sessions.get(session_id)
                if not session:
                    break

                # Parse PCM data
                data = message["data"]
                if isinstance(data, bytes) and len(data) > 0:
                    pcm = np.frombuffer(data, dtype=np.float32)
                    await session.feed_audio(pcm, 16000)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[{session_id}] Audio subscriber error: {e}")
        finally:
            try:
                await pubsub.unsubscribe(channel_name)
            except Exception:
                pass
