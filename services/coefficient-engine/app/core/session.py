"""
Coefficient streaming session — manages per-session state.
Each active avatar gets its own CoefficientSession which:
1. Subscribes to audio from Redis (published by LiveKit agent)
2. Runs lip-sync model on audio chunks
3. Layers behavior (blinks, head motion, saccades, breathing)
4. Streams binary coefficient frames to connected WebSocket clients
"""

import asyncio
import logging
import struct
import time
from typing import Dict, List, Optional, Set

import numpy as np

from .behavior_layer import BehaviorLayer, BehaviorConfig
from .lipsync_base import LipSyncModel
from .config import config

logger = logging.getLogger(__name__)

# Frame constants (matching avatar_spec)
_NUM_TOTAL = 63
_HEADER_SIZE = 6
_TARGET_FPS = 30
_FRAME_INTERVAL = 1.0 / _TARGET_FPS


class CoefficientSession:
    """
    Per-session coefficient generation and streaming.

    Lifecycle:
    1. Created when a session starts
    2. Runs a render loop at 30 FPS
    3. Receives audio chunks via feed_audio()
    4. Produces coefficient frames consumed by WebSocket clients
    """

    def __init__(
        self,
        session_id: str,
        lipsync: LipSyncModel,
    ):
        self.session_id = session_id
        self._lipsync = lipsync
        self._behavior = BehaviorLayer(BehaviorConfig(
            enable_blinks=config.ENABLE_BLINKS,
            enable_head_motion=config.ENABLE_HEAD_MOTION,
            enable_saccades=config.ENABLE_SACCADES,
            enable_breathing=config.ENABLE_BREATHING,
        ))

        # Audio buffer (accumulates chunks between frames)
        self._audio_buffer: List[np.ndarray] = []
        self._audio_lock = asyncio.Lock()

        # Output queue for WebSocket consumers
        self._frame_queue: asyncio.Queue = asyncio.Queue(maxsize=100)

        # State
        self._running = False
        self._sequence = 0
        self._last_keyframe_seq = 0
        self._previous_coeffs = np.zeros(_NUM_TOTAL, dtype=np.float32)
        self._is_speaking = False

        # Render loop task
        self._render_task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the coefficient render loop."""
        self._running = True
        self._render_task = asyncio.create_task(self._render_loop())
        logger.info(f"[{self.session_id}] Coefficient session started")

    async def stop(self):
        """Stop the render loop and clean up."""
        self._running = False
        if self._render_task:
            self._render_task.cancel()
            try:
                await self._render_task
            except asyncio.CancelledError:
                pass
        logger.info(f"[{self.session_id}] Coefficient session stopped")

    async def feed_audio(self, pcm_data: np.ndarray, sample_rate: int = 16000):
        """
        Feed an audio chunk to the session.
        Called by the Redis subscriber when LiveKit agent publishes TTS audio.
        """
        async with self._audio_lock:
            self._audio_buffer.append(pcm_data)

    async def get_frame(self) -> Optional[bytes]:
        """Get the next encoded frame (blocking). Used by WebSocket handler."""
        try:
            return await asyncio.wait_for(self._frame_queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            return None

    async def _render_loop(self):
        """Main render loop — runs at TARGET_FPS."""
        logger.info(f"[{self.session_id}] Render loop started at {_TARGET_FPS} FPS")

        while self._running:
            t0 = time.monotonic()

            try:
                frame = await self._generate_frame()
                encoded = self._encode_frame(frame)

                # Non-blocking put — drop oldest if queue full
                if self._frame_queue.full():
                    try:
                        self._frame_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                self._frame_queue.put_nowait(encoded)

            except Exception as e:
                logger.error(f"[{self.session_id}] Render error: {e}")

            # Sleep to maintain target FPS
            elapsed = time.monotonic() - t0
            sleep_time = max(0, _FRAME_INTERVAL - elapsed)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

    async def _generate_frame(self) -> np.ndarray:
        """Generate a single coefficient frame (63 floats)."""
        coeffs = np.zeros(_NUM_TOTAL, dtype=np.float32)

        # ── 1. Lip sync from audio ──────────────────────────
        lipsync_coeffs = np.zeros(56, dtype=np.float32)

        async with self._audio_lock:
            if self._audio_buffer:
                # Concatenate buffered audio
                audio = np.concatenate(self._audio_buffer)
                self._audio_buffer.clear()

                # Run lip sync model
                lip_frames = self._lipsync.process_audio(audio, 16000)
                if len(lip_frames) > 0:
                    # Use the last frame (most recent)
                    lipsync_coeffs = lip_frames[-1]
                    self._is_speaking = True
            else:
                self._is_speaking = False

        # Copy lip-sync into expression + jaw slots (indices 0-55)
        coeffs[:56] = lipsync_coeffs

        # ── 2. Behavior layer (additive) ────────────────────
        behavior = self._behavior.tick(_FRAME_INTERVAL, is_speaking=self._is_speaking)
        coeffs += behavior

        return coeffs

    def _encode_frame(self, coeffs: np.ndarray) -> bytes:
        """Encode a coefficient array into a binary frame with header."""
        timestamp_ms = int(time.time() * 1000) & 0xFFFFFFFF
        self._sequence = (self._sequence + 1) % 256

        # Determine if this should be a keyframe
        is_keyframe = (self._sequence - self._last_keyframe_seq) % 256 >= config.KEYFRAME_INTERVAL
        if is_keyframe:
            self._last_keyframe_seq = self._sequence

        # Flags
        flags = 0
        if is_keyframe:
            flags |= 0b00000010  # IS_KEYFRAME
        else:
            flags |= 0b00000001  # IS_DELTA
        if self._is_speaking:
            flags |= 0b00000100  # IS_SPEAKING

        # For delta frames, compute delta from previous
        if not is_keyframe:
            payload = (coeffs - self._previous_coeffs).astype(np.float32)
        else:
            payload = coeffs.astype(np.float32)

        self._previous_coeffs = coeffs.copy()

        # Pack header + payload
        header = struct.pack("<IBB", timestamp_ms, flags, self._sequence)
        return header + payload.tobytes()
