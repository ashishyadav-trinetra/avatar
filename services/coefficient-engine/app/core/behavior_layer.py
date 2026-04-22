"""
Behavior Layer — procedural animation above lip-sync.

Generates naturalistic idle behaviors that are uncorrelated with speech:
- Blinks (Poisson-distributed, ~15-20 per minute)
- Head micro-motion (slow Perlin-like drift)
- Eye saccades (quick gaze shifts every 2-5 seconds)
- Idle breathing (subtle chest/head rise, ~12-16 cycles/min)

All outputs are in the canonical coefficient format (63 floats).
The behavior layer ADDS to lip-sync coefficients — it doesn't replace them.
"""

import math
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np


class MotionState(str, Enum):
    NEUTRAL = "neutral"
    NODDING = "nodding"
    THINKING = "thinking"
    LISTENING = "listening"
    ENGAGED = "engaged"


@dataclass
class BehaviorConfig:
    # Blinks
    enable_blinks: bool = True
    blink_rate_per_min: float = 17.0        # Average blinks per minute
    blink_duration: float = 0.15            # Seconds
    blink_close_speed: float = 0.08         # Seconds to close
    double_blink_prob: float = 0.15         # Probability of double blink

    # Head motion
    enable_head_motion: bool = True
    head_drift_amplitude: float = 0.03      # Radians — very subtle
    head_drift_speed: float = 0.3           # Hz — slow drift
    nod_amplitude: float = 0.06             # Radians for nods
    nod_speed: float = 2.0                  # Hz for nods

    # Eye saccades
    enable_saccades: bool = True
    saccade_interval_range: tuple = (2.0, 5.0)  # Seconds between saccades
    saccade_amplitude: float = 0.08         # Radians
    saccade_duration: float = 0.05          # Seconds — saccades are fast

    # Breathing
    enable_breathing: bool = True
    breath_rate_per_min: float = 14.0       # Breaths per minute
    breath_head_amplitude: float = 0.005    # Very subtle head lift


@dataclass
class BehaviorState:
    """Mutable state for the behavior layer."""
    # Blink state
    next_blink_time: float = 0.0
    blink_phase: float = 0.0        # 0 = not blinking, 0..1 = blink progress
    blink_active: bool = False
    pending_double_blink: bool = False

    # Head motion state
    head_phase: float = 0.0         # Phase accumulator for drift
    motion_state: MotionState = MotionState.NEUTRAL
    nod_phase: float = 0.0
    nod_active: bool = False

    # Saccade state
    next_saccade_time: float = 0.0
    saccade_target: np.ndarray = field(default_factory=lambda: np.zeros(4, dtype=np.float32))
    saccade_current: np.ndarray = field(default_factory=lambda: np.zeros(4, dtype=np.float32))
    saccade_active: bool = False
    saccade_start_time: float = 0.0

    # Breathing
    breath_phase: float = 0.0


class BehaviorLayer:
    """
    Generates procedural behavior coefficients per frame.

    Usage:
        layer = BehaviorLayer()
        while streaming:
            behavior_coeffs = layer.tick(dt, is_speaking=lipsync_active)
            final_coeffs = lipsync_coeffs + behavior_coeffs
    """

    def __init__(self, cfg: Optional[BehaviorConfig] = None):
        self.cfg = cfg or BehaviorConfig()
        self.state = BehaviorState()
        self._rng = random.Random(42)
        self._t = 0.0  # Accumulated time

        # Schedule first events
        self.state.next_blink_time = self._next_blink_interval()
        self.state.next_saccade_time = self._rng.uniform(*self.cfg.saccade_interval_range)

    def tick(self, dt: float, is_speaking: bool = False) -> np.ndarray:
        """
        Advance behavior simulation by dt seconds.

        Returns:
            np.ndarray of shape (63,) — additive coefficients in canonical order:
            [exp_0..exp_49, jaw_0..jaw_5, pitch, yaw, roll, gaze_lh, gaze_lv, gaze_rh, gaze_rv]
        """
        self._t += dt
        coeffs = np.zeros(63, dtype=np.float32)

        # ── Blinks ───────────────────────────────────────────
        if self.cfg.enable_blinks:
            self._update_blinks(dt, coeffs, is_speaking)

        # ── Head motion ──────────────────────────────────────
        if self.cfg.enable_head_motion:
            self._update_head_motion(dt, coeffs, is_speaking)

        # ── Saccades ─────────────────────────────────────────
        if self.cfg.enable_saccades:
            self._update_saccades(dt, coeffs)

        # ── Breathing ────────────────────────────────────────
        if self.cfg.enable_breathing:
            self._update_breathing(dt, coeffs)

        return coeffs

    def set_motion_state(self, state: MotionState):
        """Transition to a new motion state (e.g., from intent classifier)."""
        if state != self.state.motion_state:
            self.state.motion_state = state
            if state == MotionState.NODDING:
                self.state.nod_active = True
                self.state.nod_phase = 0.0

    # ── Blink Generation ─────────────────────────────────────

    def _update_blinks(self, dt: float, coeffs: np.ndarray, is_speaking: bool):
        s = self.state
        cfg = self.cfg

        if not s.blink_active:
            s.next_blink_time -= dt
            if s.next_blink_time <= 0:
                s.blink_active = True
                s.blink_phase = 0.0
                s.pending_double_blink = self._rng.random() < cfg.double_blink_prob
                # Speaking increases blink rate slightly
                rate_mult = 1.3 if is_speaking else 1.0
                s.next_blink_time = self._next_blink_interval() / rate_mult

        if s.blink_active:
            s.blink_phase += dt / cfg.blink_duration
            if s.blink_phase >= 1.0:
                s.blink_active = False
                s.blink_phase = 0.0
                # Schedule double blink
                if s.pending_double_blink:
                    s.pending_double_blink = False
                    s.next_blink_time = 0.1  # Quick follow-up
            else:
                # Smooth blink curve: fast close, slower open
                t = s.blink_phase
                if t < 0.3:
                    # Closing (fast)
                    blink_val = t / 0.3
                elif t < 0.5:
                    # Closed
                    blink_val = 1.0
                else:
                    # Opening (slower)
                    blink_val = 1.0 - (t - 0.5) / 0.5

                blink_val = max(0.0, min(1.0, blink_val))

                # Map to expression params that control eyelids
                # exp_11 and exp_12 are used for left/right eye close in FLAME
                coeffs[11] = blink_val * 2.0   # Scale to FLAME param range
                coeffs[12] = blink_val * 2.0

    def _next_blink_interval(self) -> float:
        """Poisson-distributed inter-blink interval."""
        mean = 60.0 / self.cfg.blink_rate_per_min
        return self._rng.expovariate(1.0 / mean)

    # ── Head Motion ──────────────────────────────────────────

    def _update_head_motion(self, dt: float, coeffs: np.ndarray, is_speaking: bool):
        s = self.state
        cfg = self.cfg

        # Slow drift (always on)
        s.head_phase += dt * cfg.head_drift_speed * 2 * math.pi
        drift_pitch = math.sin(s.head_phase * 0.7) * cfg.head_drift_amplitude
        drift_yaw = math.sin(s.head_phase * 1.1 + 1.3) * cfg.head_drift_amplitude * 0.8
        drift_roll = math.sin(s.head_phase * 0.5 + 2.7) * cfg.head_drift_amplitude * 0.3

        # State-driven motion
        state_pitch = 0.0
        state_yaw = 0.0

        if s.motion_state == MotionState.NODDING and s.nod_active:
            s.nod_phase += dt * cfg.nod_speed * 2 * math.pi
            state_pitch = math.sin(s.nod_phase) * cfg.nod_amplitude
            if s.nod_phase > 4 * math.pi:  # ~2 nods
                s.nod_active = False
                s.motion_state = MotionState.NEUTRAL

        elif s.motion_state == MotionState.THINKING:
            # Slight upward look
            state_pitch = -cfg.head_drift_amplitude * 2
            state_yaw = cfg.head_drift_amplitude * 1.5

        elif s.motion_state == MotionState.LISTENING:
            # Slight head tilt
            drift_roll += cfg.head_drift_amplitude * 2

        # Indices 56, 57, 58 = pitch, yaw, roll
        coeffs[56] = drift_pitch + state_pitch
        coeffs[57] = drift_yaw + state_yaw
        coeffs[58] = drift_roll

    # ── Eye Saccades ─────────────────────────────────────────

    def _update_saccades(self, dt: float, coeffs: np.ndarray):
        s = self.state
        cfg = self.cfg

        s.next_saccade_time -= dt

        if s.next_saccade_time <= 0 and not s.saccade_active:
            # Start new saccade
            s.saccade_active = True
            s.saccade_start_time = self._t
            # Random target within range
            h = self._rng.gauss(0, cfg.saccade_amplitude)
            v = self._rng.gauss(0, cfg.saccade_amplitude * 0.5)
            # Both eyes look the same direction (conjugate gaze)
            s.saccade_target = np.array([h, v, h, v], dtype=np.float32)
            s.next_saccade_time = self._rng.uniform(*cfg.saccade_interval_range)

        if s.saccade_active:
            elapsed = self._t - s.saccade_start_time
            t = min(1.0, elapsed / cfg.saccade_duration)
            # Fast ease-out for saccade
            t_smooth = 1.0 - (1.0 - t) ** 3
            s.saccade_current = s.saccade_current + (s.saccade_target - s.saccade_current) * t_smooth

            if t >= 1.0:
                s.saccade_active = False
                s.saccade_current = s.saccade_target.copy()

        # Indices 59-62 = gaze_left_h, gaze_left_v, gaze_right_h, gaze_right_v
        coeffs[59:63] = s.saccade_current

    # ── Breathing ────────────────────────────────────────────

    def _update_breathing(self, dt: float, coeffs: np.ndarray):
        cfg = self.cfg
        s = self.state

        breath_freq = cfg.breath_rate_per_min / 60.0  # Hz
        s.breath_phase += dt * breath_freq * 2 * math.pi

        # Asymmetric breathing: longer exhale than inhale
        phase = s.breath_phase % (2 * math.pi)
        if phase < math.pi * 0.8:
            # Inhale (shorter)
            breath = math.sin(phase / 0.8)
        else:
            # Exhale (longer)
            breath = math.sin(math.pi + (phase - math.pi * 0.8) / 1.2)

        breath = max(0, breath)  # Only positive (upward motion)

        # Subtle head lift on inhale
        coeffs[56] += breath * cfg.breath_head_amplitude  # pitch

        # Very subtle jaw movement with breath
        coeffs[50] += breath * 0.02  # jaw_0 — slight jaw drop on inhale
