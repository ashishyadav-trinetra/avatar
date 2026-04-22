"""
Shared data types for the Avatar pipeline.
These define the contracts between services.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ── Calibration ──────────────────────────────────────────────────

@dataclass
class CalibrationShot:
    """Definition of a required calibration photo."""
    name: str
    angle: str
    expression: str
    description: str


@dataclass
class CalibrationPhoto:
    """A captured calibration photo with quality metadata."""
    shot_name: str              # Matches CalibrationShot.name
    image_data: bytes           # Raw image bytes (JPEG/PNG)
    width: int
    height: int
    mime_type: str = "image/jpeg"
    quality_score: float = 0.0  # 0-1, set by quality gate
    metadata: Dict[str, Any] = field(default_factory=dict)


# ── Quality Gating ───────────────────────────────────────────────

class QualityGateStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass
class QualityGateResult:
    """Result of a single quality gate check."""
    gate_name: str
    status: QualityGateStatus
    message: str
    score: float = 1.0          # 0-1 confidence
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QualityReport:
    """Aggregate quality report for a set of calibration photos."""
    passed: bool
    gates: List[QualityGateResult]
    overall_score: float
    recommendations: List[str] = field(default_factory=list)


# ── Avatar Bundle ────────────────────────────────────────────────

@dataclass
class AvatarMetadata:
    """Metadata for a reconstructed avatar."""
    spec_version: str
    mesh_version: str
    texture_version: str
    reconstruction_model: str   # e.g. "MICA+DECA"
    vertex_count: int
    face_count: int
    blendshape_count: int
    checksum: str               # sha256:...
    enhanced_texture: bool = False
    reconstruction_time_ms: int = 0
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AvatarBundle:
    """Complete avatar output from reconstruction."""
    session_id: str
    glb_data: bytes             # GLB binary
    metadata: AvatarMetadata
    texture_data: Optional[bytes] = None  # Separate texture if needed
    thumbnail: Optional[bytes] = None     # Preview image


# ── Service Interfaces ───────────────────────────────────────────

class ServiceInterface:
    """
    Base interface marker for model-swappable services.
    Concrete implementations register themselves via this pattern:

        class MICAReconstructor(ServiceInterface):
            name = "MICA"
            async def reconstruct(self, photos: List[CalibrationPhoto]) -> AvatarBundle:
                ...

    The pipeline selects the implementation by config.
    """
    name: str = "base"

    async def initialize(self) -> None:
        """Load models, warm up GPU, etc."""
        raise NotImplementedError

    async def shutdown(self) -> None:
        """Release resources."""
        pass

    def is_ready(self) -> bool:
        """Whether the service is ready to accept requests."""
        return False
