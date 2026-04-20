# ─────────────────────────────────────────────────────────────
#  Avatar Engine — GPU Service
#  Base: CUDA 11.8 + Python 3.10
# ─────────────────────────────────────────────────────────────
FROM nvidia/cuda:11.8.0-cudnn8-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1

# ── System deps ───────────────────────────────────────────────
RUN apt-get update && apt-get install -y \
    python3.10 python3.10-dev python3-pip \
    ffmpeg libgl1 libglib2.0-0 libsm6 libxext6 libxrender-dev \
    libgomp1 wget curl git \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/python3.10 /usr/bin/python3 && \
    ln -sf /usr/bin/python3 /usr/bin/python && \
    pip install --upgrade pip setuptools wheel

WORKDIR /app

# ── Python deps (cached layer) ────────────────────────────────
COPY requirements.txt .
RUN pip install torch==2.1.0 torchvision==0.16.0 torchaudio==2.1.0 \
    --index-url https://download.pytorch.org/whl/cu118

RUN pip install -r requirements.txt

# ── MediaPipe (separate — large download) ────────────────────
RUN pip install mediapipe==0.10.9

# ── App source ────────────────────────────────────────────────
COPY . .

# ── Model dir mount point ─────────────────────────────────────
RUN mkdir -p /app/models /app/uploads

EXPOSE 8001

HEALTHCHECK --interval=10s --timeout=5s --retries=10 --start-period=60s \
    CMD curl -f http://localhost:8001/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", \
     "--workers", "1", "--loop", "uvloop", "--http", "httptools"]
