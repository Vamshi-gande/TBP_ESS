"""
app/services/notification.py
Sends alerts via WebSocket broadcast and Twilio (WhatsApp / SMS fallback).
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from app.core.config import get_settings
from app.services.websocket_manager import manager

logger = logging.getLogger(__name__)
settings = get_settings()


async def dispatch_alert(
    alert_id: int,
    source_id: Optional[int],
    alert_type: str,
    suspicion_score: int,
    snapshot_path: Optional[str],
    message: str,
    alert_score_app: int = 2,
    alert_score_whatsapp: int = 3,
) -> None:
    """
    Central dispatch:
      score >= alert_score_app      → WebSocket broadcast
      score >= alert_score_whatsapp → WhatsApp (+ SMS fallback)
    """
    payload = {
        "event": "alert",
        "alert_id": alert_id,
        "source_id": source_id,
        "alert_type": alert_type,
        "suspicion_score": suspicion_score,
        "snapshot_path": snapshot_path,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if suspicion_score >= alert_score_app:
        await manager.broadcast(payload)
        logger.info("WS alert broadcast: score=%d type=%s", suspicion_score, alert_type)

    if suspicion_score >= alert_score_whatsapp:
        await _send_twilio(message, snapshot_path)


async def _send_twilio(message: str, media_url: Optional[str] = None) -> None:
    """Non-blocking Twilio send executed in thread pool."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _send_twilio_sync, message, media_url)


def _send_twilio_sync(message: str, media_url: Optional[str] = None) -> None:
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        logger.warning("Twilio not configured; skipping notification")
        return

    from twilio.rest import Client
    from twilio.base.exceptions import TwilioRestException

    client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

    # Try WhatsApp first
    try:
        kwargs = {
            "body": message,
            "from_": settings.TWILIO_FROM_WHATSAPP,
            "to": settings.ALERT_PHONE_WHATSAPP,
        }
        if media_url:
            kwargs["media_url"] = [media_url]
        client.messages.create(**kwargs)
        logger.info("WhatsApp alert sent")
        return
    except TwilioRestException as exc:
        logger.warning("WhatsApp failed (%s); falling back to SMS", exc)

    # SMS fallback
    try:
        client.messages.create(
            body=message,
            from_=settings.TWILIO_FROM_SMS,
            to=settings.ALERT_PHONE_SMS,
        )
        logger.info("SMS fallback sent")
    except TwilioRestException as exc:
        logger.error("SMS fallback also failed: %s", exc)
