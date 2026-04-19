"""
app/api/routes/websocket_route.py
WS /ws/alerts
"""
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.security import decode_token
from app.services.websocket_manager import manager

router = APIRouter(tags=["websocket"])
logger = logging.getLogger(__name__)


@router.websocket("/ws/alerts")
async def ws_alerts(websocket: WebSocket):
    """
    Connect with optional ?token=<jwt> query param for auth.
    Broadcasts all alert payloads to every connected client.
    """
    token = websocket.query_params.get("token")
    if token:
        payload = decode_token(token)
        if not payload:
            await websocket.close(code=1008, reason="Invalid token")
            return

    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive; client can also send pings
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as exc:
        logger.warning("WS error: %s", exc)
        manager.disconnect(websocket)
