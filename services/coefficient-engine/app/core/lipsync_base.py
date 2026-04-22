"""
Lip-sync model interface — swappable between FaceFormer, CodeTalker, and Stub.
All implementations take audio PCM chunks and output FLAME expression coefficients.
"""

from abc import ABC, abstractmethod
from typing import List

import numpy as np


class LipSyncModel(ABC):
    """
    Audio → FLAME coefficient model interface.

    Implementations:
    - StubLipSync: Dev mode — generates synthetic mouth movement from audio energy
    - FaceFormerLipSync: FaceFormer transformer model
    - CodeTalkerLipSync: CodeTalker VQ-VAE model
    """

    name: str = "base"

    @abstractmethod
    async def initialize(self, model_dir: str, device: str) -> None:
        """Load model weights."""
        ...

    @abstractmethod
    def process_audio(
        self,
        audio_pcm: np.ndarray,
        sample_rate: int = 16000,
    ) -> np.ndarray:
        """
        Convert audio chunk to FLAME expression coefficients.

        Args:
            audio_pcm: PCM audio data (mono, float32, -1 to 1)
            sample_rate: Audio sample rate (default 16kHz)

        Returns:
            np.ndarray of shape (num_frames, 56) — expression + jaw coefficients
            at 30 FPS. Does NOT include head pose or gaze (those come from behavior layer).
        """
        ...

    async def shutdown(self) -> None:
        pass

    def is_ready(self) -> bool:
        return False
