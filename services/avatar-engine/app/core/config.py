"""Avatar Engine configuration — loaded from environment."""
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # ── Mode ─────────────────────────────────────────────────
    DEV_MODE: bool = Field(
        default=False,
        description="Skip MuseTalk, use StubRenderer — CPU only, no weights needed"
    )

    # ── Hardware ─────────────────────────────────────────────
    DEVICE: str = Field(default="cuda", description="cuda or cpu")
    FPS_TARGET: int = Field(default=25)
    FACE_SIZE: int = Field(default=256, description="MuseTalk inference resolution")

    # ── Paths ────────────────────────────────────────────────
    MODEL_DIR: str = Field(default="/app/models")
    UPLOAD_DIR: str = Field(default="/app/uploads")

    # ── Redis ────────────────────────────────────────────────
    REDIS_URL: str = Field(default="redis://localhost:6379")

    # ── MuseTalk model paths (relative to MODEL_DIR) ─────────
    MUSETALK_CONFIG: str = Field(default="musetalk/musetalk.json")
    MUSETALK_WEIGHTS: str = Field(default="musetalk/pytorch_model.bin")
    VAE_DIR: str = Field(default="musetalk/sd-vae-ft-mse")
    WHISPER_DIR: str = Field(default="musetalk/whisper")
    DWPOSE_WEIGHTS: str = Field(default="dwpose/dw-ll_ucoco_384.pth")
    GFPGAN_WEIGHTS: str = Field(default="gfpgan/GFPGANv1.4.pth")

    # ── Inference ────────────────────────────────────────────
    BATCH_SIZE: int = Field(default=4, description="Frames per MuseTalk forward pass")
    USE_HALF_PRECISION: bool = Field(default=True, description="fp16 for speed")
    ENABLE_UPSCALER: bool = Field(default=False, description="GFPGAN HD upscaling")

    # ── Expression layer ─────────────────────────────────────
    IDLE_YAW_AMPLITUDE: float = Field(default=0.015)
    IDLE_PITCH_AMPLITUDE: float = Field(default=0.010)
    IDLE_MOTION_SPEED: float = Field(default=0.3)
    BLINK_INTERVAL_MIN: float = Field(default=3.0, description="seconds")
    BLINK_INTERVAL_MAX: float = Field(default=6.0, description="seconds")
    MOTION_TRANSITION_MS: float = Field(default=300.0)

    # ── Logging ──────────────────────────────────────────────
    LOG_LEVEL: str = Field(default="info")

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
