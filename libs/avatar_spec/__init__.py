"""
Canonical Avatar Spec — shared constants and data structures.

All services import from here to ensure consistent blendshape ordering,
frame format, and protocol definitions. This is the single source of truth.
"""

from .constants import (
    SPEC_VERSION,
    FLAME_VERTEX_COUNT,
    FLAME_FACE_COUNT,
    EXPRESSION_PARAMS,
    JAW_PARAMS,
    HEAD_POSE_CHANNELS,
    EYE_GAZE_CHANNELS,
    ALL_CHANNELS,
    NUM_EXPRESSION,
    NUM_JAW,
    NUM_HEAD_POSE,
    NUM_EYE_GAZE,
    NUM_TOTAL_FLOATS,
    FRAME_HEADER_SIZE,
    FRAME_PAYLOAD_SIZE,
    FRAME_TOTAL_SIZE,
    TARGET_FPS,
    KEYFRAME_INTERVAL,
    JITTER_BUFFER_MIN,
    JITTER_BUFFER_MAX,
    PARAM_RANGE_MIN,
    PARAM_RANGE_MAX,
    TEXTURE_RESOLUTION,
    CALIBRATION_SHOTS,
    QUALITY_GATES,
)
from .frames import CoefficientFrame, FrameFlags, encode_frame, decode_frame
from .types import (
    CalibrationShot,
    CalibrationPhoto,
    QualityGateResult,
    AvatarMetadata,
    AvatarBundle,
    ServiceInterface,
)

__version__ = SPEC_VERSION
