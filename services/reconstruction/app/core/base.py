"""
Base interface for reconstruction models.
All implementations (MICA, DECA, Stub) implement this interface,
making models swappable by configuration.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np


@dataclass
class ReconstructionInput:
    """Input to the reconstruction pipeline."""
    session_id: str
    photos: Dict[str, np.ndarray]   # shot_name → BGR image
    metadata: Dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class ReconstructionOutput:
    """Output from the reconstruction pipeline."""
    session_id: str
    glb_data: bytes                  # GLB binary with morph targets
    texture_data: Optional[bytes]    # PNG texture map
    vertex_count: int
    face_count: int
    blendshape_count: int
    mesh_version: str
    texture_version: str
    checksum: str                    # sha256:...
    reconstruction_time_ms: int
    model_name: str                  # Which model produced this


class ReconstructionModel(ABC):
    """
    Swappable reconstruction model interface.

    Implementations:
    - StubReconstructor: Dev mode — generates a simple placeholder GLB
    - MICAReconstructor: MICA shape fitting
    - DECAReconstructor: DECA shape + texture
    - MICADECAReconstructor: MICA shape + DECA texture (best quality)
    """

    name: str = "base"

    @abstractmethod
    async def initialize(self, model_dir: str, device: str) -> None:
        """Load model weights and prepare for inference."""
        ...

    @abstractmethod
    async def reconstruct(self, input: ReconstructionInput) -> ReconstructionOutput:
        """
        Reconstruct a 3D avatar from calibration photos.

        Args:
            input: Photos + metadata

        Returns:
            GLB mesh with FLAME topology and morph targets
        """
        ...

    async def shutdown(self) -> None:
        """Release GPU memory and resources."""
        pass

    def is_ready(self) -> bool:
        """Whether model is loaded and ready."""
        return False
