# ─────────────────────────────────────────────────────────────
#  LiveKit Agent Service
#  Runs livekit-agents pipeline: STT → LLM → TTS
#  Publishes TTS audio PCM to Redis → avatar-engine
#  Publishes intent/motion state to Redis → avatar-engine
# ─────────────────────────────────────────────────────────────
FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y \
    ffmpeg gcc curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download livekit-agents model deps
RUN python -m livekit.agents download-files || true

COPY . .

# Agent runs in worker mode — connects to LiveKit server and waits for rooms
CMD ["python", "-m", "app.main", "start"]
