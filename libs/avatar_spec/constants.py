"""
Canonical constants for the Avatar pipeline.
Single source of truth — all services import from here.
"""

SPEC_VERSION = "1.0.0"

# ── FLAME Mesh ────────────────────────────────────────────────────
FLAME_VERTEX_COUNT = 5023
FLAME_FACE_COUNT = 9976

# ── Blendshape Parameters ────────────────────────────────────────
# 50 FLAME expression parameters
EXPRESSION_PARAMS = [f"exp_{i}" for i in range(50)]

# 6 FLAME jaw/pose parameters
JAW_PARAMS = [f"jaw_{i}" for i in range(6)]

# Head pose (euler angles in radians)
HEAD_POSE_CHANNELS = ["pitch", "yaw", "roll"]

# Eye gaze (radians)
EYE_GAZE_CHANNELS = ["gaze_left_h", "gaze_left_v", "gaze_right_h", "gaze_right_v"]

# Canonical order for coefficient frames
ALL_CHANNELS = EXPRESSION_PARAMS + JAW_PARAMS + HEAD_POSE_CHANNELS + EYE_GAZE_CHANNELS

NUM_EXPRESSION = len(EXPRESSION_PARAMS)     # 50
NUM_JAW = len(JAW_PARAMS)                   # 6
NUM_HEAD_POSE = len(HEAD_POSE_CHANNELS)     # 3
NUM_EYE_GAZE = len(EYE_GAZE_CHANNELS)      # 4
NUM_TOTAL_FLOATS = len(ALL_CHANNELS)        # 63

# ── Frame Format ─────────────────────────────────────────────────
FRAME_HEADER_SIZE = 6          # 4 (timestamp) + 1 (flags) + 1 (sequence)
FRAME_PAYLOAD_SIZE = NUM_TOTAL_FLOATS * 4   # 63 * 4 = 252 bytes
FRAME_TOTAL_SIZE = FRAME_HEADER_SIZE + FRAME_PAYLOAD_SIZE  # 258 bytes

# ── Streaming ────────────────────────────────────────────────────
TARGET_FPS = 30
KEYFRAME_INTERVAL = 30         # Full keyframe every 30 frames (1 second)
JITTER_BUFFER_MIN = 2          # Min frames in client jitter buffer
JITTER_BUFFER_MAX = 3          # Max frames in client jitter buffer

# ── Parameter Ranges ─────────────────────────────────────────────
PARAM_RANGE_MIN = -3.0
PARAM_RANGE_MAX = 3.0

# ── Texture ──────────────────────────────────────────────────────
TEXTURE_RESOLUTION = 1024      # 1024x1024 UV texture map

# ── Calibration ──────────────────────────────────────────────────
CALIBRATION_SHOTS = [
    {"name": "front_neutral",    "angle": "0deg",   "expression": "neutral",      "description": "Front-facing, neutral expression"},
    {"name": "left_quarter",     "angle": "-30deg",  "expression": "neutral",      "description": "Slight left turn (~30 degrees)"},
    {"name": "right_quarter",    "angle": "+30deg",  "expression": "neutral",      "description": "Slight right turn (~30 degrees)"},
    {"name": "front_mouth_open", "angle": "0deg",   "expression": "mouth_open",   "description": "Front-facing, mouth open wide"},
    {"name": "front_smile",      "angle": "0deg",   "expression": "slight_smile",  "description": "Front-facing, slight natural smile"},
]

QUALITY_GATES = [
    "face_detected",
    "single_face",
    "face_size_adequate",
    "angle_matches_target",
    "sufficient_lighting",
    "no_occlusion",
    "expression_matches_target",
]

# ── Min Photo Resolution ─────────────────────────────────────────
MIN_PHOTO_WIDTH = 512
MIN_PHOTO_HEIGHT = 512
