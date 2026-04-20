"""
Frames WebSocket endpoint.
WebRTC bridge connects here to receive JPEG frame bytes
for a given session in real-time.
"""
import asyncio
import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

router = APIRouter()

REDIS_CHANNEL_FRAMES = "avatar:frames:{session_id}"


@router.websocket("/ws/{session_id}")
async def frames_ws(websocket: WebSocket, session_id: str):
    """
    WebRTC bridge subscribes here.
    Each message is a JPEG-encoded frame (bytes).
    """
    await websocket.accept()
    logger.info(f"WebRTC bridge connected for session {session_id}")

    # Get Redis URL from app config
    redis_url = websocket.app.state.pipeline._config.REDIS_URL
    redis = await aioredis.from_url(redis_url, decode_responses=False)
    pubsub = redis.pubsub()
    channel = REDIS_CHANNEL_FRAMES.format(session_id=session_id)
    await pubsub.subscribe(channel)

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            frame_bytes = message["data"]
            await websocket.send_bytes(frame_bytes)
    except (WebSocketDisconnect, asyncio.CancelledError):
        logger.info(f"WebRTC bridge disconnected for session {session_id}")
    finally:
        await pubsub.unsubscribe(channel)
        await redis.close()
