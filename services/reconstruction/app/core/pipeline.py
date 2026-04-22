"""
Reconstruction pipeline — orchestrates quality gating + model inference.
Model selection is config-driven (swappable by changing RECON_MODEL env var).
"""

import logging
import os
from typing import Dict, Optional

import cv2
import numpy as np

from .base import ReconstructionInput, ReconstructionModel, ReconstructionOutput
from .config import config
from .quality_gate import QualityGate

logger = logging.getLogger(__name__)


def _load_model(model_name: str) -> ReconstructionModel:
    """Factory: load the configured reconstruction model."""
    if model_name == "stub":
        from .stub_reconstructor import StubReconstructor
        return StubReconstructor()
    elif model_name == "mica":
        # Future: from .mica_reconstructor import MICAReconstructor
        raise NotImplementedError("MICA reconstructor not yet implemented — use stub for dev")
    elif model_name == "deca":
        # Future: from .deca_reconstructor import DECAReconstructor
        raise NotImplementedError("DECA reconstructor not yet implemented — use stub for dev")
    elif model_name == "mica_deca":
        # Future: from .mica_deca_reconstructor import MICADECAReconstructor
        raise NotImplementedError("MICA+DECA reconstructor not yet implemented — use stub for dev")
    else:
        raise ValueError(f"Unknown reconstruction model: {model_name}")


class ReconstructionPipeline:
    """
    Main reconstruction pipeline.

    Flow:
    1. Validate photos via quality gate
    2. Run reconstruction model (config-selected)
    3. (Optional) Enhance texture
    4. Return GLB + metadata
    """

    def __init__(self):
        self._model: Optional[ReconstructionModel] = None
        self._quality_gate = QualityGate(
            min_face_ratio=config.MIN_FACE_SIZE_RATIO,
            min_quality=config.MIN_QUALITY_SCORE,
        )
        self._ready = False

    async def initialize(self):
        """Load model and prepare pipeline."""
        logger.info(f"Initializing reconstruction pipeline (model={config.RECON_MODEL}, device={config.DEVICE})")

        # Initialize quality gate
        self._quality_gate.initialize()

        # Load the configured model
        self._model = _load_model(config.RECON_MODEL)
        await self._model.initialize(config.MODEL_DIR, config.DEVICE)

        # Ensure output directory exists
        os.makedirs(config.GLB_OUTPUT_DIR, exist_ok=True)

        self._ready = True
        logger.info(f"Reconstruction pipeline ready (model={self._model.name})")

    async def shutdown(self):
        """Release resources."""
        if self._model:
            await self._model.shutdown()
        self._ready = False

    def is_ready(self) -> bool:
        return self._ready and self._model is not None and self._model.is_ready()

    def validate_photos(
        self,
        photos: Dict[str, np.ndarray],
    ) -> Dict[str, dict]:
        """
        Run quality gates on all calibration photos.

        Args:
            photos: {shot_name: BGR image}

        Returns:
            {shot_name: quality_report}
        """
        results = {}
        for shot_name, image in photos.items():
            results[shot_name] = self._quality_gate.validate_photo(image, shot_name)
        return results

    async def reconstruct(
        self,
        session_id: str,
        photos: Dict[str, np.ndarray],
        skip_quality_check: bool = False,
    ) -> ReconstructionOutput:
        """
        Full reconstruction pipeline.

        Args:
            session_id: Unique session ID
            photos: {shot_name: BGR image}
            skip_quality_check: Skip quality gates (for testing)

        Returns:
            ReconstructionOutput with GLB data
        """
        if not self._ready:
            raise RuntimeError("Pipeline not initialized")

        # 1. Quality gate
        if not skip_quality_check:
            quality_results = self.validate_photos(photos)
            failed = {
                name: result
                for name, result in quality_results.items()
                if not result["passed"]
            }
            if failed:
                failed_names = list(failed.keys())
                recommendations = []
                for r in failed.values():
                    recommendations.extend(r.get("recommendations", []))
                raise ValueError(
                    f"Quality check failed for: {failed_names}. "
                    f"Recommendations: {recommendations}"
                )

        # 2. Reconstruct
        input_data = ReconstructionInput(
            session_id=session_id,
            photos=photos,
        )
        output = await self._model.reconstruct(input_data)

        # 3. Save GLB to disk
        glb_path = os.path.join(config.GLB_OUTPUT_DIR, f"{session_id}.glb")
        with open(glb_path, "wb") as f:
            f.write(output.glb_data)
        logger.info(f"Saved GLB: {glb_path} ({len(output.glb_data)} bytes)")

        return output
