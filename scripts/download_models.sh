#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  Download all required model weights for the Avatar POC
#  Run once before first docker compose up
# ─────────────────────────────────────────────────────────────
set -euo pipefail

MODELS_DIR="$(cd "$(dirname "$0")/.." && pwd)/models"
mkdir -p "$MODELS_DIR"/{musetalk,gfpgan,dwpose}

echo ""
echo "═══════════════════════════════════════════"
echo "  Downloading Avatar POC Model Weights"
echo "  Target: $MODELS_DIR"
echo "═══════════════════════════════════════════"
echo ""

# ── Helper ───────────────────────────────────────────────────
download_file() {
  local url="$1"
  local dest="$2"
  local name="$3"
  if [ -f "$dest" ]; then
    echo "  ✓ $name already exists, skipping"
    return
  fi
  echo "  ↓ Downloading $name..."
  mkdir -p "$(dirname "$dest")"
  if command -v wget &>/dev/null; then
    wget -q --show-progress -O "$dest" "$url"
  else
    curl -L --progress-bar -o "$dest" "$url"
  fi
  echo "  ✓ $name downloaded"
}

download_hf() {
  local repo="$1"
  local filename="$2"
  local dest="$3"
  local name="$4"
  local url="https://huggingface.co/${repo}/resolve/main/${filename}"
  download_file "$url" "$dest" "$name"
}

# ── MuseTalk 1.5 weights ─────────────────────────────────────
echo "── MuseTalk 1.5 ──"

download_hf \
  "TMElyralab/MuseTalk" \
  "models/musetalk/musetalk.json" \
  "$MODELS_DIR/musetalk/musetalk.json" \
  "MuseTalk config"

download_hf \
  "TMElyralab/MuseTalk" \
  "models/musetalk/pytorch_model.bin" \
  "$MODELS_DIR/musetalk/pytorch_model.bin" \
  "MuseTalk UNet weights (~1.4GB)"

# ── VAE (ft-mse) ─────────────────────────────────────────────
echo ""
echo "── Stable Diffusion VAE (ft-mse) ──"
download_hf \
  "stabilityai/sd-vae-ft-mse" \
  "diffusion_pytorch_model.bin" \
  "$MODELS_DIR/musetalk/sd-vae-ft-mse/diffusion_pytorch_model.bin" \
  "VAE weights (~850MB)"

download_hf \
  "stabilityai/sd-vae-ft-mse" \
  "config.json" \
  "$MODELS_DIR/musetalk/sd-vae-ft-mse/config.json" \
  "VAE config"

# ── Whisper tiny (audio encoder inside MuseTalk) ─────────────
echo ""
echo "── Whisper Tiny ──"
download_hf \
  "openai/whisper-tiny" \
  "pytorch_model.bin" \
  "$MODELS_DIR/musetalk/whisper/pytorch_model.bin" \
  "Whisper tiny weights (~150MB)"

download_hf \
  "openai/whisper-tiny" \
  "config.json" \
  "$MODELS_DIR/musetalk/whisper/config.json" \
  "Whisper config"

# ── DWPose / face detection (S3FD) ───────────────────────────
echo ""
echo "── DWPose / S3FD face detection ──"
download_hf \
  "TMElyralab/MuseTalk" \
  "models/dwpose/dw-ll_ucoco_384.pth" \
  "$MODELS_DIR/dwpose/dw-ll_ucoco_384.pth" \
  "DWPose body pose (~280MB)"

download_hf \
  "TMElyralab/MuseTalk" \
  "models/face-parse-bisent/79999_iter.pth" \
  "$MODELS_DIR/musetalk/face-parse-bisent/79999_iter.pth" \
  "Face parsing model (~50MB)"

# ── GFPGAN v1.4 (optional HD upscaler) ───────────────────────
echo ""
echo "── GFPGAN v1.4 (face upscaler, optional) ──"
download_file \
  "https://github.com/TencentARC/GFPGAN/releases/download/v1.3.4/GFPGANv1.4.pth" \
  "$MODELS_DIR/gfpgan/GFPGANv1.4.pth" \
  "GFPGAN v1.4 (~350MB)"

# ── Summary ──────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════"
echo "  Download complete!"
echo ""
echo "  Total model storage:"
du -sh "$MODELS_DIR" 2>/dev/null || true
echo ""
echo "  Next: fill in .env credentials → make run"
echo "═══════════════════════════════════════════"
echo ""
