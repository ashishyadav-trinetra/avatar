"""Coefficient engine configuration."""

import os


class Config:
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")
    DEVICE: str = os.getenv("DEVICE", "cpu")
    DEV_MODE: bool = os.getenv("DEV_MODE", "false").lower() == "true"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "info")
    MODEL_DIR: str = os.getenv("MODEL_DIR", "/app/models")

    # Lip sync model selection (swappable)
    LIPSYNC_MODEL: str = os.getenv("LIPSYNC_MODEL", "stub")  # stub | faceformer | codetalker

    # Streaming
    TARGET_FPS: int = int(os.getenv("TARGET_FPS", "30"))
    KEYFRAME_INTERVAL: int = int(os.getenv("KEYFRAME_INTERVAL", "30"))

    # Behavior layer
    ENABLE_BLINKS: bool = os.getenv("ENABLE_BLINKS", "true").lower() == "true"
    ENABLE_HEAD_MOTION: bool = os.getenv("ENABLE_HEAD_MOTION", "true").lower() == "true"
    ENABLE_SACCADES: bool = os.getenv("ENABLE_SACCADES", "true").lower() == "true"
    ENABLE_BREATHING: bool = os.getenv("ENABLE_BREATHING", "true").lower() == "true"


config = Config()
