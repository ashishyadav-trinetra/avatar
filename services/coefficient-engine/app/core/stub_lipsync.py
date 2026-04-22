"""
Stub lip-sync for DEV MODE — generates synthetic FLAME coefficients
from audio energy analysis. No ML model needed.

Produces visually plausible mouth movement by mapping:
- RMS energy → jaw open (jaw_0)
- Spectral centroid → mouth shape variation (exp params 0-19)
- Zero-crossing rate → lip tension
"""

import logging

import numpy as np

from .lipsync_base import LipSyncModel

logger = logging.getLogger(__name__)

# Target output FPS
_TARGET_FPS = 30
# Number of expression + jaw params
_NUM_COEFF = 56  # 50 expression + 6 jaw


def _rms_energy(audio: np.ndarray, frame_size: int) -> np.ndarray:
    """Compute RMS energy per frame."""
    n_frames = len(audio) // frame_size
    if n_frames == 0:
        return np.array([0.0])
    frames = audio[:n_frames * frame_size].reshape(n_frames, frame_size)
    return np.sqrt(np.mean(frames ** 2, axis=1))


def _zero_crossing_rate(audio: np.ndarray, frame_size: int) -> np.ndarray:
    """Compute zero-crossing rate per frame."""
    n_frames = len(audio) // frame_size
    if n_frames == 0:
        return np.array([0.0])
    frames = audio[:n_frames * frame_size].reshape(n_frames, frame_size)
    signs = np.sign(frames)
    diffs = np.abs(np.diff(signs, axis=1))
    return np.mean(diffs, axis=1) / 2


class StubLipSync(LipSyncModel):
    """
    Dev-mode lip sync — audio energy to FLAME coefficients.
    No GPU required. Produces reasonable-looking mouth movement.
    """

    name = "stub"

    def __init__(self):
        self._ready = False

    async def initialize(self, model_dir: str, device: str) -> None:
        logger.info("StubLipSync: initialized (energy-based, no model)")
        self._ready = True

    def process_audio(
        self,
        audio_pcm: np.ndarray,
        sample_rate: int = 16000,
    ) -> np.ndarray:
        """
        Convert audio to 56-dimensional FLAME coefficients at 30 FPS.

        Returns shape (num_frames, 56).
        """
        if len(audio_pcm) == 0:
            return np.zeros((1, _NUM_COEFF), dtype=np.float32)

        # Calculate frames at target FPS
        samples_per_frame = sample_rate // _TARGET_FPS
        n_frames = max(1, len(audio_pcm) // samples_per_frame)

        # Resample audio to frame boundaries
        audio = audio_pcm[:n_frames * samples_per_frame]

        # Compute features
        energy = _rms_energy(audio, samples_per_frame)
        zcr = _zero_crossing_rate(audio, samples_per_frame)

        # Normalize energy to 0-1 range
        max_energy = np.max(energy) if np.max(energy) > 0 else 1.0
        energy_norm = np.clip(energy / max_energy, 0, 1)

        # Generate coefficients
        coeffs = np.zeros((n_frames, _NUM_COEFF), dtype=np.float32)

        for i in range(n_frames):
            e = energy_norm[i] if i < len(energy_norm) else 0
            z = zcr[i] if i < len(zcr) else 0

            # ── Jaw open (primary mouth movement) ────────────
            # jaw_0 is the main jaw open parameter
            coeffs[i, 50] = e * 1.5  # jaw_0: proportional to energy

            # ── Lip shape (expression params 0-19) ───────────
            # Map different audio features to different mouth shapes
            # to create varied visemes

            # Upper lip raise (tracks energy with slight delay)
            coeffs[i, 0] = e * 0.8

            # Lower lip drop
            coeffs[i, 1] = e * 1.0

            # Lip corner pull (smile-like when speaking)
            coeffs[i, 2] = e * 0.3

            # Lip pucker (from ZCR — higher pitch = more pucker)
            pucker = min(1.0, z * 2)
            coeffs[i, 5] = pucker * 0.4

            # Lip stretch (antagonist to pucker)
            coeffs[i, 6] = (1.0 - pucker) * e * 0.3

            # Mouth width variation
            coeffs[i, 10] = e * 0.2 * (1 + 0.5 * np.sin(i * 0.5))

            # Cheek puff (subtle, tracks energy)
            coeffs[i, 15] = e * 0.15

            # Add some temporal smoothing via simple low-pass
            if i > 0:
                alpha = 0.3  # Smoothing factor
                coeffs[i, :50] = alpha * coeffs[i, :50] + (1 - alpha) * coeffs[i - 1, :50]

        return coeffs

    def is_ready(self) -> bool:
        return self._ready
