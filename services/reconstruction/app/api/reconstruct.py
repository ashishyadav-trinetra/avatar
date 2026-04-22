"""
Reconstruction API endpoints.
"""

import logging
import uuid
from typing import Dict, List

import cv2
import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..core.pipeline import ReconstructionPipeline

logger = logging.getLogger(__name__)
router = APIRouter()

# Pipeline instance — initialized by app lifespan
pipeline: ReconstructionPipeline = None


def set_pipeline(p: ReconstructionPipeline):
    global pipeline
    pipeline = p


@router.post("/reconstruct")
async def reconstruct_avatar(
    session_id: str = Form(None),
    front_neutral: UploadFile = File(...),
    left_quarter: UploadFile = File(None),
    right_quarter: UploadFile = File(None),
    front_mouth_open: UploadFile = File(None),
    front_smile: UploadFile = File(None),
    skip_quality_check: bool = Form(False),
):
    """
    Reconstruct a 3D avatar from calibration photos.

    Required: front_neutral
    Optional (improve quality): left_quarter, right_quarter, front_mouth_open, front_smile

    Returns JSON with session_id and metadata. GLB downloadable via /avatar/{session_id}/glb
    """
    if not pipeline or not pipeline.is_ready():
        raise HTTPException(503, "Reconstruction pipeline not ready")

    if not session_id:
        session_id = str(uuid.uuid4())

    # Parse uploaded photos
    photos: Dict[str, np.ndarray] = {}
    uploads = {
        "front_neutral": front_neutral,
        "left_quarter": left_quarter,
        "right_quarter": right_quarter,
        "front_mouth_open": front_mouth_open,
        "front_smile": front_smile,
    }

    for shot_name, upload in uploads.items():
        if upload is None:
            continue
        data = await upload.read()
        if not data:
            continue
        arr = np.frombuffer(data, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise HTTPException(400, f"Could not decode image for {shot_name}")
        photos[shot_name] = img

    if not photos:
        raise HTTPException(400, "No valid photos provided")

    if "front_neutral" not in photos:
        raise HTTPException(400, "front_neutral photo is required")

    try:
        output = await pipeline.reconstruct(
            session_id=session_id,
            photos=photos,
            skip_quality_check=skip_quality_check,
        )
    except ValueError as e:
        # Quality gate failure
        raise HTTPException(422, str(e))
    except Exception as e:
        logger.exception("Reconstruction failed")
        raise HTTPException(500, f"Reconstruction error: {e}")

    return {
        "session_id": output.session_id,
        "model": output.model_name,
        "vertex_count": output.vertex_count,
        "face_count": output.face_count,
        "blendshape_count": output.blendshape_count,
        "mesh_version": output.mesh_version,
        "texture_version": output.texture_version,
        "checksum": output.checksum,
        "reconstruction_time_ms": output.reconstruction_time_ms,
        "glb_url": f"/avatar/{session_id}/glb",
    }


@router.post("/validate")
async def validate_photos(
    front_neutral: UploadFile = File(None),
    left_quarter: UploadFile = File(None),
    right_quarter: UploadFile = File(None),
    front_mouth_open: UploadFile = File(None),
    front_smile: UploadFile = File(None),
):
    """
    Validate calibration photos against quality gates WITHOUT running reconstruction.
    Use this for real-time feedback during the photo capture flow.
    """
    if not pipeline or not pipeline.is_ready():
        raise HTTPException(503, "Pipeline not ready")

    photos: Dict[str, np.ndarray] = {}
    uploads = {
        "front_neutral": front_neutral,
        "left_quarter": left_quarter,
        "right_quarter": right_quarter,
        "front_mouth_open": front_mouth_open,
        "front_smile": front_smile,
    }

    for shot_name, upload in uploads.items():
        if upload is None:
            continue
        data = await upload.read()
        if not data:
            continue
        arr = np.frombuffer(data, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is not None:
            photos[shot_name] = img

    if not photos:
        raise HTTPException(400, "No valid photos provided")

    results = pipeline.validate_photos(photos)

    all_passed = all(r["passed"] for r in results.values())
    return {
        "all_passed": all_passed,
        "results": results,
    }


@router.get("/avatar/{session_id}/glb")
async def download_glb(session_id: str):
    """Download the reconstructed GLB file."""
    import os
    from fastapi.responses import FileResponse

    from ..core.config import config

    glb_path = os.path.join(config.GLB_OUTPUT_DIR, f"{session_id}.glb")
    if not os.path.exists(glb_path):
        raise HTTPException(404, "Avatar not found")

    return FileResponse(
        glb_path,
        media_type="model/gltf-binary",
        filename=f"avatar_{session_id}.glb",
    )
