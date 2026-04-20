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

---

## First-Time Setup

### 1. Install nvidia-docker2 (if not already installed)

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
cp .env.example .env
```

Edit `.env` with your credentials:
```env
LIVEKIT_URL=wss://your-server.livekit.cloud
LIVEKIT_API_KEY=your_api_key
LIVEKIT_API_SECRET=your_api_secret
OPENAI_API_KEY=sk-...
```

### 3. Run setup (downloads models + builds images)

```bash
make setup
```

This will:
- Download ~3.5 GB of model weights into `./models/`
- Build all Docker images

### 4. Start

```bash
make run
```

Open **http://localhost:3000**

---

## Usage

1. Open the app in your browser
2. Upload a front-facing photo (ideally 512×512+, good lighting)
3. Click **Start Call**
4. Wait ~5 seconds for avatar to initialize
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

```bash
make logs               # tail all logs
make logs-avatar-engine # tail one service
make stop               # stop everything
make restart            # restart everything
make gpu-check          # verify GPU is accessible
make shell-avatar-engine # bash into container
```

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

The LLM response is classified into one of:

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

All providers are configured via `.env`:

```env
# TTS options: openai | elevenlabs
TTS_PROVIDER=openai

# STT options: deepgram | openai
STT_PROVIDER=deepgram

# LLM options: gpt-4o-mini | gpt-4o | claude-3-5-haiku
LLM_MODEL=gpt-4o-mini
```

---

## GPU Cloud Setup (RunPod)

1. Create a pod with **NVIDIA RTX 4090**, template: `RunPod PyTorch 2.1`
2. Expose ports: 3000, 8000, 8002, 50000-50020/UDP
3. SSH in, clone repo, follow setup above
4. Set `VITE_API_URL` and `VITE_WEBRTC_URL` to your pod's public IP

---

## Integrating Vapi / Retell (later)

The `api-gateway` exposes a stub webhook at `POST /api/webhook/vapi`.
When you're ready to replace the LiveKit agent with Vapi:

1. Configure Vapi to POST audio chunks to `/api/webhook/vapi?session_id=<id>`
2. The gateway forwards PCM to Redis → avatar engine picks it up
3. Disable the `livekit-agent` service in `docker-compose.yml`

---

## Troubleshooting

**No face detected on upload**
→ Use a clear front-facing photo, good lighting, face taking up >40% of frame

**GPU OOM error**
→ Set `USE_HALF_PRECISION=true` in `.env` (default)
→ Reduce `FACE_SIZE=256` (default, don't increase on small GPUs)
→ Reduce `BATCH_SIZE=2`

**WebRTC video not appearing**
→ Check browser allows camera/mic permissions
→ Verify ports 50000-50020/UDP are open on your firewall
→ Check `make logs-webrtc-bridge`

**LiveKit agent not responding**
→ Verify `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` in `.env`
→ Check `make logs-livekit-agent`
