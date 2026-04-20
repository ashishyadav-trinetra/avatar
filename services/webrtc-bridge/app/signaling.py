"""
WebRTC Signaling + Avatar Video Track
──────────────────────────────────────
POST /webrtc/offer/{session_id}
  - Receives SDP offer from browser
  - Creates RTCPeerConnection with AvatarVideoTrack
  - AvatarVideoTrack pulls JPEG frames from avatar-engine WS
  - Returns SDP answer to browser

The browser then renders the peer connection video stream
which shows the live lip-synced avatar.
"""
import asyncio
import fractions
import time
from typing import Optional

import aiohttp
import numpy as np
import cv2
from av import VideoFrame
from aiortc import (
    RTCPeerConnection,
    RTCSessionDescription,
    RTCIceServer,
    RTCConfiguration,
    MediaStreamTrack,
)
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

from app.config import settings

router = APIRouter()

# Track all active peer connections for cleanup
_peer_connections: dict[str, RTCPeerConnection] = {}


# ── Pydantic models ───────────────────────────────────────────
class OfferRequest(BaseModel):
    sdp: str
    type: str


class AnswerResponse(BaseModel):
    sdp: str
    type: str


# ── Avatar Video Track ────────────────────────────────────────
class AvatarVideoTrack(MediaStreamTrack):
    """
    aiortc MediaStreamTrack that pulls JPEG frames from
    the avatar-engine WebSocket and feeds them into WebRTC.
    """
    kind = "video"

    def __init__(self, session_id: str, fps: int = 25):
        super().__init__()
        self._session_id   = session_id
        self._fps          = fps
        self._frame_time   = 1.0 / fps
        self._ws           = None
        self._ws_task: Optional[asyncio.Task] = None
        self._frame_queue: asyncio.Queue      = asyncio.Queue(maxsize=10)
        self._last_frame: Optional[np.ndarray] = None
        self._pts          = 0
        self._clock_rate   = 90000  # standard RTP video clock

    async def _connect_ws(self):
        """Connect to avatar-engine frames WebSocket."""
        url = f"{settings.AVATAR_ENGINE_URL.replace('http', 'ws')}/frames/ws/{self._session_id}"
        logger.info(f"Connecting to avatar frames WS: {url}")
        session = aiohttp.ClientSession()
        try:
            async with session.ws_connect(url) as ws:
                logger.info(f"Avatar frames WS connected for session {self._session_id}")
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.BINARY:
                        # Decode JPEG → numpy
                        nparr = np.frombuffer(msg.data, np.uint8)
                        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                        if frame is not None:
                            # Drop oldest if queue is full (don't back up)
                            if self._frame_queue.full():
                                try:
                                    self._frame_queue.get_nowait()
                                except asyncio.QueueEmpty:
                                    pass
                            await self._frame_queue.put(frame)
                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        logger.warning(f"Avatar frames WS closed/error: {msg.type}")
                        break
        except Exception as e:
            logger.error(f"Avatar frames WS error: {e}")
        finally:
            await session.close()

    def start_receiving(self):
        self._ws_task = asyncio.ensure_future(self._connect_ws())

    async def recv(self) -> VideoFrame:
        """
        Called by aiortc at the negotiated frame rate.
        Returns a VideoFrame (yuv420p) for RTP packetization.
        """
        # Ensure WS is started
        if self._ws_task is None:
            self.start_receiving()

        # Try to get a fresh frame; fall back to last known frame
        try:
            bgr = await asyncio.wait_for(
                self._frame_queue.get(),
                timeout=self._frame_time * 2,
            )
            self._last_frame = bgr
        except asyncio.TimeoutError:
            if self._last_frame is not None:
                bgr = self._last_frame
            else:
                # No frame yet — return black frame
                bgr = np.zeros((256, 256, 3), dtype=np.uint8)

        # BGR → RGB
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

        # Build av.VideoFrame
        av_frame = VideoFrame.from_ndarray(rgb, format="rgb24")
        av_frame = av_frame.reformat(format="yuv420p")

        # Assign PTS (presentation timestamp)
        av_frame.pts = self._pts
        av_frame.time_base = fractions.Fraction(1, self._clock_rate)
        self._pts += int(self._clock_rate / self._fps)

        return av_frame

    async def stop(self):
        if self._ws_task:
            self._ws_task.cancel()
        super().stop()


# ── Signaling endpoint ────────────────────────────────────────
@router.post("/offer/{session_id}", response_model=AnswerResponse)
async def webrtc_offer(session_id: str, offer: OfferRequest):
    """
    Browser sends SDP offer → we create peer connection with
    AvatarVideoTrack → return SDP answer.
    """
    # Clean up any existing PC for this session
    if session_id in _peer_connections:
        old_pc = _peer_connections.pop(session_id)
        await old_pc.close()

    # ICE configuration
    ice_servers = [RTCIceServer(urls=[settings.STUN_SERVER])]
    config = RTCConfiguration(iceServers=ice_servers)
    pc = RTCPeerConnection(configuration=config)
    _peer_connections[session_id] = pc

    # Create and add avatar video track
    video_track = AvatarVideoTrack(session_id)
    pc.addTrack(video_track)

    @pc.on("connectionstatechange")
    async def on_state_change():
        state = pc.connectionState
        logger.info(f"PC [{session_id}] state: {state}")
        if state in ("failed", "closed", "disconnected"):
            await video_track.stop()
            _peer_connections.pop(session_id, None)

    @pc.on("iceconnectionstatechange")
    async def on_ice_change():
        logger.debug(f"ICE [{session_id}]: {pc.iceConnectionState}")

    # Set remote description (browser's offer)
    await pc.setRemoteDescription(
        RTCSessionDescription(sdp=offer.sdp, type=offer.type)
    )

    # Create answer
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    logger.info(f"WebRTC session established: {session_id}")

    return AnswerResponse(
        sdp=pc.localDescription.sdp,
        type=pc.localDescription.type,
    )


@router.delete("/session/{session_id}")
async def close_session(session_id: str):
    """Close WebRTC peer connection for a session."""
    if session_id not in _peer_connections:
        raise HTTPException(404, "Session not found")
    pc = _peer_connections.pop(session_id)
    await pc.close()
    return {"status": "closed"}


@router.get("/sessions")
async def list_sessions():
    return {
        "sessions": [
            {"session_id": sid, "state": pc.connectionState}
            for sid, pc in _peer_connections.items()
        ]
    }
