"""
Expression Layer — MediaPipe Face Mesh + Affine Warp
─────────────────────────────────────────────────────
Extracts 468 landmarks from source photo ONCE at startup.
Per frame: applies parametric yaw/pitch/roll/eye params via
affine transformation to produce an animated reference frame.
MuseTalk then stamps lip-sync onto this frame.
"""
import math
import time
import random
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import cv2
import numpy as np
import mediapipe as mp
from loguru import logger


# ── Motion states driven by LLM intent ───────────────────────
class MotionState(str, Enum):
    NEUTRAL   = "neutral"
    NODDING   = "nodding"
    THINKING  = "thinking"
    ENGAGED   = "engaged"
    EMPATHIC  = "empathic"
    LISTENING = "listening"


# Param envelopes per state: (yaw, pitch, brow_raise, nod_amplitude, speed_mult)
STATE_PARAMS = {
    MotionState.NEUTRAL:   dict(yaw=0.00,  pitch=0.00,  brow=0.00, nod=0.00, spd=1.0),
    MotionState.NODDING:   dict(yaw=0.00,  pitch=0.00,  brow=0.05, nod=0.06, spd=1.4),
    MotionState.THINKING:  dict(yaw=-0.03, pitch=0.04,  brow=0.10, nod=0.00, spd=0.7),
    MotionState.ENGAGED:   dict(yaw=0.03,  pitch=-0.02, brow=0.15, nod=0.03, spd=1.2),
    MotionState.EMPATHIC:  dict(yaw=0.00,  pitch=-0.03, brow=0.20, nod=0.02, spd=0.9),
    MotionState.LISTENING: dict(yaw=0.02,  pitch=-0.01, brow=0.05, nod=0.01, spd=0.8),
}


@dataclass
class MotionParams:
    yaw:        float = 0.0
    pitch:      float = 0.0
    roll:       float = 0.0
    eye_open_l: float = 1.0
    eye_open_r: float = 1.0
    brow_raise: float = 0.0


class BlinkController:
    """Poisson-distributed blink events."""

    def __init__(self, interval_min=3.0, interval_max=6.0):
        self._min = interval_min
        self._max = interval_max
        self._next_blink = time.time() + random.uniform(interval_min, interval_max)
        self._blink_duration = 0.12  # seconds
        self._blink_start: Optional[float] = None

    def get_eye_openness(self) -> tuple[float, float]:
        now = time.time()
        if self._blink_start is None and now >= self._next_blink:
            self._blink_start = now
            self._next_blink = now + random.uniform(self._min, self._max)

        if self._blink_start is not None:
            elapsed = now - self._blink_start
            if elapsed >= self._blink_duration:
                self._blink_start = None
                return 1.0, 1.0
            # Smooth close-open curve: goes to 0 at midpoint
            t = elapsed / self._blink_duration
            openness = 1.0 - math.sin(t * math.pi) ** 2
            # Slight natural asymmetry
            return openness, openness * 0.97

        return 1.0, 0.98  # resting asymmetry


class ExpressionLayer:
    """
    Drives the reference frame that MuseTalk receives.
    Two layers blended together:
      - Procedural idle micro-motion (always running)
      - Intent-driven FSM envelope (async updated)
    """

    def __init__(self, config):
        self._config = config
        self._mp_face_mesh = mp.solutions.face_mesh
        self._face_mesh = self._mp_face_mesh.FaceMesh(
            static_image_mode=True,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
        )

        # Source photo data (set on initialize)
        self._source_image: Optional[np.ndarray] = None
        self._landmarks: Optional[np.ndarray] = None   # (468, 2) pixel coords
        self._face_center: Optional[np.ndarray] = None

        # Motion state
        self._motion_state = MotionState.NEUTRAL
        self._state_params = STATE_PARAMS[MotionState.NEUTRAL].copy()
        self._target_params = self._state_params.copy()
        self._transition_start = time.time()
        self._state_lock = threading.Lock()

        # Blink
        self._blink = BlinkController(
            config.BLINK_INTERVAL_MIN,
            config.BLINK_INTERVAL_MAX,
        )

        self._t0 = time.time()

    # ── Public API ───────────────────────────────────────────

    def load_source(self, image: np.ndarray) -> bool:
        """Extract MediaPipe landmarks from source photo. Call once."""
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        results = self._face_mesh.process(rgb)
        if not results.multi_face_landmarks:
            logger.warning("No face detected in source image")
            return False

        h, w = image.shape[:2]
        lm = results.multi_face_landmarks[0].landmark
        self._landmarks = np.array([[l.x * w, l.y * h] for l in lm], dtype=np.float32)
        self._face_center = self._landmarks.mean(axis=0)
        self._source_image = image.copy()
        logger.info(f"Loaded {len(self._landmarks)} landmarks from source photo")
        return True

    def set_motion_state(self, state: MotionState):
        """Called from intent classifier (async, no GPU required)."""
        with self._state_lock:
            if state == self._motion_state:
                return
            logger.debug(f"Motion state: {self._motion_state} → {state}")
            self._motion_state = state
            self._target_params = STATE_PARAMS[state].copy()
            self._transition_start = time.time()

    def get_frame(self) -> Optional[np.ndarray]:
        """
        Generate one animated reference frame.
        Called every 1/FPS seconds from the render loop.
        Returns BGR ndarray same size as source image.
        """
        if self._source_image is None or self._landmarks is None:
            return None

        t = time.time() - self._t0
        params = self._compute_params(t)
        return self._warp_frame(params)

    # ── Internal ─────────────────────────────────────────────

    def _compute_params(self, t: float) -> MotionParams:
        cfg = self._config

        # ── Layer 1: procedural idle micro-motion ─────────────
        spd = self._state_params.get("spd", 1.0) * cfg.IDLE_MOTION_SPEED
        idle_yaw   = cfg.IDLE_YAW_AMPLITUDE   * math.sin(t * spd * 1.0)
        idle_pitch = cfg.IDLE_PITCH_AMPLITUDE * math.sin(t * spd * 0.7 + 0.5)
        idle_roll  = cfg.IDLE_YAW_AMPLITUDE * 0.3 * math.sin(t * spd * 0.4 + 1.0)

        # ── Layer 2: FSM envelope ─────────────────────────────
        with self._state_lock:
            elapsed = (time.time() - self._transition_start) * 1000
            alpha = min(elapsed / cfg.MOTION_TRANSITION_MS, 1.0)
            # Cubic ease-in-out
            alpha = alpha * alpha * (3 - 2 * alpha)
            current = self._state_params
            target  = self._target_params
            blended = {k: current[k] + (target[k] - current[k]) * alpha for k in current}
            # Snap once fully transitioned
            if alpha >= 1.0:
                self._state_params = target.copy()

        # Nodding: extra pitch oscillation
        nod = blended["nod"] * math.sin(t * 4.0) if blended["nod"] > 0 else 0

        # ── Layer 3: blink ────────────────────────────────────
        eye_l, eye_r = self._blink.get_eye_openness()

        return MotionParams(
            yaw        = idle_yaw   + blended["yaw"],
            pitch      = idle_pitch + blended["pitch"] + nod,
            roll       = idle_roll,
            eye_open_l = eye_l,
            eye_open_r = eye_r,
            brow_raise = blended["brow"],
        )

    def _warp_frame(self, params: MotionParams) -> np.ndarray:
        """
        Apply affine warp to simulate head rotation.
        Uses the landmark centroid as the warp center.
        Small angles only — good for subtle motion (±5°).
        """
        img = self._source_image.copy()
        h, w = img.shape[:2]
        cx, cy = self._face_center

        # Convert params to pixel displacement
        # yaw   → horizontal shift of face
        # pitch → vertical shift of face
        # roll  → rotation around center
        face_width = (
            self._landmarks[:, 0].max() - self._landmarks[:, 0].min()
        )

        dx = params.yaw   * face_width * 2.0
        dy = params.pitch * face_width * 2.0
        angle_deg = math.degrees(params.roll)

        # Build 2×3 affine matrix: rotate + translate
        M = cv2.getRotationMatrix2D((cx, cy), angle_deg, 1.0)
        M[0, 2] += dx
        M[1, 2] += dy

        warped = cv2.warpAffine(
            img, M, (w, h),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )

        # Apply eye/brow modulation via landmark-based local warps
        warped = self._apply_eye_state(warped, params)
        return warped

    def _apply_eye_state(self, img: np.ndarray, params: MotionParams) -> np.ndarray:
        """
        Approximate eye closure by scaling the eye region vertically.
        Uses MediaPipe eye landmark indices.
        """
        if params.eye_open_l >= 0.99 and params.eye_open_r >= 0.99:
            return img  # fully open — skip warp

        # MediaPipe left eye upper/lower lid indices (subset)
        LEFT_EYE_TOP    = [386, 374, 373, 390]
        LEFT_EYE_BOTTOM = [380, 381, 382, 362]
        RIGHT_EYE_TOP   = [159, 145, 144, 163]
        RIGHT_EYE_BOTTOM = [153, 154, 155, 133]

        lm = self._landmarks
        result = img.copy()

        def close_eye(top_idx, bot_idx, openness):
            if openness >= 0.99:
                return
            top_pts = lm[top_idx]
            bot_pts = lm[bot_idx]
            center_y = (top_pts[:, 1].mean() + bot_pts[:, 1].mean()) / 2
            # Shift top lids down toward center proportional to closure
            shift = (1.0 - openness) * (center_y - top_pts[:, 1].mean())
            # We just do a small vertical region warp — approximate
            y1 = int(top_pts[:, 1].min()) - 2
            y2 = int(bot_pts[:, 1].max()) + 2
            x1 = int(min(top_pts[:, 0].min(), bot_pts[:, 0].min())) - 2
            x2 = int(max(top_pts[:, 0].max(), bot_pts[:, 0].max())) + 2
            y1, y2 = max(0, y1), min(img.shape[0], y2)
            x1, x2 = max(0, x1), min(img.shape[1], x2)
            if y2 <= y1 or x2 <= x1:
                return
            region = result[y1:y2, x1:x2]
            rh = y2 - y1
            new_h = max(1, int(rh * openness))
            scaled = cv2.resize(region, (x2 - x1, new_h), interpolation=cv2.INTER_LINEAR)
            # Paste scaled region, rest fill with skin color
            fill = region[rh // 2 : rh // 2 + 1, :]
            result[y1:y2, x1:x2] = np.tile(fill, (rh, 1, 1))
            result[y1:y1 + new_h, x1:x2] = scaled

        close_eye(LEFT_EYE_TOP,  LEFT_EYE_BOTTOM,  params.eye_open_l)
        close_eye(RIGHT_EYE_TOP, RIGHT_EYE_BOTTOM, params.eye_open_r)
        return result
