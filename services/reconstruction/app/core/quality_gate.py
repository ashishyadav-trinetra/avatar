"""
Quality gating service — validates calibration photos before reconstruction.
Rejects bad inputs early with structured feedback.
"""

import logging
from typing import List, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# MediaPipe is optional — quality gating degrades gracefully without it
try:
    import mediapipe as mp
    _HAS_MEDIAPIPE = hasattr(mp, 'solutions')
except ImportError:
    mp = None
    _HAS_MEDIAPIPE = False


class QualityGate:
    """
    Validates calibration photos against quality gates.
    Uses MediaPipe Face Mesh for detection, landmark analysis, and pose estimation.
    Falls back to basic OpenCV checks if MediaPipe is unavailable.
    """

    def __init__(self, min_face_ratio: float = 0.15, min_quality: float = 0.6):
        self.min_face_ratio = min_face_ratio
        self.min_quality = min_quality
        self._face_mesh = None
        self._face_detection = None
        self._cv_cascade = None
        self._available = False

    def initialize(self):
        """Initialize face detection models."""
        if _HAS_MEDIAPIPE:
            try:
                self._face_detection = mp.solutions.face_detection.FaceDetection(
                    model_selection=1,
                    min_detection_confidence=0.5,
                )
                self._face_mesh = mp.solutions.face_mesh.FaceMesh(
                    static_image_mode=True,
                    max_num_faces=1,
                    refine_landmarks=True,
                    min_detection_confidence=0.5,
                )
                self._available = True
                logger.info("QualityGate initialized with MediaPipe")
                return
            except Exception as e:
                logger.warning(f"MediaPipe init failed: {e}, falling back to OpenCV")

        # Fallback: OpenCV Haar cascade for basic face detection
        try:
            cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            self._cv_cascade = cv2.CascadeClassifier(cascade_path)
            self._available = True
            logger.info("QualityGate initialized with OpenCV Haar cascade (limited checks)")
        except Exception as e:
            logger.warning(f"OpenCV cascade init failed: {e}. Quality gating disabled — all photos will pass.")
            self._available = False

    def validate_photo(
        self,
        image: np.ndarray,
        expected_shot: str,
    ) -> dict:
        """
        Validate a single calibration photo.

        Returns:
            {
                "passed": bool,
                "score": float,  # 0-1
                "gates": [
                    {"name": str, "status": "pass"|"warn"|"fail", "message": str, "score": float}
                ],
                "recommendations": [str]
            }
        """
        h, w = image.shape[:2]
        gates = []
        recommendations = []

        # If quality gating is completely unavailable, pass everything
        if not self._available:
            gates.append({
                "name": "quality_gate_available",
                "status": "warn",
                "message": "Quality gating unavailable — photo accepted without validation",
                "score": 0.5,
            })
            return self._compile_result(gates, recommendations)

        # Use OpenCV fallback if MediaPipe is unavailable
        if self._face_detection is None and self._cv_cascade is not None:
            return self._validate_with_opencv(image, expected_shot)

        # ── Gate 1: Face detected ────────────────────────────
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        det_results = self._face_detection.process(rgb)

        if not det_results.detections:
            gates.append({
                "name": "face_detected",
                "status": "fail",
                "message": "No face detected in the photo",
                "score": 0.0,
            })
            return self._compile_result(gates, recommendations)

        gates.append({
            "name": "face_detected",
            "status": "pass",
            "message": "Face detected",
            "score": 1.0,
        })

        # ── Gate 2: Single face ──────────────────────────────
        num_faces = len(det_results.detections)
        if num_faces > 1:
            gates.append({
                "name": "single_face",
                "status": "fail",
                "message": f"Multiple faces detected ({num_faces}). Only one face should be visible.",
                "score": 0.0,
            })
            recommendations.append("Ensure only your face is visible in the photo")
        else:
            gates.append({
                "name": "single_face",
                "status": "pass",
                "message": "Single face confirmed",
                "score": 1.0,
            })

        # ── Gate 3: Face size adequate ───────────────────────
        detection = det_results.detections[0]
        bbox = detection.location_data.relative_bounding_box
        face_area_ratio = bbox.width * bbox.height

        if face_area_ratio < self.min_face_ratio:
            gates.append({
                "name": "face_size_adequate",
                "status": "fail",
                "message": f"Face is too small ({face_area_ratio:.1%} of image). Move closer to the camera.",
                "score": face_area_ratio / self.min_face_ratio,
            })
            recommendations.append("Move closer to the camera so your face fills more of the frame")
        else:
            gates.append({
                "name": "face_size_adequate",
                "status": "pass",
                "message": f"Face size OK ({face_area_ratio:.1%} of image)",
                "score": min(1.0, face_area_ratio / self.min_face_ratio),
            })

        # ── Gate 4: Angle matches target ─────────────────────
        mesh_results = self._face_mesh.process(rgb)
        if mesh_results.multi_face_landmarks:
            landmarks = mesh_results.multi_face_landmarks[0]
            yaw, pitch = self._estimate_head_pose(landmarks, w, h)

            angle_gate = self._check_angle(expected_shot, yaw, pitch)
            gates.append(angle_gate)
            if angle_gate["status"] == "fail":
                recommendations.append(angle_gate.get("recommendation", "Adjust your head angle"))
        else:
            gates.append({
                "name": "angle_matches_target",
                "status": "warn",
                "message": "Could not estimate head pose — face mesh not found",
                "score": 0.5,
            })

        # ── Gate 5: Sufficient lighting ──────────────────────
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        brightness = np.mean(gray)
        contrast = np.std(gray)

        if brightness < 60:
            gates.append({
                "name": "sufficient_lighting",
                "status": "fail",
                "message": f"Image too dark (brightness: {brightness:.0f}/255)",
                "score": brightness / 120,
            })
            recommendations.append("Move to a brighter area or turn on more lights")
        elif brightness > 220:
            gates.append({
                "name": "sufficient_lighting",
                "status": "warn",
                "message": f"Image overexposed (brightness: {brightness:.0f}/255)",
                "score": 0.7,
            })
            recommendations.append("Reduce lighting or move away from direct light")
        else:
            gates.append({
                "name": "sufficient_lighting",
                "status": "pass",
                "message": f"Good lighting (brightness: {brightness:.0f}, contrast: {contrast:.0f})",
                "score": 1.0,
            })

        # ── Gate 6: No occlusion ─────────────────────────────
        # Simple heuristic: check face detection confidence as proxy
        confidence = detection.score[0] if detection.score else 0.5
        if confidence < 0.7:
            gates.append({
                "name": "no_occlusion",
                "status": "warn",
                "message": f"Face may be partially occluded (confidence: {confidence:.2f})",
                "score": confidence,
            })
            recommendations.append("Remove glasses, hats, or anything covering your face")
        else:
            gates.append({
                "name": "no_occlusion",
                "status": "pass",
                "message": "No significant occlusion detected",
                "score": confidence,
            })

        # ── Gate 7: Expression matches target ────────────────
        if mesh_results.multi_face_landmarks:
            expr_gate = self._check_expression(
                expected_shot, landmarks, w, h
            )
            gates.append(expr_gate)
            if expr_gate["status"] == "fail":
                recommendations.append(expr_gate.get("recommendation", "Match the requested expression"))

        return self._compile_result(gates, recommendations)

    def _estimate_head_pose(self, landmarks, w: int, h: int) -> Tuple[float, float]:
        """Estimate yaw and pitch from face mesh landmarks."""
        # Key landmarks: nose tip (1), chin (152), left eye (33), right eye (263)
        nose = landmarks.landmark[1]
        left_eye = landmarks.landmark[33]
        right_eye = landmarks.landmark[263]

        # Yaw: horizontal offset of nose from eye midpoint
        eye_mid_x = (left_eye.x + right_eye.x) / 2
        yaw = (nose.x - eye_mid_x) * 2  # Rough radians

        # Pitch: vertical offset
        eye_mid_y = (left_eye.y + right_eye.y) / 2
        pitch = (nose.y - eye_mid_y - 0.05) * 2

        return yaw, pitch

    def _check_angle(self, shot_name: str, yaw: float, pitch: float) -> dict:
        """Check if head angle matches the expected calibration shot."""
        if "front" in shot_name:
            if abs(yaw) > 0.15:
                return {
                    "name": "angle_matches_target",
                    "status": "fail",
                    "message": f"Head is turned too far for a front shot (yaw: {yaw:.2f})",
                    "score": max(0, 1 - abs(yaw) / 0.3),
                    "recommendation": "Face the camera directly",
                }
        elif "left" in shot_name:
            if yaw > -0.05:
                return {
                    "name": "angle_matches_target",
                    "status": "fail",
                    "message": "Please turn your head slightly to the left",
                    "score": 0.3,
                    "recommendation": "Turn your head about 30 degrees to the left",
                }
        elif "right" in shot_name:
            if yaw < 0.05:
                return {
                    "name": "angle_matches_target",
                    "status": "fail",
                    "message": "Please turn your head slightly to the right",
                    "score": 0.3,
                    "recommendation": "Turn your head about 30 degrees to the right",
                }

        return {
            "name": "angle_matches_target",
            "status": "pass",
            "message": f"Head angle matches target (yaw: {yaw:.2f}, pitch: {pitch:.2f})",
            "score": 1.0,
        }

    def _check_expression(self, shot_name: str, landmarks, w: int, h: int) -> dict:
        """Check if expression matches the expected calibration shot."""
        # Measure mouth openness using landmarks
        upper_lip = landmarks.landmark[13]  # Upper lip center
        lower_lip = landmarks.landmark[14]  # Lower lip center
        mouth_open = abs(lower_lip.y - upper_lip.y) * h

        # Measure smile using mouth corner distance
        left_corner = landmarks.landmark[61]
        right_corner = landmarks.landmark[291]
        mouth_width = abs(right_corner.x - left_corner.x) * w

        if "mouth_open" in shot_name:
            if mouth_open < 15:
                return {
                    "name": "expression_matches_target",
                    "status": "fail",
                    "message": "Please open your mouth wider",
                    "score": mouth_open / 30,
                    "recommendation": "Open your mouth wide, like saying 'aah'",
                }
        elif "smile" in shot_name:
            # Smile typically widens the mouth
            if mouth_width < 40:
                return {
                    "name": "expression_matches_target",
                    "status": "warn",
                    "message": "Smile detected but could be bigger",
                    "score": 0.7,
                    "recommendation": "Try a natural, slight smile",
                }
        elif "neutral" in shot_name:
            if mouth_open > 20:
                return {
                    "name": "expression_matches_target",
                    "status": "warn",
                    "message": "Mouth appears open — try a neutral, relaxed expression",
                    "score": 0.7,
                    "recommendation": "Relax your face into a neutral expression",
                }

        return {
            "name": "expression_matches_target",
            "status": "pass",
            "message": "Expression matches target",
            "score": 1.0,
        }

    def _validate_with_opencv(self, image: np.ndarray, expected_shot: str) -> dict:
        """Fallback validation using OpenCV Haar cascade (basic face detection + lighting only)."""
        gates = []
        recommendations = []
        h, w = image.shape[:2]

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Face detection via Haar cascade
        faces = self._cv_cascade.detectMultiScale(gray, 1.1, 5, minSize=(50, 50))
        if len(faces) == 0:
            gates.append({"name": "face_detected", "status": "fail", "message": "No face detected", "score": 0.0})
            return self._compile_result(gates, ["Ensure your face is clearly visible"])

        gates.append({"name": "face_detected", "status": "pass", "message": "Face detected", "score": 1.0})

        if len(faces) > 1:
            gates.append({"name": "single_face", "status": "fail", "message": f"{len(faces)} faces found", "score": 0.0})
        else:
            gates.append({"name": "single_face", "status": "pass", "message": "Single face", "score": 1.0})

        # Face size check
        x, y, fw, fh = faces[0]
        face_ratio = (fw * fh) / (w * h)
        if face_ratio < self.min_face_ratio:
            gates.append({"name": "face_size_adequate", "status": "fail",
                          "message": f"Face too small ({face_ratio:.1%})", "score": face_ratio / self.min_face_ratio})
            recommendations.append("Move closer to the camera")
        else:
            gates.append({"name": "face_size_adequate", "status": "pass",
                          "message": f"Face size OK ({face_ratio:.1%})", "score": 1.0})

        # Lighting check
        brightness = np.mean(gray)
        if brightness < 60:
            gates.append({"name": "sufficient_lighting", "status": "fail",
                          "message": f"Too dark ({brightness:.0f}/255)", "score": brightness / 120})
            recommendations.append("Improve lighting")
        elif brightness > 220:
            gates.append({"name": "sufficient_lighting", "status": "warn",
                          "message": f"Overexposed ({brightness:.0f}/255)", "score": 0.7})
        else:
            gates.append({"name": "sufficient_lighting", "status": "pass",
                          "message": "Good lighting", "score": 1.0})

        return self._compile_result(gates, recommendations)

    def _compile_result(self, gates: list, recommendations: list) -> dict:
        """Compile gates into a final quality report."""
        scores = [g["score"] for g in gates]
        has_fail = any(g["status"] == "fail" for g in gates)
        overall = sum(scores) / len(scores) if scores else 0

        return {
            "passed": not has_fail and overall >= self.min_quality,
            "score": round(overall, 3),
            "gates": gates,
            "recommendations": recommendations,
        }
