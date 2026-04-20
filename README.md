# AI Avatar POC

Real-time AI avatar that lip-syncs to speech using MuseTalk 1.5 + MediaPipe expression layer, driven by a LiveKit voice agent.

```
User speaks → LiveKit Agent (STT→LLM→TTS) → audio PCM → Redis
                                                              ↓
                                              Avatar Engine (MuseTalk + MediaPipe)
                                                              ↓
                                              WebRTC Bridge (aiortc) → Browser video
```

---

## Requirements

| Requirement         | Minimum              | Recommended         |
|---------------------|----------------------|---------------------|
| GPU                 | RTX 3080 (10GB VRAM) | RTX 4090 / A100     |
| RAM                 | 16 GB                | 32 GB               |
| Disk                | 10 GB free           | 20 GB               |
| CUDA                | 11.8+                | 12.1                |
| Docker              | 24+                  | latest              |
| nvidia-docker2      | required             | required            |
| OS                  | Ubuntu 22.04         | Ubuntu 22.04        |

> **Windows users:** `make` commands may not work. See the [Windows Commands](#windows-commands-no-make-needed) section below for direct Docker equivalents.

---

## First-Time Setup

### 1. Install nvidia-docker2 (Linux/prod only)

```bash
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list \
  | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt-get update && sudo apt-get install -y nvidia-docker2
sudo systemctl restart docker
```

### 2. Clone and configure

```bash
git clone <your-repo>
cd avatar-poc
cp .env.example .env        # Linux/Mac
copy .env.example .env      # Windows PowerShell
```

Edit `.env` with your credentials:
```env
LIVEKIT_URL=wss://your-server.livekit.cloud
LIVEKIT_API_KEY=your_api_key
LIVEKIT_API_SECRET=your_api_secret
OPENAI_API_KEY=sk-...
```

### 3. Build and start (Linux/Mac)

```bash
make setup-dev   # first time — builds images
make dev         # start the stack
```

### 3. Build and start (Windows PowerShell)

```powershell
docker compose -f docker-compose.dev.yml build
docker compose -f docker-compose.dev.yml up -d
```

Open **http://localhost:3000**

---

## Usage

1. Open the app in your browser
2. Upload a front-facing photo (ideally 512x512+, good lighting)
3. Click **Start Call**
4. Wait ~10 seconds for avatar to initialize
5. Speak — the avatar responds with lip-sync and expression

---

## Services

| Service          | Port  | Purpose                            |
|------------------|-------|------------------------------------|
| `frontend`       | 3000  | React UI                           |
| `api-gateway`    | 8000  | REST API, session orchestration    |
| `webrtc-bridge`  | 8002  | WebRTC signaling + frame injection |
| `avatar-engine`  | 8001  | MuseTalk + MediaPipe (GPU)         |
| `livekit-agent`  | —     | LiveKit STT→LLM→TTS worker         |
| `redis`          | 6379  | Internal pub/sub                   |

---

## Common Commands

### Linux / Mac (make)

```bash
# Dev
make dev                 # start dev stack
make dev-stop            # stop dev stack
make dev-logs            # tail all logs
make dev-restart         # restart everything
make logs-avatar-engine  # tail one service
make shell-avatar-engine # bash into container

# Prod
make prod                # start prod stack
make prod-stop           # stop prod stack
make prod-logs           # tail prod logs
make gpu-check           # verify GPU accessible
```

### Windows PowerShell (direct Docker commands)

```powershell
# Dev — start / stop / restart
docker compose -f docker-compose.dev.yml up -d
docker compose -f docker-compose.dev.yml down
docker compose -f docker-compose.dev.yml down; docker compose -f docker-compose.dev.yml up -d

# Dev — logs
docker compose -f docker-compose.dev.yml logs -f
docker compose -f docker-compose.dev.yml logs -f avatar-engine
docker compose -f docker-compose.dev.yml logs -f livekit-agent

# Dev — shell into a container
docker compose -f docker-compose.dev.yml exec avatar-engine /bin/bash

# Prod — start / stop
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
docker compose -f docker-compose.prod.yml --env-file .env.prod down
docker compose -f docker-compose.prod.yml --env-file .env.prod logs -f
```

---

## Windows Commands (no make needed)

If `make` is unavailable on Windows, every operation maps to a direct Docker command:

| What you want to do | Windows PowerShell command |
|---|---|
| First-time dev build | `docker compose -f docker-compose.dev.yml build` |
| Start dev stack | `docker compose -f docker-compose.dev.yml up -d` |
| Stop dev stack | `docker compose -f docker-compose.dev.yml down` |
| Watch all logs | `docker compose -f docker-compose.dev.yml logs -f` |
| Watch one service log | `docker compose -f docker-compose.dev.yml logs -f avatar-engine` |
| Restart everything | `docker compose -f docker-compose.dev.yml down; docker compose -f docker-compose.dev.yml up -d` |
| Bash into container | `docker compose -f docker-compose.dev.yml exec avatar-engine /bin/bash` |
| Check running services | `docker compose -f docker-compose.dev.yml ps` |
| First-time prod build | `docker compose -f docker-compose.prod.yml --env-file .env.prod build` |
| Start prod stack | `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d` |
| Stop prod stack | `docker compose -f docker-compose.prod.yml --env-file .env.prod down` |
| Watch prod logs | `docker compose -f docker-compose.prod.yml --env-file .env.prod logs -f` |

---

## Architecture

### Data flow per frame (~40ms on RTX 4090)

```
t=0ms    TTS audio chunk arrives via Redis
t=1ms    AudioEncoder (Whisper-tiny) → mel features
t=2ms    ExpressionLayer (MediaPipe affine warp) → animated ref frame
t=35ms   MuseTalk UNet inpaint → lip-synced frame
t=36ms   JPEG encode → Redis publish
t=37ms   WebRTC bridge pulls frame → RTP packetize
t=50ms   Browser receives frame → renders in <video>
```

### Expression layer states

| State      | Trigger keywords           | Motion                            |
|------------|----------------------------|-----------------------------------|
| `neutral`  | (default)                  | Subtle idle drift                 |
| `nodding`  | yes, correct, understood   | Pitch oscillation, brow raise     |
| `thinking` | think, consider, depends   | Head tilt, slight brow furrow     |
| `engaged`  | great, absolutely, exactly | Forward lean sim, brow raise      |
| `empathic` | understand, sorry, concern | Chin down, strong brow raise      |
| `listening`| (short responses)          | Minimal motion, attentive         |

---

## Swapping TTS / STT / LLM

All providers configured via `.env`:

```env
TTS_PROVIDER=openai      # openai | elevenlabs
STT_PROVIDER=deepgram    # deepgram | openai
LLM_MODEL=gpt-4o-mini   # gpt-4o-mini | gpt-4o | claude-3-5-haiku
```

---

## GPU Cloud Setup (RunPod)

1. Create a pod with **NVIDIA RTX 4090**, template: `RunPod PyTorch 2.1`
2. Expose ports: 3000, 8000, 8002, 50000-50020/UDP
3. SSH in, clone repo
4. Set credentials in `.env.prod`
5. Run: `bash scripts/download_models.sh`
6. Run: `docker compose -f docker-compose.prod.yml --env-file .env.prod build`
7. Run: `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d`

---

## Troubleshooting

**No face detected on upload**
→ Use a clear front-facing photo, face taking up >40% of frame

**WebRTC video not appearing**
→ Check browser mic/camera permissions
→ Verify ports 50000-50020/UDP are open
→ Logs: `docker compose -f docker-compose.dev.yml logs -f webrtc-bridge`

**LiveKit agent not responding**
→ Verify `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` in `.env`
→ Logs: `docker compose -f docker-compose.dev.yml logs -f livekit-agent`

**GPU OOM error (prod)**
→ Set `USE_HALF_PRECISION=true` in `.env.prod`
→ Set `BATCH_SIZE=2`
→ Check: `nvidia-smi`

**"DEV MODE" watermark showing**
→ This is expected in dev. Disappears in prod when `DEV_MODE=false`

**make not working on Windows**
→ Use the direct Docker commands from the Windows Commands table above
→ Or run: `winget install GnuWin32.Make` then add `C:\Program Files (x86)\GnuWin32\bin` to PATH
