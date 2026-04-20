"""
MuseTalk Inference Wrapper
──────────────────────────
Wraps MuseTalk 1.5's UNet + VAE pipeline for per-frame lip sync.
Input:  reference frame (BGR) + audio features (mel spectrogram)
Output: lip-synced frame (BGR)
"""
import os
import json
from pathlib import Path
from typing import Optional

import torch
import numpy as np
import cv2
from loguru import logger


class MuseTalkInference:
    """
    Thin wrapper around MuseTalk's latent-space inpainting pipeline.
    Loads weights once, runs inference per frame.
    """

    def __init__(self, config):
        self._config = config
        self._device = torch.device(config.DEVICE)
        self._dtype  = torch.float16 if config.USE_HALF_PRECISION and config.DEVICE == "cuda" else torch.float32

        self._unet    = None
        self._vae     = None
        self._whisper = None
        self._loaded  = False

        # Face crop state (set per avatar session)
        self._face_box: Optional[tuple] = None     # (x1,y1,x2,y2)
        self._face_size = config.FACE_SIZE

    def load(self):
        """Load all model weights. Called once at startup."""
        model_dir = Path(self._config.MODEL_DIR)
        logger.info("Loading MuseTalk weights...")

        # ── VAE ──────────────────────────────────────────────
        from diffusers import AutoencoderKL
        vae_path = model_dir / self._config.VAE_DIR
        self._vae = AutoencoderKL.from_pretrained(
            str(vae_path), torch_dtype=self._dtype
        ).to(self._device)
        self._vae.eval()
        logger.info("✓ VAE loaded")

        # ── Whisper audio encoder ─────────────────────────────
        from transformers import WhisperModel, WhisperFeatureExtractor
        whisper_path = model_dir / self._config.WHISPER_DIR
        self._whisper_extractor = WhisperFeatureExtractor.from_pretrained(str(whisper_path))
        self._whisper_encoder = WhisperModel.from_pretrained(
            str(whisper_path), torch_dtype=self._dtype
        ).encoder.to(self._device)
        self._whisper_encoder.eval()
        logger.info("✓ Whisper encoder loaded")

        # ── MuseTalk UNet ─────────────────────────────────────
        from diffusers import UNet2DConditionModel
        musetalk_config = model_dir / self._config.MUSETALK_CONFIG
        musetalk_weights = model_dir / self._config.MUSETALK_WEIGHTS

        with open(musetalk_config) as f:
            unet_config = json.load(f)

        self._unet = UNet2DConditionModel(**unet_config).to(self._device)
        state_dict = torch.load(str(musetalk_weights), map_location=self._device)
        self._unet.load_state_dict(state_dict)
        self._unet.eval()
        if self._dtype == torch.float16:
            self._unet = self._unet.half()
        logger.info("✓ MuseTalk UNet loaded")

        # ── Face detector ─────────────────────────────────────
        import face_alignment
        self._fa = face_alignment.FaceAlignment(
            face_alignment.LandmarksType.TWO_D,
            device=str(self._device),
            flip_input=False,
        )
        logger.info("✓ Face alignment loaded")

        self._loaded = True
        logger.info(f"MuseTalk ready on {self._device} ({self._dtype})")

    def prepare_face(self, image: np.ndarray) -> Optional[tuple]:
        """
        Detect face, compute crop box, precompute reference latent.
        Returns (crop_box, reference_latent) or None if no face found.
        Call once per avatar session.
        """
        assert self._loaded, "Call load() first"
        preds = self._fa.get_landmarks(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        if preds is None or len(preds) == 0:
            return None

        lm = preds[0]  # (68, 2)
        x1 = int(lm[:, 0].min()) - 20
        y1 = int(lm[:, 1].min()) - 30
        x2 = int(lm[:, 0].max()) + 20
        y2 = int(lm[:, 1].max()) + 20
        h, w = image.shape[:2]
        self._face_box = (
            max(0, x1), max(0, y1),
            min(w, x2), min(h, y2)
        )
        logger.info(f"Face crop box: {self._face_box}")
        return self._face_box

    @torch.inference_mode()
    def infer_frame(
        self,
        reference_frame: np.ndarray,
        audio_features: np.ndarray,
    ) -> np.ndarray:
        """
        Core per-frame inference.
        reference_frame: BGR (H, W, 3)  — from expression layer
        audio_features:  (1, T, D)       — from audio_encoder
        Returns: BGR (H, W, 3)
        """
        assert self._loaded
        assert self._face_box is not None, "Call prepare_face() first"

        x1, y1, x2, y2 = self._face_box
        face_crop = reference_frame[y1:y2, x1:x2]
        face_resized = cv2.resize(face_crop, (self._face_size, self._face_size))

        # BGR → RGB → tensor → [-1, 1]
        face_rgb = cv2.cvtColor(face_resized, cv2.COLOR_BGR2RGB)
        face_t = torch.from_numpy(face_rgb).float().permute(2, 0, 1) / 127.5 - 1.0
        face_t = face_t.unsqueeze(0).to(self._device).to(self._dtype)

        # ── VAE encode ────────────────────────────────────────
        latent = self._vae.encode(face_t).latent_dist.sample() * 0.18215

        # ── Mask lower half (mouth region) ───────────────────
        mask = torch.ones_like(latent)
        mask[:, :, latent.shape[2] // 2 :, :] = 0  # zero lower face latents
        latent_masked = latent * mask

        # ── Audio features → cross-attention context ──────────
        audio_t = torch.from_numpy(audio_features).to(self._device).to(self._dtype)
        if audio_t.dim() == 2:
            audio_t = audio_t.unsqueeze(0)

        # ── UNet inpainting ───────────────────────────────────
        # Concatenate original + masked along channel dim (MuseTalk convention)
        unet_input = torch.cat([latent_masked, mask], dim=1)

        # Timestep = 0 (inference, no diffusion noise)
        t = torch.zeros(1, dtype=torch.long, device=self._device)

        with torch.autocast(device_type="cuda", dtype=self._dtype, enabled=(self._dtype == torch.float16)):
            noise_pred = self._unet(
                unet_input,
                t,
                encoder_hidden_states=audio_t,
            ).sample

        # Reconstruct: replace lower face latent with predicted
        latent_out = latent * mask + noise_pred * (1 - mask)

        # ── VAE decode ────────────────────────────────────────
        decoded = self._vae.decode(latent_out / 0.18215).sample
        decoded = (decoded.clamp(-1, 1) + 1) / 2  # [0, 1]
        decoded_np = (decoded[0].permute(1, 2, 0).cpu().float().numpy() * 255).astype(np.uint8)
        decoded_bgr = cv2.cvtColor(decoded_np, cv2.COLOR_RGB2BGR)

        # ── Paste back onto full reference frame ─────────────
        result = reference_frame.copy()
        face_h, face_w = y2 - y1, x2 - x1
        mouth_patch = cv2.resize(decoded_bgr, (face_w, face_h))
        result[y1:y2, x1:x2] = mouth_patch

        return result


class AudioEncoder:
    """
    Encodes raw audio chunks → mel features for MuseTalk.
    Uses Whisper-tiny encoder (same weights as MuseTalk uses internally).
    """

    def __init__(self, config):
        self._config = config
        self._device = torch.device(config.DEVICE)
        self._dtype  = torch.float16 if config.USE_HALF_PRECISION and config.DEVICE == "cuda" else torch.float32
        self._extractor = None
        self._encoder   = None

    def load(self, whisper_path: str):
        from transformers import WhisperModel, WhisperFeatureExtractor
        self._extractor = WhisperFeatureExtractor.from_pretrained(whisper_path)
        self._encoder = WhisperModel.from_pretrained(
            whisper_path, torch_dtype=self._dtype
        ).encoder.to(self._device)
        self._encoder.eval()

    @torch.inference_mode()
    def encode(self, audio_chunk: np.ndarray, sample_rate: int = 16000) -> np.ndarray:
        """
        audio_chunk: float32 mono PCM at 16kHz
        Returns:     numpy (1, T, 384) — cross-attention features
        """
        inputs = self._extractor(
            audio_chunk,
            sampling_rate=sample_rate,
            return_tensors="pt",
        )
        input_features = inputs.input_features.to(self._device).to(self._dtype)
        with torch.autocast(device_type="cuda", dtype=self._dtype, enabled=(self._dtype == torch.float16)):
            out = self._encoder(input_features)
        return out.last_hidden_state.cpu().float().numpy()
