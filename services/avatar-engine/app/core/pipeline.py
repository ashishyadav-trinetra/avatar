"""
Avatar Pipeline — Orchestrator
───────────────────────────────
Coordinates:
  - ExpressionLayer  (MediaPipe + affine warp, CPU)
  - MuseTalkInference (UNet inpainting, GPU)
  - AudioEncoder     (Whisper tiny, GPU)
  - Redis pub/sub    (receives audio from LiveKit agent,
                      publishes frame bytes to WebRTC bridge)
"""
import asyncio
import time
import uuid
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import redis.asyncio as aioredis
from loguru import logger

from app.core.config import Settings
from app.core.expression_layer import ExpressionLayer, MotionState
from app.core.musetalk import MuseTalkInference, AudioEncoder
from app.core.stub_renderer import StubRenderer, StubAudioEncoder


def _make_renderer(config: Settings):
    """Return real MuseTalk or dev stub depending on DEV_MODE setting."""
    if config.DEV_MODE:
        logger.info("DEV_MODE=true → using StubRenderer (no GPU / no weights needed)")
        return StubRenderer(config)
    return MuseTalkInference(config)


def _make_audio_encoder(config: Settings):
    if config.DEV_MODE:
        return StubAudioEncoder(config)
    return AudioEncoder(config)


REDIS_CHANNEL_AUDIO  = "avatar:audio:{session_id}"   # LiveKit agent → engine
REDIS_CHANNEL_FRAMES = "avatar:frames:{session_id}"  # engine → WebRTC bridge
REDIS_CHANNEL_INTENT = "avatar:intent:{session_id}"  # agent → engine (motion state)
REDIS_KEY_SESSION    = "avatar:session:{session_id}"


class AvatarSession:
    """One active avatar session (one user, one video call)."""

    def __init__(self, session_id: str, image: np.ndarray, config: Settings):
        self.session_id = session_id
        self._config    = config
        self._image     = image
        self._running   = False

        self.expression  = ExpressionLayer(config)
        self.musetalk    = MuseTalkInference(config)
        self.audio_enc   = AudioEncoder(config)

        # Audio queue: chunks arrive from Redis, get consumed by render loop
        self._audio_queue: asyncio.Queue = asyncio.Queue(maxsize=30)
        self._idle_audio = self._make_silence_features()

    def _make_silence_features(self) -> np.ndarray:
        """1/FPS worth of silence features for idle state."""
        silence = np.zeros(int(16000 / self._config.FPS_TARGET), dtype=np.float32)
        return self.audio_enc.encode(silence)

    async def initialize(self):
        """Prepare face detection + load landmarks."""
        ok = self.expression.load_source(self._image)
        if not ok:
            raise ValueError("No face detected in uploaded photo")

        face_box = self.musetalk.prepare_face(self._image)
        if face_box is None:
            raise ValueError("MuseTalk face detection failed")

        logger.info(f"Session {self.session_id} initialized")

    async def enqueue_audio(self, pcm_bytes: bytes):
        """Receive raw PCM from Redis. Non-blocking drop if queue full."""
        pcm = np.frombuffer(pcm_bytes, dtype=np.float32)
        try:
            self._audio_queue.put_nowait(pcm)
        except asyncio.QueueFull:
            pass  # drop oldest intent — better than backing up

    def set_motion_state(self, state_str: str):
        try:
            state = MotionState(state_str)
            self.expression.set_motion_state(state)
        except ValueError:
            logger.warning(f"Unknown motion state: {state_str}")

    async def render_loop(self, redis_client: aioredis.Redis):
        """
        Main render loop: ~FPS iterations/second.
        Each iteration:
          1. Get animated ref frame from expression layer
          2. Get audio features (or silence)
          3. Run MuseTalk
          4. Publish frame bytes to Redis → WebRTC bridge
        """
        self._running = True
        frame_interval = 1.0 / self._config.FPS_TARGET
        channel = REDIS_CHANNEL_FRAMES.format(session_id=self.session_id)

        logger.info(f"Render loop started for session {self.session_id} @ {self._config.FPS_TARGET}fps")

        while self._running:
            t_start = time.perf_counter()

            # ── Expression layer (CPU) ─────────────────────────
            ref_frame = self.expression.get_frame()
            if ref_frame is None:
                await asyncio.sleep(frame_interval)
                continue

            # ── Audio features ────────────────────────────────
            try:
                pcm = self._audio_queue.get_nowait()
                audio_feats = self.audio_enc.encode(pcm)
            except asyncio.QueueEmpty:
                audio_feats = self._idle_audio  # silence = closed mouth

            # ── MuseTalk inference (GPU) ──────────────────────
            try:
                output_frame = self.musetalk.infer_frame(ref_frame, audio_feats)
            except Exception as e:
                logger.error(f"MuseTalk inference error: {e}")
                output_frame = ref_frame  # fallback: pass through

            # ── Encode + publish ──────────────────────────────
            _, buf = cv2.imencode(".jpg", output_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            await redis_client.publish(channel, buf.tobytes())

            # ── Pace to FPS target ─────────────────────────────
            elapsed = time.perf_counter() - t_start
            sleep_for = max(0.0, frame_interval - elapsed)
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)

        logger.info(f"Render loop stopped for session {self.session_id}")

    def stop(self):
        self._running = False


class AvatarPipeline:
    """Manages all active avatar sessions and Redis subscriptions."""

    def __init__(self, config: Settings):
        self._config   = config
        self._redis: Optional[aioredis.Redis] = None
        self._sessions: dict[str, AvatarSession] = {}
        self._sub_tasks: dict[str, asyncio.Task] = {}
        self._render_tasks: dict[str, asyncio.Task] = {}

        # Load ML models once at startup (real or stub depending on DEV_MODE)
        self._musetalk_template = _make_renderer(config)
        self._audio_enc_template = _make_audio_encoder(config)

    async def initialize(self):
        """Load weights + connect Redis."""
        if self._config.DEV_MODE:
            logger.info("DEV MODE — skipping model weight download/load")
        else:
            logger.info("Loading ML models (this takes 30–90s first time)...")

        self._musetalk_template.load()

        model_dir = Path(self._config.MODEL_DIR)
        if self._config.DEV_MODE:
            self._audio_enc_template.load("")   # stub ignores path
        else:
            self._audio_enc_template.load(str(model_dir / self._config.WHISPER_DIR))

        self._redis = await aioredis.from_url(
            self._config.REDIS_URL,
            encoding="utf-8",
            decode_responses=False,
        )
        logger.info("Pipeline initialized")

    async def create_session(self, image: np.ndarray) -> str:
        """Create a new avatar session from a source image."""
        session_id = str(uuid.uuid4())[:8]
        session = AvatarSession(session_id, image, self._config)

        # Share loaded model weights (don't re-load)
        session.musetalk = self._musetalk_template
        session.audio_enc = self._audio_enc_template

        await session.initialize()
        self._sessions[session_id] = session

        # Subscribe to audio + intent channels
        self._sub_tasks[session_id] = asyncio.create_task(
            self._subscribe_session(session_id)
        )

        # Start render loop
        self._render_tasks[session_id] = asyncio.create_task(
            session.render_loop(self._redis)
        )

        logger.info(f"Session created: {session_id}")
        return session_id

    async def destroy_session(self, session_id: str):
        if session_id in self._sessions:
            self._sessions[session_id].stop()
            del self._sessions[session_id]
        for task_map in (self._sub_tasks, self._render_tasks):
            if session_id in task_map:
                task_map[session_id].cancel()
                del task_map[session_id]
        logger.info(f"Session destroyed: {session_id}")

    async def _subscribe_session(self, session_id: str):
        """Listen for audio PCM and intent events from LiveKit agent."""
        pubsub = self._redis.pubsub()
        audio_ch  = REDIS_CHANNEL_AUDIO.format(session_id=session_id)
        intent_ch = REDIS_CHANNEL_INTENT.format(session_id=session_id)
        await pubsub.subscribe(audio_ch, intent_ch)

        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                channel = message["channel"].decode() if isinstance(message["channel"], bytes) else message["channel"]
                data    = message["data"]

                if channel == audio_ch:
                    session = self._sessions.get(session_id)
                    if session:
                        await session.enqueue_audio(data)

                elif channel == intent_ch:
                    state_str = data.decode() if isinstance(data, bytes) else data
                    session = self._sessions.get(session_id)
                    if session:
                        session.set_motion_state(state_str)
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe(audio_ch, intent_ch)

    async def cleanup(self):
        for sid in list(self._sessions.keys()):
            await self.destroy_session(sid)
        if self._redis:
            await self._redis.close()
