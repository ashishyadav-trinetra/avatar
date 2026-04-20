"""
Dev Stub Renderer
──────────────────
Replaces MuseTalk when DEV_MODE=true.
Generates animated frames using pure OpenCV — no GPU, no model weights.

What it does:
  - Takes the source photo
  - Draws an animated mouth shape that pulses with the audio amplitude
  - Overlays a "DEV MODE" watermark so you always know it's a stub
  - Produces frames at ~10 FPS on CPU (vs 25 FPS with GPU + MuseTalk)

This lets you validate the full pipeline end-to-end:
  LiveKit agent → Redis → avatar-engine → WebRTC bridge → browser
without needing a GPU or downloading model weights.
"""
import math
import time
from typing import Optional

import cv2
import numpy as np
from loguru import logger


class StubRenderer:
    """
    CPU-only animated frame generator for dev/testing.
    Mimics the MuseTalkInference.infer_frame() interface exactly.
    """

    def __init__(self, config):
        self._config    = config
        self._face_box: Optional[tuple] = None
        self._t0        = time.time()
        self._loaded    = False
        logger.warning("DEV MODE: Using StubRenderer — MuseTalk NOT loaded")

    def load(self):
        """No-op in dev mode. Real MuseTalk would load ~3.5GB of weights here."""
        self._loaded = True
        logger.info("StubRenderer ready (no weights loaded — dev mode)")

    def prepare_face(self, image: np.ndarray) -> Optional[tuple]:
        """
        Detect face using basic OpenCV Haar cascade (no deep learning).
        Falls back to a fixed center crop if no face found.
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        h, w = image.shape[:2]

        # Try Haar cascade
        cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        faces = cascade.detectMultiScale(gray, 1.1, 4)

        if len(faces) > 0:
            fx, fy, fw, fh = faces[0]
            # Expand box slightly
            pad = 20
            x1 = max(0, fx - pad)
            y1 = max(0, fy - pad)
            x2 = min(w, fx + fw + pad)
            y2 = min(h, fy + fh + pad)
            self._face_box = (x1, y1, x2, y2)
            logger.info(f"[DEV] Haar face detected: {self._face_box}")
        else:
            # No face found — use center 60% of image
            cx, cy = w // 2, h // 2
            fw, fh = int(w * 0.6), int(h * 0.6)
            self._face_box = (cx - fw//2, cy - fh//2, cx + fw//2, cy + fh//2)
            logger.warning(f"[DEV] No face detected via Haar — using center crop: {self._face_box}")

        return self._face_box

    def infer_frame(
        self,
        reference_frame: np.ndarray,
        audio_features: np.ndarray,
    ) -> np.ndarray:
        """
        Generate a fake lip-synced frame.
        Draws an animated ellipse mouth that oscillates with audio energy.
        """
        result = reference_frame.copy()
        t = time.time() - self._t0

        if self._face_box is None:
            return result

        x1, y1, x2, y2 = self._face_box
        fw = x2 - x1
        fh = y2 - y1

        # ── Estimate mouth position (lower 1/3 of face box) ──
        mouth_cx = x1 + fw // 2
        mouth_cy = y1 + int(fh * 0.78)

        # ── Audio amplitude → mouth openness ─────────────────
        if audio_features is not None and len(audio_features.flatten()) > 0:
            amplitude = float(np.abs(audio_features).mean())
            # Normalize — whisper features are typically 0–8 range
            amplitude = min(amplitude / 4.0, 1.0)
        else:
            amplitude = 0.0

        # Add natural oscillation when speaking
        speak_osc = amplitude * 0.3 * math.sin(t * 12.0)
        mouth_open = amplitude + speak_osc

        # ── Draw animated mouth ───────────────────────────────
        mouth_w = max(4, int(fw * 0.22))
        mouth_h_open = max(2, int(fh * 0.08 * (mouth_open + 0.05)))
        mouth_h_close = max(2, int(fh * 0.015))

        # Outer lip outline (darker)
        cv2.ellipse(
            result,
            (mouth_cx, mouth_cy),
            (mouth_w, max(mouth_h_open, mouth_h_close)),
            0, 0, 180,
            (60, 30, 30), -1
        )
        # Inner mouth opening (dark)
        if mouth_open > 0.05:
            cv2.ellipse(
                result,
                (mouth_cx, mouth_cy + mouth_h_close),
                (int(mouth_w * 0.75), mouth_h_open),
                0, 0, 180,
                (20, 10, 10), -1
            )
        # Upper lip
        cv2.ellipse(
            result,
            (mouth_cx, mouth_cy),
            (mouth_w, mouth_h_close),
            0, 180, 360,
            (80, 50, 60), -1
        )

        # ── DEV watermark ─────────────────────────────────────
        cv2.putText(
            result,
            "DEV MODE",
            (x1 + 4, y1 + 18),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45, (0, 200, 100), 1, cv2.LINE_AA
        )

        # ── FPS counter ───────────────────────────────────────
        fps_text = f"{self._config.FPS_TARGET}fps target"
        cv2.putText(
            result,
            fps_text,
            (x1 + 4, y1 + 34),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.35, (0, 150, 80), 1, cv2.LINE_AA
        )

        return result


class StubAudioEncoder:
    """
    CPU audio encoder stub.
    Returns dummy feature vector instead of running Whisper.
    """

    def __init__(self, config):
        self._config = config

    def load(self, whisper_path: str):
        logger.info("[DEV] StubAudioEncoder loaded (no Whisper weights)")

    def encode(self, audio_chunk: np.ndarray, sample_rate: int = 16000) -> np.ndarray:
        """
        Compute simple RMS energy as a proxy for audio features.
        Shape matches Whisper output: (1, T, 384) approximately.
        In dev mode we just return energy as a scalar embedded in the array.
        """
        if len(audio_chunk) == 0:
            return np.zeros((1, 1, 384), dtype=np.float32)

        rms = float(np.sqrt(np.mean(audio_chunk ** 2)))
        # Fill a (1, 8, 384) array with the RMS value
        # This gives the StubRenderer something to read for mouth animation
        features = np.full((1, 8, 384), rms * 4.0, dtype=np.float32)
        return features
