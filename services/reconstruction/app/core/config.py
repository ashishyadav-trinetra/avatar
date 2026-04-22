"""
Reconstruction service configuration.
"""

import os


class Config:
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")
    MODEL_DIR: str = os.getenv("MODEL_DIR", "/app/models")
    DEVICE: str = os.getenv("DEVICE", "cpu")
    DEV_MODE: bool = os.getenv("DEV_MODE", "false").lower() == "true"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "info")

    # Reconstruction model selection (swappable)
    RECON_MODEL: str = os.getenv("RECON_MODEL", "stub")  # stub | mica | deca | mica_deca
    TEXTURE_ENHANCER: str = os.getenv("TEXTURE_ENHANCER", "none")  # none | realesrgan | multiview

    # Output
    TEXTURE_RESOLUTION: int = int(os.getenv("TEXTURE_RESOLUTION", "1024"))
    GLB_OUTPUT_DIR: str = os.getenv("GLB_OUTPUT_DIR", "/app/outputs")

    # Quality gating thresholds
    MIN_FACE_SIZE_RATIO: float = float(os.getenv("MIN_FACE_SIZE_RATIO", "0.15"))  # Face must be ≥15% of image
    MIN_QUALITY_SCORE: float = float(os.getenv("MIN_QUALITY_SCORE", "0.6"))


config = Config()
