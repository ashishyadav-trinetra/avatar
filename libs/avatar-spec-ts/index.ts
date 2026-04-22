/**
 * Canonical Avatar Spec — TypeScript constants and types.
 * Frontend mirror of the Python avatar_spec package.
 * All channel ordering, frame format, and constants match exactly.
 */

// ── Spec Version ────────────────────────────────────────────────
export const SPEC_VERSION = "1.0.0";

// ── FLAME Mesh ──────────────────────────────────────────────────
export const FLAME_VERTEX_COUNT = 5023;
export const FLAME_FACE_COUNT = 9976;

// ── Blendshape Parameters ───────────────────────────────────────
export const EXPRESSION_PARAMS = Array.from({ length: 50 }, (_, i) => `exp_${i}`);
export const JAW_PARAMS = Array.from({ length: 6 }, (_, i) => `jaw_${i}`);
export const HEAD_POSE_CHANNELS = ["pitch", "yaw", "roll"] as const;
export const EYE_GAZE_CHANNELS = [
  "gaze_left_h", "gaze_left_v",
  "gaze_right_h", "gaze_right_v",
] as const;

export const ALL_CHANNELS = [
  ...EXPRESSION_PARAMS,
  ...JAW_PARAMS,
  ...HEAD_POSE_CHANNELS,
  ...EYE_GAZE_CHANNELS,
] as const;

export const NUM_EXPRESSION = 50;
export const NUM_JAW = 6;
export const NUM_HEAD_POSE = 3;
export const NUM_EYE_GAZE = 4;
export const NUM_TOTAL_FLOATS = 63;

// ── Frame Format ────────────────────────────────────────────────
export const FRAME_HEADER_SIZE = 6;
export const FRAME_PAYLOAD_SIZE = NUM_TOTAL_FLOATS * 4;  // 252
export const FRAME_TOTAL_SIZE = FRAME_HEADER_SIZE + FRAME_PAYLOAD_SIZE;  // 258

// ── Streaming ───────────────────────────────────────────────────
export const TARGET_FPS = 30;
export const KEYFRAME_INTERVAL = 30;
export const JITTER_BUFFER_MIN = 2;
export const JITTER_BUFFER_MAX = 3;

// ── Frame Flags ─────────────────────────────────────────────────
export const FrameFlags = {
  IS_DELTA:    0b00000001,
  IS_KEYFRAME: 0b00000010,
  IS_SPEAKING: 0b00000100,
} as const;

// ── Types ───────────────────────────────────────────────────────

export interface CoefficientFrame {
  timestampMs: number;
  sequence: number;
  flags: number;
  coefficients: Float32Array;  // length = NUM_TOTAL_FLOATS (63)
}

export interface CalibrationShot {
  name: string;
  angle: string;
  expression: string;
  description: string;
}

export const CALIBRATION_SHOTS: CalibrationShot[] = [
  { name: "front_neutral",    angle: "0deg",   expression: "neutral",      description: "Front-facing, neutral expression" },
  { name: "left_quarter",     angle: "-30deg",  expression: "neutral",      description: "Slight left turn (~30 degrees)" },
  { name: "right_quarter",    angle: "+30deg",  expression: "neutral",      description: "Slight right turn (~30 degrees)" },
  { name: "front_mouth_open", angle: "0deg",   expression: "mouth_open",   description: "Front-facing, mouth open wide" },
  { name: "front_smile",      angle: "0deg",   expression: "slight_smile",  description: "Front-facing, slight natural smile" },
];

export const QUALITY_GATES = [
  "face_detected",
  "single_face",
  "face_size_adequate",
  "angle_matches_target",
  "sufficient_lighting",
  "no_occlusion",
  "expression_matches_target",
] as const;

// ── Frame Codec ─────────────────────────────────────────────────

/**
 * Decode a binary coefficient frame (258 bytes) into a CoefficientFrame.
 */
export function decodeFrame(buffer: ArrayBuffer): CoefficientFrame {
  if (buffer.byteLength !== FRAME_TOTAL_SIZE) {
    throw new Error(`Expected ${FRAME_TOTAL_SIZE} bytes, got ${buffer.byteLength}`);
  }

  const view = new DataView(buffer);
  const timestampMs = view.getUint32(0, true);  // little-endian
  const flags = view.getUint8(4);
  const sequence = view.getUint8(5);

  const coefficients = new Float32Array(
    buffer.slice(FRAME_HEADER_SIZE, FRAME_TOTAL_SIZE)
  );

  return { timestampMs, sequence, flags, coefficients };
}

/**
 * Encode a CoefficientFrame to binary (258 bytes).
 */
export function encodeFrame(frame: CoefficientFrame): ArrayBuffer {
  const buffer = new ArrayBuffer(FRAME_TOTAL_SIZE);
  const view = new DataView(buffer);

  view.setUint32(0, frame.timestampMs, true);
  view.setUint8(4, frame.flags);
  view.setUint8(5, frame.sequence);

  const payload = new Float32Array(buffer, FRAME_HEADER_SIZE, NUM_TOTAL_FLOATS);
  payload.set(frame.coefficients);

  return buffer;
}

/**
 * Apply a delta frame on top of a previous frame's coefficients.
 */
export function applyDelta(
  delta: CoefficientFrame,
  previous: Float32Array,
): Float32Array {
  const result = new Float32Array(NUM_TOTAL_FLOATS);
  for (let i = 0; i < NUM_TOTAL_FLOATS; i++) {
    result[i] = previous[i] + delta.coefficients[i];
  }
  return result;
}

// ── Coefficient Accessors ───────────────────────────────────────

/** Get expression params (indices 0..49) from a coefficient array */
export function getExpression(coeffs: Float32Array): Float32Array {
  return coeffs.subarray(0, 50);
}

/** Get jaw params (indices 50..55) */
export function getJaw(coeffs: Float32Array): Float32Array {
  return coeffs.subarray(50, 56);
}

/** Get head pose [pitch, yaw, roll] (indices 56..58) */
export function getHeadPose(coeffs: Float32Array): Float32Array {
  return coeffs.subarray(56, 59);
}

/** Get eye gaze (indices 59..62) */
export function getEyeGaze(coeffs: Float32Array): Float32Array {
  return coeffs.subarray(59, 63);
}
