"""
LiveKit Agent — Main Entry Point (LiveKit Agents 1.x)
───────────────────────────────────────────────────────
Uses the modern AgentSession + Agent API.

Pipeline: VAD → STT → LLM → TTS
Additionally:
  - Intercepts TTS audio and publishes raw PCM to Redis
    so coefficient-engine drives lip-sync + behavior layer
  - Classifies LLM responses and publishes motion state to Redis
"""
import asyncio
import logging
from typing import AsyncIterable

import numpy as np
import redis.asyncio as aioredis
from loguru import logger

from livekit import rtc
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    WorkerOptions,
    cli,
    stt as lk_stt,
    tts as lk_tts,
)
from livekit.plugins import openai as lk_openai
from livekit.plugins import silero

from app.config import settings
from app.intent_classifier import classify, MotionState

logging.getLogger("livekit").setLevel(logging.WARNING)

REDIS_CHANNEL_AUDIO  = "avatar:audio:{session_id}"
REDIS_CHANNEL_INTENT = "avatar:intent:{session_id}"


def _build_stt():
    if settings.STT_PROVIDER == "deepgram" and settings.DEEPGRAM_API_KEY:
        from livekit.plugins import deepgram as lk_deepgram
        return lk_deepgram.STT(api_key=settings.DEEPGRAM_API_KEY)
    return lk_openai.STT(model="whisper-1", api_key=settings.OPENAI_API_KEY)


def _build_llm():
    return lk_openai.LLM(
        model=settings.LLM_MODEL,
        api_key=settings.OPENAI_API_KEY,
    )


def _build_tts():
    if settings.TTS_PROVIDER == "elevenlabs" and settings.ELEVENLABS_API_KEY:
        try:
            from livekit.plugins import elevenlabs as lk_elevenlabs
            return lk_elevenlabs.TTS(
                api_key=settings.ELEVENLABS_API_KEY,
                voice_id=settings.ELEVENLABS_VOICE_ID or "21m00Tcm4TlvDq8ikWAM",
            )
        except ImportError:
            logger.warning("ElevenLabs plugin not installed — falling back to OpenAI TTS")
    return lk_openai.TTS(
        model="tts-1",
        voice="nova",
        api_key=settings.OPENAI_API_KEY,
    )


class AvatarAgent(Agent):
    """
    LiveKit Agent 1.x subclass.
    Overrides tts_node to intercept audio chunks and forward
    them to the coefficient-engine via Redis pub/sub.
    """

    def __init__(self, redis: aioredis.Redis, session_id: str):
        super().__init__(instructions=settings.AGENT_SYSTEM_PROMPT)
        self._redis = redis
        self._session_id = session_id
        self._audio_channel = REDIS_CHANNEL_AUDIO.format(session_id=session_id)
        self._intent_channel = REDIS_CHANNEL_INTENT.format(session_id=session_id)

    async def on_enter(self):
        """Called when agent becomes active in session. Send greeting."""
        await asyncio.sleep(0.8)
        await self.session.say(
            "Hello! I'm your AI assistant. How can I help you today?",
            allow_interruptions=True,
        )

    async def tts_node(
        self,
        text: AsyncIterable[str],
        model_settings,
    ) -> AsyncIterable[rtc.AudioFrame]:
        """
        Override TTS node to intercept audio.
        Runs default TTS, then for each AudioFrame:
          1. Yields frame back to LiveKit (so user hears the voice)
          2. Publishes raw PCM to Redis (so coefficient-engine drives lip-sync)
        """
        # Collect text to also classify intent
        collected_text = []

        async def _text_with_capture():
            async for chunk in text:
                collected_text.append(chunk)
                yield chunk

        # Run TTS
        tts = _build_tts()
        async for frame in tts.stream(_text_with_capture(), model_settings):
            # Forward to LiveKit
            yield frame

            # Publish PCM to Redis for coefficient engine
            try:
                # Convert audio frame to float32 PCM
                pcm_data = np.frombuffer(frame.data, dtype=np.int16).astype(np.float32) / 32768.0
                await self._redis.publish(
                    self._audio_channel,
                    pcm_data.tobytes(),
                )
            except Exception as e:
                logger.error(f"Redis audio publish error: {e}")

        # After TTS completes, classify intent and publish
        full_text = "".join(collected_text)
        if full_text.strip():
            intent = classify(full_text)
            try:
                await self._redis.publish(
                    self._intent_channel,
                    intent.value,
                )
            except Exception as e:
                logger.error(f"Redis intent publish error: {e}")


async def entrypoint(ctx: JobContext):
    """
    Entry point for each LiveKit job (one per room/session).
    """
    # Extract session_id from room name: "avatar-{session_id}"
    room_name = ctx.room.name or ""
    if room_name.startswith("avatar-"):
        session_id = room_name[len("avatar-"):]
    else:
        session_id = room_name or "unknown"

    logger.info(f"Agent joining room: {room_name} (session: {session_id})")

    # Connect to Redis
    redis = aioredis.from_url(settings.REDIS_URL, decode_responses=False)
    await redis.ping()
    logger.info("Redis connected")

    # Build the agent
    agent = AvatarAgent(redis=redis, session_id=session_id)

    # Create agent session with pipeline
    session = AgentSession(
        stt=_build_stt(),
        llm=_build_llm(),
        tts=_build_tts(),
        vad=silero.VAD.load(),
    )

    # Start the session
    await session.start(agent=agent, room=ctx.room)

    # Wait for room disconnect
    disconnect_event = asyncio.Event()

    @ctx.room.on("disconnected")
    def on_disconnect():
        logger.info(f"Room disconnected: {room_name}")
        disconnect_event.set()

    await disconnect_event.wait()

    # Cleanup
    await redis.close()
    logger.info(f"Agent cleaned up for session {session_id}")


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
        ),
    )
