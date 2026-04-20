"""
LiveKit Agent — Main Entry Point
──────────────────────────────────
Uses livekit-agents framework to run:
  STT (Deepgram / OpenAI Whisper)
  → LLM (GPT-4o-mini / GPT-4o)
  → TTS (OpenAI / ElevenLabs)

Additionally:
  - Intercepts TTS audio chunks and publishes raw PCM to Redis
    so the avatar-engine can drive MuseTalk lip-sync
  - Classifies each LLM response and publishes motion state to Redis
    so the avatar-engine expression layer reacts
"""
import asyncio
import logging
from typing import Optional

import numpy as np
import redis.asyncio as aioredis
from loguru import logger

from livekit import agents
from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, cli
from livekit.agents.llm import ChatContext, ChatMessage
from livekit.agents.voice_assistant import VoiceAssistant
from livekit.plugins import openai as lk_openai
from livekit.plugins import deepgram as lk_deepgram
from livekit.plugins import silero

from app.config import settings
from app.intent_classifier import classify, MotionState

# Silence loguru + standard logging noise
logging.getLogger("livekit").setLevel(logging.WARNING)

REDIS_CHANNEL_AUDIO  = "avatar:audio:{session_id}"
REDIS_CHANNEL_INTENT = "avatar:intent:{session_id}"


class AvatarAudioInterceptor:
    """
    Wraps a TTS plugin and intercepts the audio output.
    Publishes PCM chunks to Redis for the avatar engine.
    """

    def __init__(self, tts_plugin, redis: aioredis.Redis, session_id: str):
        self._tts     = tts_plugin
        self._redis   = redis
        self._session_id = session_id
        self._audio_channel = REDIS_CHANNEL_AUDIO.format(session_id=session_id)

    async def synthesize(self, text: str):
        """
        Synthesize speech, publishing PCM chunks to Redis
        as they arrive from the TTS stream.
        """
        async with self._tts.stream() as stream:
            await stream.push_text(text)
            await stream.mark_segment_end()

            async for event in stream:
                if not hasattr(event, "data") or event.data is None:
                    continue
                # event.data is a livekit AudioFrame
                audio_frame = event.data
                # Convert to float32 mono PCM at 16kHz for MuseTalk
                pcm = np.frombuffer(audio_frame.data, dtype=np.int16).astype(np.float32)
                pcm /= 32768.0  # normalize to [-1, 1]

                # Resample to 16kHz if needed
                if audio_frame.sample_rate != settings.AUDIO_SAMPLE_RATE:
                    import librosa
                    pcm = librosa.resample(
                        pcm,
                        orig_sr=audio_frame.sample_rate,
                        target_sr=settings.AUDIO_SAMPLE_RATE,
                    )

                await self._redis.publish(self._audio_channel, pcm.tobytes())


def _build_stt():
    if settings.STT_PROVIDER == "deepgram" and settings.DEEPGRAM_API_KEY:
        return lk_deepgram.STT(api_key=settings.DEEPGRAM_API_KEY)
    # Default: OpenAI Whisper via LiveKit
    return lk_openai.STT(model="whisper-1", api_key=settings.OPENAI_API_KEY)


def _build_llm():
    return lk_openai.LLM(
        model=settings.LLM_MODEL,
        api_key=settings.OPENAI_API_KEY,
    )


def _build_tts():
    if settings.TTS_PROVIDER == "elevenlabs" and settings.ELEVENLABS_API_KEY:
        from livekit.plugins import elevenlabs as lk_elevenlabs
        return lk_elevenlabs.TTS(
            api_key=settings.ELEVENLABS_API_KEY,
            voice_id=settings.ELEVENLABS_VOICE_ID or "21m00Tcm4TlvDq8ikWAM",
        )
    # Default: OpenAI TTS
    return lk_openai.TTS(
        model="tts-1",
        voice="nova",
        api_key=settings.OPENAI_API_KEY,
    )


async def entrypoint(ctx: JobContext):
    """
    Called once per LiveKit room that the agent joins.
    The session_id is passed via room metadata.
    """
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    logger.info(f"Agent joined room: {ctx.room.name}")

    # Extract avatar session_id from room metadata
    # Convention: room name = "avatar-{session_id}"
    # Or set via room metadata
    room_meta = ctx.room.metadata or ""
    session_id = room_meta if room_meta else ctx.room.name.replace("avatar-", "")
    logger.info(f"Avatar session_id: {session_id}")

    # Redis connection
    redis = await aioredis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=False,
    )
    intent_channel = REDIS_CHANNEL_INTENT.format(session_id=session_id)

    # Build plugins
    stt = _build_stt()
    llm = _build_llm()
    tts = _build_tts()
    vad = silero.VAD.load()

    # Initial chat context (system prompt)
    initial_ctx = ChatContext(
        messages=[
            ChatMessage(
                role="system",
                content=settings.AGENT_SYSTEM_PROMPT,
            )
        ]
    )

    # ── Custom TTS wrapper that intercepts audio for avatar ───
    audio_interceptor = AvatarAudioInterceptor(tts, redis, session_id)

    async def on_llm_response(text: str):
        """
        Called when LLM response text is ready (before TTS starts).
        1. Classify intent → publish motion state
        2. Synthesize + publish audio PCM
        """
        # Publish motion state immediately (async, no delay)
        motion_state = classify(text)
        await redis.publish(intent_channel, motion_state.value)
        logger.debug(f"Intent: {motion_state.value} for: {text[:60]}...")

        # TTS → PCM → Redis (streaming)
        await audio_interceptor.synthesize(text)

    # ── Voice Assistant ───────────────────────────────────────
    assistant = VoiceAssistant(
        vad=vad,
        stt=stt,
        llm=llm,
        tts=tts,
        chat_ctx=initial_ctx,
        interrupt_speech_duration=0.5,
        interrupt_min_words=2,
        allow_interruptions=True,
    )

    # Hook into assistant events to intercept LLM output
    @assistant.on("agent_speech_committed")
    def on_speech_committed(msg: ChatMessage):
        """Fires when assistant commits a spoken response."""
        if msg.content:
            text = msg.content if isinstance(msg.content, str) else str(msg.content)
            asyncio.ensure_future(on_llm_response(text))

    assistant.start(ctx.room)

    # Greet the user
    await asyncio.sleep(1)
    await assistant.say(
        "Hello! I'm your AI assistant. How can I help you today?",
        allow_interruptions=True,
    )

    # Keep agent alive until room closes
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
