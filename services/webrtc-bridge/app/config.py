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

    # When running in Docker, ICE candidates advertise the container's
    # internal IP (172.x.x.x) which the browser can't reach. Set this
    # to the host IP the browser can reach (e.g. "127.0.0.1" for local dev).
    ANNOUNCE_IP: str          = Field(default="")

    class Config:
        env_file = ".env"


settings = Settings()
