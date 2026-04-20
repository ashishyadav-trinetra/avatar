# ─────────────────────────────────────────────────────────────
#  WebRTC Bridge — CPU service
#  Receives JPEG frames from avatar-engine via WebSocket,
#  injects them into a WebRTC VideoStreamTrack via aiortc,
#  serves the WebRTC offer/answer signaling to the browser.
# ─────────────────────────────────────────────────────────────
FROM python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y \
    ffmpeg libavcodec-dev libavformat-dev libavutil-dev \
    libopus-dev libvpx-dev libssl-dev \
    gcc g++ curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8002

HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
    CMD curl -f http://localhost:8002/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002", \
     "--workers", "1", "--loop", "uvloop"]
