"""
WebSocket endpoint for coefficient streaming.
Clients connect here to receive 258-byte binary frames at 30 FPS.
"""

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter()

# Session registry — set by main app
_sessions = {}


def set_sessions(s):
    global _sessions
    _sessions = s


@router.websocket("/coefficients/ws/{session_id}")
async def coefficient_stream(ws: WebSocket, session_id: str):
    """
    Stream coefficient frames for a session.

    Protocol:
    - Server sends binary frames (258 bytes each)
    - Frame format: 6-byte header + 252-byte payload (see avatar_spec)
    - Client can send text "ping" to keep alive
    - Client can send text "set_state:{state}" to change behavior state
    """
    await ws.accept()
    logger.info(f"[{session_id}] WebSocket client connected for coefficient stream")

    session = _sessions.get(session_id)
    if not session:
        await ws.send_json({"error": "Session not found", "session_id": session_id})
        await ws.close(1008)
        return

    try:
        # Start two concurrent tasks: sending frames and receiving commands
        send_task = asyncio.create_task(_send_frames(ws, session))
        recv_task = asyncio.create_task(_recv_commands(ws, session))

        # Wait for either to finish (disconnect)
        done, pending = await asyncio.wait(
            [send_task, recv_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()

    except WebSocketDisconnect:
        logger.info(f"[{session_id}] WebSocket client disconnected")
    except Exception as e:
        logger.error(f"[{session_id}] WebSocket error: {e}")
    finally:
        logger.info(f"[{session_id}] Coefficient stream ended")


async def _send_frames(ws: WebSocket, session):
    """Send coefficient frames as binary WebSocket messages."""
    try:
        while True:
            frame_data = await session.get_frame()
            if frame_data:
                await ws.send_bytes(frame_data)
    except Exception:
        pass


async def _recv_commands(ws: WebSocket, session):
    """Receive control commands from the client."""
    from ..core.behavior_layer import MotionState

    try:
        while True:
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text("pong")
            elif data.startswith("set_state:"):
                state_name = data.split(":", 1)[1].strip().upper()
                try:
                    state = MotionState(state_name.lower())
                    session._behavior.set_motion_state(state)
                    logger.debug(f"[{session.session_id}] Motion state → {state}")
                except ValueError:
                    pass
    except Exception:
        pass
