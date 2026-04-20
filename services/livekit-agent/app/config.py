from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # LiveKit
    LIVEKIT_URL: str        = Field(...)
    LIVEKIT_API_KEY: str    = Field(...)
    LIVEKIT_API_SECRET: str = Field(...)

    # AI providers
    OPENAI_API_KEY: str     = Field(...)
    DEEPGRAM_API_KEY: str   = Field(default="")
    ELEVENLABS_API_KEY: str = Field(default="")
    ELEVENLABS_VOICE_ID: str = Field(default="")

    # Agent behaviour
    LLM_MODEL: str          = Field(default="gpt-4o-mini")
    STT_PROVIDER: str       = Field(default="deepgram")   # deepgram | openai
    TTS_PROVIDER: str       = Field(default="openai")     # openai | elevenlabs
    AGENT_SYSTEM_PROMPT: str = Field(
        default="You are a helpful AI assistant. Be concise and conversational. Keep responses under 3 sentences."
    )

    # Redis
    REDIS_URL: str          = Field(default="redis://localhost:6379")

    # Audio
    AUDIO_SAMPLE_RATE: int  = Field(default=16000)
    AUDIO_CHANNELS: int     = Field(default=1)

    LOG_LEVEL: str          = Field(default="info")

    class Config:
        env_file = ".env"


settings = Settings()
