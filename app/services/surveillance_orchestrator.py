"""
app/services/surveillance_orchestrator.py
Ties together: MOG2 motion detection → AI pipeline results → ROI check
→ face classification → loitering → scoring → DB persist → notifications.

Features:
  - Per-source ROI/settings cache (refreshed every 30s)
  - Per-track alert cooldown (60s) to prevent flooding
  - MOG2 pre-filtering before YOLO
  - History logging for all detection events
"""
import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import asyncpg
import cv2
import numpy as np

from app.core.config import get_settings
from app.services.ai_pipeline import PipelineResult, Detection, start_detection, stop_detection
from app.services import face_engine, loitering_engine, scoring, motion_detector
from app.services.notification import dispatch_alert

logger = logging.getLogger(__name__)
settings = get_settings()

_loop: Optional[asyncio.AbstractEventLoop] = None
_active: Dict[int, bool] = {}

# ── Cache ─────────────────────────────────────────────────────────────────
_CACHE_TTL = 30.0  # seconds

_roi_cache: Dict[int, Tuple[float, List[dict]]] = {}   # source_id → (timestamp, rois)
_settings_cache: Tuple[float, dict] = (0.0, {})        # (timestamp, settings_dict)

# ── Alert cooldown ────────────────────────────────────────────────────────
_ALERT_COOLDOWN = 60.0  # seconds between alerts for the same track_id
_last_alert: Dict[Tuple[int, int], float] = {}  # (source_id, track_id) → timestamp


def set_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


# ── Helpers ───────────────────────────────────────────────────────────────

def _save_snapshot(frame: np.ndarray, source_id: int) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = settings.snapshots_dir / f"src{source_id}_{ts}.jpg"
    cv2.imwrite(str(path), frame)
    return str(path)


def _centroid(bbox):
    x1, y1, x2, y2 = bbox
    return (x1 + x2) // 2, (y1 + y2) // 2


def _is_cooled_down(source_id: int, track_id: Optional[int]) -> bool:
    """Returns True if enough time has passed since last alert for this track."""
    if track_id is None:
        return True
    key = (source_id, track_id)
    now = time.time()
    last = _last_alert.get(key, 0.0)
    if now - last < _ALERT_COOLDOWN:
        return False
    _last_alert[key] = now
    return True


# ── Cache helpers ─────────────────────────────────────────────────────────

async def _get_rois(conn: asyncpg.Connection, source_id: int) -> List[dict]:
    """Get ROI zones with caching."""
    now = time.time()
    cached = _roi_cache.get(source_id)
    if cached and now - cached[0] < _CACHE_TTL:
        return cached[1]

    rows = await conn.fetch(
        "SELECT * FROM roi_zones WHERE source_id=$1", source_id
    )
    rois = [dict(r) for r in rows]

    _roi_cache[source_id] = (now, rois)
    return rois


async def _get_settings(conn: asyncpg.Connection) -> dict:
    """Get settings with caching."""
    global _settings_cache
    now = time.time()
    if now - _settings_cache[0] < _CACHE_TTL:
        return _settings_cache[1]

    rows = await conn.fetch("SELECT key, value FROM settings")
    cfg = {r["key"]: r["value"] for r in rows}

    _settings_cache = (now, cfg)
    return cfg


# ── Per-frame callback (called from detection thread) ─────────────────────

def _make_callback(source_id: int):
    """Returns a callback function bound to source_id."""

    def on_result(result: PipelineResult) -> None:
        if _loop is None or _loop.is_closed():
            return
        asyncio.run_coroutine_threadsafe(
            _process(result), _loop
        )

    return on_result


async def _process(result: PipelineResult) -> None:
    if not result.detections:
        return

    pool = None
    try:
        from app.db.database import get_pool
        pool = get_pool()
    except RuntimeError:
        logger.warning("DB pool not available, skipping detection processing")
        return

    async with pool.acquire() as conn:
        # Load ROI zones (cached)
        rois = await _get_rois(conn, result.source_id)

        # Load settings (cached)
        cfg = await _get_settings(conn)

        night_start = int(cfg.get("night_start_hour", 20))
        night_end   = int(cfg.get("night_end_hour",   6))
        score_app   = int(cfg.get("alert_score_app",   2))
        score_wa    = int(cfg.get("alert_score_whatsapp", 3))

        # Compute night time once for all detections in this frame
        is_night = scoring.is_night_time(night_start, night_end)

        for det in result.detections:
            # Check cooldown
            if not _is_cooled_down(result.source_id, det.track_id):
                continue

            cx, cy = _centroid(det.bbox)

            # Determine ROI membership
            matched_rois = [r for r in rois if loitering_engine.point_in_roi(cx, cy, r)]
            in_danger    = any(r["zone_type"] in ("red", "critical") for r in matched_rois)

            # Loitering check (Signal 2: BEHAVIOR)
            loitering = False
            for roi in matched_rois:
                if det.track_id is not None:
                    loit = loitering_engine.update(result.source_id, det.track_id, roi["id"])
                    if loit:
                        loitering = True

            # Face classification (Signal 3: FREQUENCY)
            x1, y1, x2, y2 = det.bbox
            is_unknown = True
            face_crop = result.frame[max(0, y1):y2, max(0, x1):x2]
            if face_crop.size > 0:
                classifications = face_engine.classify_faces_in_frame(
                    result.frame, [det.bbox]
                )
                if classifications:
                    _, is_known = classifications[0]
                    is_unknown = not is_known

            # Three-Signal Score
            score = scoring.compute_score(
                is_unknown=is_unknown,
                is_night=is_night,
                loitering=loitering,
            )

            if score == 0:
                continue  # nothing notable

            # Save snapshot
            snapshot = _save_snapshot(result.frame, result.source_id)

            # Persist alert
            meta = json.dumps({
                "track_id": det.track_id,
                "confidence": det.confidence,
                "is_unknown": is_unknown,
                "loitering": loitering,
                "in_danger_zone": in_danger,
                "is_night": is_night,
                "matched_rois": [r["name"] for r in matched_rois],
            })
            alert_type = "loitering" if loitering else ("unknown_face" if is_unknown else "detection")

            alert_id = await conn.fetchval(
                """INSERT INTO alerts
                   (source_id, alert_type, suspicion_score, snapshot_path, meta)
                   VALUES ($1,$2,$3,$4,$5) RETURNING id""",
                result.source_id, alert_type, score, snapshot, meta,
            )

            # Log to history
            await conn.execute(
                "INSERT INTO history (source_id, event_type, detail) VALUES ($1,$2,$3)",
                result.source_id, alert_type,
                f"Score {score}: {'night ' if is_night else ''}{'loitering ' if loitering else ''}{'unknown' if is_unknown else 'known'}",
            )

            # Dispatch notifications
            msg = (
                f"[Score {score}] {alert_type.upper()} on source {result.source_id}. "
                f"{'Loitering detected. ' if loitering else ''}"
                f"{'Unknown person. ' if is_unknown else ''}"
                f"{'Night time. ' if is_night else ''}"
            )
            await dispatch_alert(
                alert_id=alert_id,
                source_id=result.source_id,
                alert_type=alert_type,
                suspicion_score=score,
                snapshot_path=snapshot,
                message=msg,
                alert_score_app=score_app,
                alert_score_whatsapp=score_wa,
            )


# ── Public API ────────────────────────────────────────────────────────────

def activate_source(source_id: int) -> None:
    _active[source_id] = True
    start_detection(source_id, _make_callback(source_id))
    logger.info("Orchestrator activated for source %d", source_id)


def deactivate_source(source_id: int) -> None:
    _active.pop(source_id, None)
    stop_detection(source_id)
    motion_detector.reset_source(source_id)
    _roi_cache.pop(source_id, None)
    # Clean up cooldown entries for this source
    stale = [k for k in _last_alert if k[0] == source_id]
    for k in stale:
        del _last_alert[k]
    logger.info("Orchestrator deactivated for source %d", source_id)


def shutdown_all() -> None:
    """Deactivate all sources — called on app shutdown."""
    for sid in list(_active.keys()):
        deactivate_source(sid)
    logger.info("All orchestrator sources shut down")
