from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    REDIS_URL: str            = Field(default="redis://localhost:6379")
    AVATAR_ENGINE_URL: str    = Field(default="http://avatar-engine:8001")
    STUN_SERVER: str          = Field(default="stun:stun.l.google.com:19302")
    LOG_LEVEL: str            = Field(default="info")

    # UDP media port range exposed in docker-compose
    RTP_PORT_MIN: int         = Field(default=50000)
    RTP_PORT_MAX: int         = Field(default=50020)

    class Config:
        env_file = ".env"


settings = Settings()
