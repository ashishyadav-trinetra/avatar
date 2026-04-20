"""
LiveKit Agent — Main Entry Point (LiveKit Agents 1.x)
───────────────────────────────────────────────────────
Uses the modern AgentSession + Agent API.

Pipeline: VAD → STT → LLM → TTS
Additionally:
  - Intercepts TTS audio and publishes raw PCM to Redis
    so avatar-engine drives MuseTalk lip-sync
  - Classifies LLM responses and publishes motion state to Redis
    so avatar-engine expression layer reacts
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
    them to the avatar-engine via Redis pub/sub.
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
          2. Publishes raw PCM to Redis (so avatar-engine drives lip-sync)
        """
        # Collect text to classify intent before audio starts
        text_buffer = []

        async def tee_text():
            async for chunk in text:
                text_buffer.append(chunk)
                yield chunk

        async for audio_frame in Agent.default.tts_node(self, tee_text(), model_settings):
            # Forward to LiveKit WebRTC (user hears the voice)
            yield audio_frame

            # Publish PCM to Redis for avatar lip-sync
            try:
                pcm = np.frombuffer(audio_frame.data, dtype=np.int16).astype(np.float32)
                pcm /= 32768.0  # normalise to [-1, 1]

                # Resample to 16kHz if needed (MuseTalk expects 16kHz)
                if audio_frame.sample_rate != 16000:
                    import librosa
                    pcm = librosa.resample(
                        pcm,
                        orig_sr=audio_frame.sample_rate,
                        target_sr=16000,
                    )

                await self._redis.publish(self._audio_channel, pcm.tobytes())
            except Exception as e:
                logger.warning(f"Audio publish error: {e}")

        # After all audio is done, classify the full response and set motion state
        if text_buffer:
            full_text = "".join(text_buffer)
            motion_state = classify(full_text)
            try:
                await self._redis.publish(self._intent_channel, motion_state.value)
                logger.debug(f"Intent: {motion_state.value} | text: {full_text[:60]}...")
            except Exception as e:
                logger.warning(f"Intent publish error: {e}")


async def entrypoint(ctx: JobContext):
    """
    Called once per LiveKit room.
    Room name convention: avatar-{session_id}
    """
    await ctx.connect()
    logger.info(f"Agent joined room: {ctx.room.name}")

    # Extract session_id from room name
    room_name = ctx.room.name or ""
    session_id = room_name.replace("avatar-", "") if room_name.startswith("avatar-") else room_name
    logger.info(f"Avatar session_id: {session_id}")

    # Connect to Redis
    redis = await aioredis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=False,
    )

    # Build agent + session
    agent = AvatarAgent(redis=redis, session_id=session_id)

    session = AgentSession(
        vad=silero.VAD.load(),
        stt=_build_stt(),
        llm=_build_llm(),
        tts=_build_tts(),
    )

    await session.start(agent=agent, room=ctx.room)

    # Keep alive until room disconnects
    await ctx.wait_for_disconnect()

    logger.info(f"Agent disconnecting from room: {ctx.room.name}")
    await redis.close()


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            api_key=settings.LIVEKIT_API_KEY,
            api_secret=settings.LIVEKIT_API_SECRET,
            ws_url=settings.LIVEKIT_URL,
        )
    )
