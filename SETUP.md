# AI Avatar POC — Complete Setup & Documentation

---

## Table of Contents

1. [What You Need Before Starting](#1-what-you-need-before-starting)
2. [Project Structure — Every File Explained](#2-project-structure--every-file-explained)
3. [Development Setup (No GPU)](#3-development-setup-no-gpu)
4. [Production Setup (GPU Required)](#4-production-setup-gpu-required)
5. [Environment Variables — Every Field Explained](#5-environment-variables--every-field-explained)
6. [Service Architecture](#6-service-architecture)
7. [Code Reference — Every Function Explained](#7-code-reference--every-function-explained)
8. [Avatar Photo Requirements](#8-avatar-photo-requirements)
9. [What You Do NOT Need](#9-what-you-do-not-need)
10. [Troubleshooting](#10-troubleshooting)
11. [Dev vs Prod Differences](#11-dev-vs-prod-differences)

---

## 1. What You Need Before Starting

### API Credentials (REQUIRED — get these first)

| Credential | Where to get | Cost |
|---|---|---|
| `LIVEKIT_URL` | [cloud.livekit.io](https://cloud.livekit.io) → create project | Free tier available |
| `LIVEKIT_API_KEY` | Same LiveKit dashboard | Free tier available |
| `LIVEKIT_API_SECRET` | Same LiveKit dashboard | Free tier available |
| `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com) | ~$0.01 per conversation |

That is **all you need** for dev mode. Everything else is optional.

### Optional credentials

| Credential | Purpose | Without it |
|---|---|---|
| `DEEPGRAM_API_KEY` | Better STT (speech-to-text) | Falls back to OpenAI Whisper |
| `ELEVENLABS_API_KEY` | Higher quality TTS voice | Falls back to OpenAI TTS |
| `ELEVENLABS_VOICE_ID` | Specific ElevenLabs voice | Uses default voice |

### Hardware

| Mode | GPU | RAM | Disk |
|---|---|---|---|
| **Dev** | None needed | 8 GB | 5 GB |
| **Prod** | NVIDIA RTX 3080+ (10GB VRAM min) | 16 GB | 15 GB |
| **Prod (recommended)** | RTX 4090 / A100 | 32 GB | 20 GB |

### Software (both modes)

- Docker 24+ with Docker Compose v2
- `git`
- A modern browser (Chrome / Firefox)

### Software (prod only)

- NVIDIA driver ≥ 525
- CUDA 11.8+
- `nvidia-docker2` (see Section 4)

---

## 2. Project Structure — Every File Explained

```
avatar-poc/
│
├── .env.example              ← Template for all credentials
├── .env                      ← Your dev credentials (gitignored)
├── .env.prod                 ← Your prod credentials (gitignored)
├── .gitignore
├── Makefile                  ← All commands (make dev / make prod / etc)
├── README.md
├── SETUP.md                  ← This file
│
├── docker-compose.dev.yml    ← Dev stack (CPU, stub renderer, hot reload)
├── docker-compose.prod.yml   ← Prod stack (GPU, MuseTalk, nginx)
│
├── scripts/
│   └── download_models.sh    ← Downloads ~3.5GB of model weights (prod only)
│
├── models/                   ← Downloaded weights live here (gitignored)
│   ├── musetalk/             ← MuseTalk UNet + VAE + Whisper
│   ├── dwpose/               ← Face/body detection
│   └── gfpgan/               ← Optional HD upscaler
│
└── services/
    ├── avatar-engine/        ← GPU service: MuseTalk + expression layer
    ├── webrtc-bridge/        ← WebRTC signaling + frame streaming
    ├── livekit-agent/        ← LiveKit STT→LLM→TTS pipeline
    ├── api-gateway/          ← REST API for frontend
    └── frontend/             ← React app
```

### services/avatar-engine/

```
avatar-engine/
├── Dockerfile                ← Production: CUDA 11.8 base image
├── Dockerfile.dev            ← Dev: python:3.10-slim, CPU torch
├── requirements.txt          ← Prod deps (GPU torch, onnxruntime-gpu)
├── requirements.dev.txt      ← Dev deps (CPU torch, no GPU packages)
└── app/
    ├── main.py               ← FastAPI app entry, lifespan startup
    ├── core/
    │   ├── config.py         ← All settings from environment variables
    │   ├── pipeline.py       ← Orchestrator: sessions, Redis pub/sub, render loops
    │   ├── musetalk.py       ← MuseTalk UNet inference wrapper (prod)
    │   ├── expression_layer.py ← MediaPipe landmarks + affine warp (all modes)
    │   └── stub_renderer.py  ← Dev replacement for MuseTalk (CPU only)
    └── api/
        ├── health.py         ← GET /health
        ├── avatar.py         ← POST /avatar/session (photo upload)
        └── frames.py         ← WebSocket /frames/ws/{session_id}
```

### services/webrtc-bridge/

```
webrtc-bridge/
├── Dockerfile
├── requirements.txt
└── app/
    ├── main.py               ← FastAPI app
    ├── config.py             ← Settings
    ├── health.py             ← GET /health
    └── signaling.py          ← POST /webrtc/offer/{session_id}
                                 AvatarVideoTrack (aiortc)
```

### services/livekit-agent/

```
livekit-agent/
├── Dockerfile
├── requirements.txt
└── app/
    ├── config.py             ← LiveKit + provider settings
    ├── intent_classifier.py  ← Text → motion state (NEUTRAL/NODDING/etc)
    └── main.py               ← LiveKit worker entrypoint
                                 VoiceAssistant setup
                                 TTS audio → Redis publisher
```

### services/api-gateway/

```
api-gateway/
├── Dockerfile
├── requirements.txt
└── app/
    └── main.py               ← POST /api/session/start
                                 DELETE /api/session/{id}
                                 GET /api/livekit/token
```

### services/frontend/

```
frontend/
├── Dockerfile                ← Prod: Vite build + nginx
├── Dockerfile.dev            ← Dev: Vite dev server with HMR
├── nginx.conf                ← Nginx SPA config
├── package.json
├── vite.config.ts
└── src/
    ├── main.tsx              ← React root
    ├── App.tsx               ← Main component, session orchestration
    ├── index.css             ← Global CSS variables + base styles
    ├── store/
    │   └── avatarStore.ts    ← Zustand global state
    ├── hooks/
    │   ├── useWebRTC.ts      ← RTCPeerConnection management
    │   └── useLiveKit.ts     ← LiveKit Room connection
    ├── utils/
    │   └── api.ts            ← fetch wrappers for backend API
    └── components/
        ├── PhotoUploader.tsx ← Drag-and-drop photo input
        ├── AvatarVideo.tsx   ← WebRTC video element
        ├── Controls.tsx      ← MicButton, EndCallButton, StatusBadge
        └── TranscriptPanel.tsx ← Scrolling conversation history
```

---

## 3. Development Setup (No GPU)

### Step 1 — Get API credentials

Sign up for:
- [LiveKit Cloud](https://cloud.livekit.io) → create a project → copy URL, API Key, API Secret
- [OpenAI](https://platform.openai.com) → create API key

### Step 2 — Clone and configure

**Linux / Mac:**
```bash
git clone <your-repo-url>
cd avatar-poc
cp .env.example .env
```

**Windows PowerShell:**
```powershell
git clone <your-repo-url>
cd avatar-poc
copy .env.example .env
notepad .env
```

Open `.env` and fill in **only these 4 lines** to get started:

```env
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=APIxxxxxxxxxx
LIVEKIT_API_SECRET=your_secret_here
OPENAI_API_KEY=sk-proj-...
```

Leave everything else at defaults.

### Step 3 — Build dev images

**Linux / Mac:**
```bash
make setup-dev
```

**Windows PowerShell:**
```powershell
docker compose -f docker-compose.dev.yml build
```

This builds the CPU-only Docker images (~3–5 minutes, downloads ~1GB of Python packages).
It does NOT download the 3.5GB model weights — those are only needed for prod.

### Step 4 — Start

**Linux / Mac:**
```bash
make dev
```

**Windows PowerShell:**
```powershell
docker compose -f docker-compose.dev.yml up -d
```

Services start up. Open **http://localhost:3000**

**Windows — open browser automatically:**
```powershell
Start-Process "http://localhost:3000"
```

### Step 5 — Test it

1. Upload any face photo (see Section 8 for photo tips)
2. Click **Start Call**
3. Wait ~10 seconds for the dev stack to initialize
4. Talk — you'll see the avatar with a **"DEV MODE"** watermark
5. The mouth will animate (stub renderer, not real lip-sync)
6. The LiveKit agent will respond via voice

### What dev mode does differently

The dev stack replaces MuseTalk with `StubRenderer` (in `stub_renderer.py`).
Instead of GPU-accelerated lip-sync, it draws an animated oval mouth using OpenCV.
You will see a **"DEV MODE"** green text watermark on the avatar.

Everything else is real and identical to prod:
- LiveKit agent runs real STT + LLM + TTS
- Redis pub/sub is live
- WebRTC stream is real
- Expression layer (head motion, blink) runs
- Intent classification runs

### Useful dev commands

**Linux / Mac (make):**
```bash
make dev-logs                    # watch all service output
make logs-avatar-engine          # watch just avatar engine
make logs-livekit-agent          # watch the LLM/TTS agent
make shell-avatar-engine         # bash into the container
make dev-stop                    # stop everything
make dev-restart                 # restart everything
```

**Windows PowerShell (direct Docker commands):**
```powershell
# Watch all logs
docker compose -f docker-compose.dev.yml logs -f

# Watch one service
docker compose -f docker-compose.dev.yml logs -f avatar-engine
docker compose -f docker-compose.dev.yml logs -f livekit-agent
docker compose -f docker-compose.dev.yml logs -f webrtc-bridge
docker compose -f docker-compose.dev.yml logs -f api-gateway

# Bash into a container
docker compose -f docker-compose.dev.yml exec avatar-engine /bin/bash

# Stop everything
docker compose -f docker-compose.dev.yml down

# Restart everything
docker compose -f docker-compose.dev.yml down
docker compose -f docker-compose.dev.yml up -d

# Check all service statuses
docker compose -f docker-compose.dev.yml ps
```

---

## 4. Production Setup (GPU Required)

> **Note:** Production runs on Linux (Ubuntu 22.04). The GPU machine should be Linux, not Windows.
> If you're using a cloud GPU (RunPod, Lambda Labs), you SSH into a Linux machine and run the Linux commands below.

### Step 1 — Install nvidia-docker2

```bash
# Ubuntu 22.04
distribution=$(. /etc/os-release; echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L "https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list" \
  | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt-get update
sudo apt-get install -y nvidia-docker2
sudo systemctl restart docker

# Verify:
docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi
```

You should see your GPU listed. If not, check your NVIDIA driver version:
```bash
nvidia-smi   # must show driver >= 525
```

### Step 2 — Create prod env file

```bash
cp .env.example .env.prod
```

Edit `.env.prod` — same 4 required credentials as dev, plus optional better providers:

```env
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=APIxxxxxxxxxx
LIVEKIT_API_SECRET=your_secret_here
OPENAI_API_KEY=sk-proj-...

# Optional but recommended for prod:
DEEPGRAM_API_KEY=your_deepgram_key     # better STT
ELEVENLABS_API_KEY=your_elevenlabs_key # better TTS voice
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM  # Rachel voice

# GPU tuning (defaults are fine to start):
FPS_TARGET=25
FACE_SIZE=256
ENABLE_UPSCALER=false
```

### Step 3 — Download models and build

**Linux / Mac (make):**
```bash
make setup-prod
```

**Linux / Mac (direct commands — same as make setup-prod):**
```bash
bash scripts/download_models.sh
docker compose -f docker-compose.prod.yml --env-file .env.prod build
```

This does:
1. Downloads all model weights (~3.5GB) into `./models/`
2. Builds production Docker images (~10–15 minutes)

Model download breakdown:
```
models/
├── musetalk/
│   ├── pytorch_model.bin        ~1.4 GB  <- MuseTalk UNet weights
│   ├── musetalk.json            ~2 KB    <- UNet architecture config
│   ├── sd-vae-ft-mse/
│   │   ├── diffusion_pytorch_model.bin  ~850 MB  <- VAE weights
│   │   └── config.json
│   ├── whisper/
│   │   ├── pytorch_model.bin    ~150 MB  <- Whisper-tiny audio encoder
│   │   └── config.json
│   └── face-parse-bisent/
│       └── 79999_iter.pth       ~50 MB   <- Face parsing
├── dwpose/
│   └── dw-ll_ucoco_384.pth     ~280 MB  <- Body/face pose detection
└── gfpgan/
    └── GFPGANv1.4.pth          ~350 MB  <- HD face upscaler (optional)

Total: ~3.0–3.5 GB
```

### Step 4 — Start production

**Linux / Mac (make):**
```bash
make prod
```

**Linux / Mac (direct commands):**
```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
```

The avatar-engine takes **60–90 seconds** to start (loading GPU models into VRAM).

**Watch progress:**

```bash
# make
make prod-logs

# direct
docker compose -f docker-compose.prod.yml --env-file .env.prod logs -f avatar-engine
```

When you see `Avatar Engine ready` in the logs, open **http://localhost:3000**

### Useful prod commands

**Linux / Mac (make):**
```bash
make prod-stop         # stop prod stack
make prod-restart      # restart prod stack
make prod-logs         # tail all prod logs
make logs-avatar-engine # tail avatar engine only
```

**Linux / Mac (direct commands):**
```bash
# Stop
docker compose -f docker-compose.prod.yml --env-file .env.prod down

# Restart
docker compose -f docker-compose.prod.yml --env-file .env.prod down
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d

# All logs
docker compose -f docker-compose.prod.yml --env-file .env.prod logs -f

# One service log
docker compose -f docker-compose.prod.yml --env-file .env.prod logs -f avatar-engine
```

### Production on a cloud GPU (RunPod / Lambda Labs)

1. Create instance with NVIDIA GPU (RTX 4090 recommended)
2. Template: `RunPod PyTorch 2.1` or `Ubuntu 22.04 + CUDA 11.8`
3. Open ports: `3000`, `8000`, `8002`, `50000-50020/UDP`
4. SSH in, clone repo, run the Linux commands above
5. Update `.env.prod`:
   ```env
   VITE_API_URL=http://YOUR_SERVER_IP:8000
   VITE_WEBRTC_URL=http://YOUR_SERVER_IP:8002
   ```
6. Start with `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d`

---

## 5. Environment Variables — Every Field Explained

### Required (both modes)

| Variable | Example | What it does |
|---|---|---|
| `LIVEKIT_URL` | `wss://project.livekit.cloud` | LiveKit server WebSocket URL |
| `LIVEKIT_API_KEY` | `APIxxxxxxxx` | LiveKit API key for token signing |
| `LIVEKIT_API_SECRET` | `secret_xxx` | LiveKit secret for token signing |
| `OPENAI_API_KEY` | `sk-proj-...` | Powers LLM (GPT-4o-mini) and TTS |

### Avatar engine

| Variable | Default | What it does |
|---|---|---|
| `AVATAR_DEVICE` | `cuda` (prod), `cpu` (dev) | Which device to run inference on |
| `DEV_MODE` | `false` (prod), `true` (dev) | If true, skips MuseTalk, uses stub |
| `FPS_TARGET` | `25` (prod), `10` (dev) | Target frames per second |
| `FACE_SIZE` | `256` | Resolution MuseTalk runs at (always 256) |
| `BATCH_SIZE` | `4` | Frames processed per GPU forward pass |
| `USE_HALF_PRECISION` | `true` | fp16 inference — faster, less VRAM |
| `ENABLE_UPSCALER` | `false` | Run GFPGAN after MuseTalk for HD output |

### Agent (LiveKit pipeline)

| Variable | Default | What it does |
|---|---|---|
| `STT_PROVIDER` | `openai` (dev), `deepgram` (prod) | Speech-to-text engine |
| `TTS_PROVIDER` | `openai` | Text-to-speech engine |
| `LLM_MODEL` | `gpt-4o-mini` | Which LLM the agent uses |
| `AGENT_SYSTEM_PROMPT` | (see .env.example) | Personality/instructions for the avatar |

### Optional providers

| Variable | When to set |
|---|---|
| `DEEPGRAM_API_KEY` | Set to use Deepgram STT (lower latency, better accuracy) |
| `ELEVENLABS_API_KEY` | Set to use ElevenLabs TTS (much better voice quality) |
| `ELEVENLABS_VOICE_ID` | Required if using ElevenLabs — pick from their voice library |

---

## 6. Service Architecture

### How the services connect

```
Browser
  │
  ├─ HTTP/REST ──────────────── api-gateway :8000
  │                                 │
  │                          forwards photo upload to avatar-engine
  │                          generates LiveKit JWT token
  │                          returns session_id + credentials
  │
  ├─ WebRTC signaling ────────── webrtc-bridge :8002
  │   (SDP offer/answer)             │
  │                          subscribes to Redis frames channel
  │                          injects JPEG frames into RTP stream
  │
  ├─ WebRTC video ◄──────────── webrtc-bridge :8002
  │   (live avatar video)
  │
  └─ LiveKit WebSocket ──────── LiveKit Cloud
       (mic audio + voice)          │
                               livekit-agent (worker)
                                    │
                               STT: transcribes user speech
                               LLM: generates response
                               TTS: synthesizes speech
                                    │
                               publishes PCM audio → Redis
                               publishes intent state → Redis

Redis (internal)
  avatar:audio:{id}      ← livekit-agent → avatar-engine
  avatar:intent:{id}     ← livekit-agent → avatar-engine
  avatar:frames:{id}     ← avatar-engine → webrtc-bridge

avatar-engine :8001
  Startup:
    1. Load MuseTalk weights (prod) or init StubRenderer (dev)
    2. Connect to Redis

  Per session (per uploaded photo):
    3. MediaPipe: extract 468 face landmarks
    4. MuseTalk: detect face bounding box
    5. Start render loop (background task)

  Render loop (every 1/FPS seconds):
    6. ExpressionLayer → animated reference frame (CPU)
    7. AudioEncoder → mel features from PCM chunk
    8. MuseTalk → lip-synced output frame (GPU)
    9. JPEG encode → publish to Redis
```

---

## 7. Code Reference — Every Function Explained

### avatar-engine/app/core/config.py

`Settings` — Pydantic settings class. Reads every config value from environment variables. Any field with a default will use that default if the env var isn't set. The single `settings` instance is imported everywhere in the avatar-engine.

### avatar-engine/app/core/expression_layer.py

`ExpressionLayer.load_source(image)` — Takes the uploaded photo, runs MediaPipe FaceMesh, extracts all 468 landmark (x, y) pixel coordinates. Stores them. Must be called once before `get_frame()`.

`ExpressionLayer.set_motion_state(state)` — Called by the pipeline when Redis receives an intent message from the LiveKit agent. Updates the target motion parameters. Thread-safe.

`ExpressionLayer.get_frame()` — Called every frame in the render loop. Computes the current animated parameters by blending three layers (procedural idle + FSM intent + blink), then calls `_warp_frame()`.

`ExpressionLayer._warp_frame(params)` — Applies a 2×3 affine transformation matrix to the source image based on yaw/pitch/roll values. The face centroid is used as the rotation center. Small angles (~±3°) only.

`ExpressionLayer._apply_eye_state(img, params)` — Uses MediaPipe eye lid landmark indices to scale the eye region vertically, simulating eye closure during blinks.

`BlinkController.get_eye_openness()` — Returns (left_eye, right_eye) values between 0 (closed) and 1 (open). Uses Poisson-distributed blink timing (random interval between `BLINK_INTERVAL_MIN` and `BLINK_INTERVAL_MAX` seconds). Blink takes 120ms with a sine wave opening curve.

`MotionState` (enum) — The six motion states: `NEUTRAL`, `NODDING`, `THINKING`, `ENGAGED`, `EMPATHIC`, `LISTENING`. Each maps to a dict of parameter targets in `STATE_PARAMS`.

### avatar-engine/app/core/musetalk.py (prod only)

`MuseTalkInference.load()` — Loads VAE, Whisper encoder, UNet, and face alignment model into GPU memory. Called once at startup. Takes 30–90s.

`MuseTalkInference.prepare_face(image)` — Runs face landmark detection on the source photo to find the face bounding box. Stored as `self._face_box`. Must be called once per session before `infer_frame()`.

`MuseTalkInference.infer_frame(reference_frame, audio_features)` — The core per-frame function. Crops the face, encodes it through VAE, masks the lower half, runs UNet with audio cross-attention, decodes back to pixels, pastes the new mouth region onto the full reference frame.

`AudioEncoder.encode(audio_chunk, sample_rate)` — Takes raw float32 mono PCM at 16kHz, runs Whisper feature extractor + encoder, returns (1, T, 384) numpy array of audio features.

### avatar-engine/app/core/stub_renderer.py (dev only)

`StubRenderer.load()` — No-op. Logs that it's in dev mode.

`StubRenderer.prepare_face(image)` — Uses OpenCV Haar cascade for face detection (no neural network). Falls back to center crop if no face found.

`StubRenderer.infer_frame(reference_frame, audio_features)` — Draws an animated ellipse mouth. Mouth openness = audio RMS amplitude. Adds "DEV MODE" watermark text.

`StubAudioEncoder.encode(audio_chunk)` — Returns RMS energy as a (1, 8, 384) constant array. The StubRenderer reads the mean value to drive mouth animation.

### avatar-engine/app/core/pipeline.py

`_make_renderer(config)` — Factory: returns `StubRenderer` if `DEV_MODE=true`, else `MuseTalkInference`.

`AvatarSession` — Represents one active avatar call. Holds the expression layer, renderer, audio encoder, and audio queue for one session.

`AvatarSession.initialize()` — Loads face landmarks and face bounding box. Raises `ValueError` if no face is detected.

`AvatarSession.enqueue_audio(pcm_bytes)` — Called when Redis receives an audio chunk from the LiveKit agent. Converts bytes to float32 numpy and puts it on the queue. Non-blocking — drops if queue is full (prevents audio backup during slow inference).

`AvatarSession.render_loop(redis_client)` — The main async loop that runs at `FPS_TARGET` Hz. Each iteration: get expression frame → get audio features → run inference → JPEG encode → Redis publish.

`AvatarPipeline.create_session(image)` — Creates an `AvatarSession`, initializes it, starts the Redis subscription task and render loop task. Returns the session_id.

`AvatarPipeline._subscribe_session(session_id)` — Subscribes to `avatar:audio:{id}` and `avatar:intent:{id}` Redis channels. Routes messages to the session.

### livekit-agent/app/intent_classifier.py

`classify(text)` — Takes an LLM response string, runs regex keyword matching against 4 pattern groups, returns the `MotionState` with the most keyword matches. Falls back to `NEUTRAL`. Runs synchronously in ~0.1ms (no LLM call needed).

### livekit-agent/app/main.py

`entrypoint(ctx)` — Called by LiveKit worker framework when the agent joins a room. Extracts `session_id` from the room name, sets up Redis connection, creates `VoiceAssistant` with STT+LLM+TTS plugins.

`AvatarAudioInterceptor.synthesize(text)` — Calls the TTS plugin in streaming mode, intercepts each `AudioFrame` chunk, converts to float32 PCM at 16kHz, publishes to Redis `avatar:audio:{id}` channel.

`on_llm_response(text)` — Called when the LLM commits a response. First publishes motion state to Redis (fast), then calls `audio_interceptor.synthesize()` to stream TTS audio chunks.

### webrtc-bridge/app/signaling.py

`AvatarVideoTrack` — An `aiortc` `MediaStreamTrack` subclass. Connects to the avatar-engine WebSocket, receives JPEG frames, converts to `av.VideoFrame` (yuv420p), assigns RTP timestamps, returns to aiortc for RTP packetization.

`AvatarVideoTrack.recv()` — Called by aiortc at the negotiated frame rate. Gets the next frame from the queue or repeats the last frame on timeout.

`webrtc_offer(session_id, offer)` — Receives the browser's SDP offer, creates an `RTCPeerConnection`, adds the `AvatarVideoTrack`, creates an SDP answer, returns it to the browser.

### api-gateway/app/main.py

`start_session(photo)` — Main endpoint. Forwards the photo to avatar-engine, gets `session_id`, generates a LiveKit JWT token for the browser, returns all credentials the frontend needs in one response.

`generate_livekit_token(session_id, identity)` — Uses the LiveKit Python SDK to create a signed JWT that authorizes the browser to join room `avatar-{session_id}` with publish + subscribe permissions.

### frontend/src/hooks/useWebRTC.ts

`useWebRTC.connect()` — Creates `RTCPeerConnection`, adds a recvonly video transceiver, creates an SDP offer, waits for ICE gathering, sends the offer to the webrtc-bridge, sets the returned answer. When the video track arrives, calls `onTrack(stream)`.

### frontend/src/hooks/useLiveKit.ts

`useLiveKit.connect()` — Connects to the LiveKit room, enables the microphone, sets up event listeners for speaking detection and transcript data channel messages.

### frontend/src/store/avatarStore.ts

Zustand store holding: `status`, `session` (credentials), `error`, `isMuted`, `isSpeaking`, `transcript[]`. All components read from and write to this store. No prop drilling.

---

## 8. Avatar Photo Requirements

This is the only asset you need to provide. **No videos, no expression clips, no training.**

### Required: 1 photo minimum

The avatar-engine accepts 1–5 photos. For the POC, 1 good photo is enough.

### Photo guidelines (important — affects quality significantly)

| Requirement | Why |
|---|---|
| **Front-facing** | MediaPipe needs to see both eyes and the full mouth |
| **Good lighting** | Even, diffuse light. No harsh shadows across the face |
| **Face fills 40–70% of frame** | Too small = poor landmark detection |
| **Neutral or slight smile expression** | The expression layer animates from this base |
| **Eyes open** | The blink system works from the open-eye baseline |
| **No sunglasses, hats, or face coverings** | Blocks landmark detection |
| **Resolution: at least 256×256** | 512×512 or higher is ideal |
| **Format: JPEG or PNG** | Both work |

### What happens with the photo

1. Uploaded via the browser UI
2. Resized to max 512px on longest side (preserving aspect ratio)
3. MediaPipe extracts 468 face landmarks — stored in memory
4. MuseTalk (prod) or Haar cascade (dev) finds the face bounding box
5. The photo becomes the "base frame" — every frame is derived from it
6. The expression layer warps this base frame for head motion
7. MuseTalk inpaints the lower face (mouth region) per-frame

### Photos you do NOT need

- Expression videos (nodding, smiling, etc.) — not used
- Multiple poses — not needed (the warping simulates this)
- Audio samples for voice matching — voice comes from TTS provider
- Body or clothing photos — only face/head is used in this POC

---

## 9. What You Do NOT Need

To be completely clear about what this system does NOT require:

| Thing | Needed? | Why not |
|---|---|---|
| Driving video | No | LivePortrait approach was replaced with affine warp |
| Pre-recorded expression clips | No | Motion is procedurally generated |
| Voice samples / voice cloning | No | TTS is provider-based (OpenAI/ElevenLabs) |
| Training the model on your face | No | MuseTalk is one-shot (single photo) |
| A camera on your machine | No | The avatar speaks; you use mic only |
| GPU for dev/testing | No | Dev mode runs on CPU with stub renderer |
| Model weights for dev | No | Stub renderer needs no weights |
| Deepgram account | No | Falls back to OpenAI STT |
| ElevenLabs account | No | Falls back to OpenAI TTS |

---

## 10. Troubleshooting

### "No face detected" error on photo upload

- Use a clearer front-facing photo
- Ensure the face takes up at least 40% of the image
- Try with no glasses, good even lighting
- Check logs: `make logs-avatar-engine`

### WebRTC video not appearing in browser

- Check browser console for WebRTC errors (F12)
- Ensure ports `50000-50010/UDP` are open if behind a firewall
- Try with Chrome (most compatible WebRTC implementation)
- Check `make logs-webrtc-bridge`

### LiveKit agent not responding to voice

- Check `make logs-livekit-agent` — should show "Agent joined room"
- Verify `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` are correct
- Check browser mic permissions (padlock icon in URL bar)
- Verify `OPENAI_API_KEY` is valid and has credits

### GPU OOM (out of memory) in prod

- Ensure `USE_HALF_PRECISION=true` (default)
- Try `BATCH_SIZE=2` instead of 4
- Check other processes using GPU: `nvidia-smi`
- On RTX 3080 (10GB), set `ENABLE_UPSCALER=false`

### Avatar engine takes too long to start in prod

- Normal: 60–90 seconds to load ~3GB of weights into VRAM
- Watch: `make prod-logs` — wait for "Avatar Engine ready ✓"
- If it fails after 90s: check GPU memory with `nvidia-smi`

### "DEV MODE" watermark showing in prod

- Check `DEV_MODE=false` in `.env.prod`
- Ensure you're running `make prod` not `make dev`
- Check: `make logs-avatar-engine` should say "Loading ML models..." not "DEV MODE"

### MuseTalk state_dict mismatch error

If you see a PyTorch error about unexpected/missing keys when loading weights:
```
RuntimeError: Error(s) in loading state_dict for UNet2DConditionModel
```
This means the downloaded `pytorch_model.bin` uses different layer names than the `musetalk.json` config expects. Fix:
```bash
make shell-avatar-engine
python3 -c "
import torch
state = torch.load('/app/models/musetalk/pytorch_model.bin', map_location='cpu')
print(list(state.keys())[:10])  # shows actual key names
"
```
Then compare against the config in `musetalk.json`. Update the config's layer names accordingly.

---

## 11. Dev vs Prod Differences

| Aspect | Dev | Prod |
|---|---|---|
| Docker compose file | `docker-compose.dev.yml` | `docker-compose.prod.yml` |
| Env file | `.env` | `.env.prod` |
| Make commands | `make dev` / `make dev-stop` | `make prod` / `make prod-stop` |
| Lip-sync renderer | StubRenderer (OpenCV ellipse) | MuseTalk 1.5 UNet (GPU) |
| Audio encoder | StubAudioEncoder (RMS energy) | Whisper-tiny (GPU) |
| GPU required | No | Yes |
| Model weights downloaded | No | Yes (~3.5GB) |
| Watermark on avatar | Yes ("DEV MODE") | No |
| FPS | 10 | 25 |
| Hot reload | Yes (all services) | No (built images) |
| Redis exposed | Yes (port 6379) | No |
| Avatar engine base image | python:3.10-slim | nvidia/cuda:11.8 |
| Frontend | Vite dev server (HMR) | Nginx (pre-built) |
| Startup time | ~30 seconds | ~90 seconds |
| LiveKit agent | Same | Same |
| WebRTC bridge | Same | Same |
| API gateway | Same | Same |
| Expression layer | Same (CPU always) | Same (CPU always) |
