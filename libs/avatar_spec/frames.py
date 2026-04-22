"""
Binary coefficient frame encoding/decoding.

Frame layout (258 bytes total):
  Header (6 bytes):
    [0..3]  uint32 LE  — timestamp in milliseconds
    [4]     uint8      — flags (bit 0: is_delta, bit 1: is_keyframe, bit 2: is_speaking)
    [5]     uint8      — sequence number (0-255, rolling)
  Payload (252 bytes):
    [6..257] float32 LE array — 63 coefficient values in canonical order
"""

import struct
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .constants import (
    NUM_TOTAL_FLOATS,
    FRAME_HEADER_SIZE,
    FRAME_PAYLOAD_SIZE,
    FRAME_TOTAL_SIZE,
)


class FrameFlags:
    """Bitmask flags for coefficient frames."""
    IS_DELTA    = 0b00000001   # Payload contains deltas from previous frame
    IS_KEYFRAME = 0b00000010   # Full absolute values (not delta)
    IS_SPEAKING = 0b00000100   # Audio-driven coefficients active


@dataclass
class CoefficientFrame:
    """A single coefficient frame with header metadata."""
    timestamp_ms: int                          # Server timestamp
    sequence: int                              # Rolling 0-255
    flags: int = FrameFlags.IS_KEYFRAME        # Default to keyframe
    coefficients: np.ndarray = field(
        default_factory=lambda: np.zeros(NUM_TOTAL_FLOATS, dtype=np.float32)
    )

    @property
    def is_delta(self) -> bool:
        return bool(self.flags & FrameFlags.IS_DELTA)

    @property
    def is_keyframe(self) -> bool:
        return bool(self.flags & FrameFlags.IS_KEYFRAME)

    @property
    def is_speaking(self) -> bool:
        return bool(self.flags & FrameFlags.IS_SPEAKING)

    # ── Sliced views into the coefficient array ──────────────
    @property
    def expression(self) -> np.ndarray:
        return self.coefficients[0:50]

    @property
    def jaw(self) -> np.ndarray:
        return self.coefficients[50:56]

    @property
    def head_pose(self) -> np.ndarray:
        return self.coefficients[56:59]

    @property
    def eye_gaze(self) -> np.ndarray:
        return self.coefficients[59:63]


def encode_frame(frame: CoefficientFrame) -> bytes:
    """Encode a CoefficientFrame to binary (258 bytes)."""
    header = struct.pack(
        "<IBB",
        frame.timestamp_ms & 0xFFFFFFFF,
        frame.flags & 0xFF,
        frame.sequence & 0xFF,
    )
    payload = frame.coefficients.astype(np.float32).tobytes()
    assert len(payload) == FRAME_PAYLOAD_SIZE, f"Payload size mismatch: {len(payload)} != {FRAME_PAYLOAD_SIZE}"
    return header + payload


def decode_frame(data: bytes) -> CoefficientFrame:
    """Decode binary data (258 bytes) into a CoefficientFrame."""
    if len(data) != FRAME_TOTAL_SIZE:
        raise ValueError(f"Expected {FRAME_TOTAL_SIZE} bytes, got {len(data)}")

    timestamp_ms, flags, sequence = struct.unpack("<IBB", data[:FRAME_HEADER_SIZE])
    coefficients = np.frombuffer(data[FRAME_HEADER_SIZE:], dtype=np.float32).copy()

    return CoefficientFrame(
        timestamp_ms=timestamp_ms,
        sequence=sequence,
        flags=flags,
        coefficients=coefficients,
    )


def make_delta_frame(
    current: CoefficientFrame,
    previous: CoefficientFrame,
) -> CoefficientFrame:
    """Create a delta-compressed frame from current and previous frames."""
    delta = current.coefficients - previous.coefficients
    return CoefficientFrame(
        timestamp_ms=current.timestamp_ms,
        sequence=current.sequence,
        flags=(current.flags & ~FrameFlags.IS_KEYFRAME) | FrameFlags.IS_DELTA,
        coefficients=delta,
    )


def apply_delta_frame(
    delta: CoefficientFrame,
    previous: CoefficientFrame,
) -> CoefficientFrame:
    """Reconstruct absolute frame from delta and previous frame."""
    return CoefficientFrame(
        timestamp_ms=delta.timestamp_ms,
        sequence=delta.sequence,
        flags=(delta.flags & ~FrameFlags.IS_DELTA) | FrameFlags.IS_KEYFRAME,
        coefficients=previous.coefficients + delta.coefficients,
    )
