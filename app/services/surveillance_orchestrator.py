"""
app/services/surveillance_orchestrator.py
Ties together: AI pipeline results → ROI check → face classification
→ loitering → scoring → DB persist → notifications.

One orchestrator instance per active source.
"""
import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import aiosqlite
import cv2
import numpy as np

from app.core.config import get_settings
from app.services.ai_pipeline import PipelineResult, Detection, start_detection, stop_detection
from app.services import face_engine, loitering_engine, scoring
from app.services.notification import dispatch_alert

logger = logging.getLogger(__name__)
settings = get_settings()

_loop: Optional[asyncio.AbstractEventLoop] = None
_active: Dict[int, bool] = {}

# Per-track dedup: (source_id, track_id, alert_type) -> last_alert_ts
_ALERT_DEDUP_SECONDS = 5.0
_last_alerts: Dict[tuple, float] = {}

# Per-track face classification cache: (source_id, track_id) -> (is_unknown, timestamp)
_FACE_CACHE_TTL = 5.0   # seconds to cache face classification per track
_face_cache: Dict[Tuple[int, int], Tuple[bool, float]] = {}
_MIN_FACE_CROP_PX = 40  # minimum width/height for face recognition


def set_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


# ── Helpers ───────────────────────────────────────────────────────────────

def _save_snapshot(frame: np.ndarray, source_id: int) -> Optional[str]:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = settings.snapshots_dir / f"src{source_id}_{ts}.jpg"
    ok = cv2.imwrite(str(path), frame)
    if not ok:
        logger.warning("Failed to write snapshot to %s", path)
        return None
    return str(path)


def _centroid(bbox):
    x1, y1, x2, y2 = bbox
    return (x1 + x2) // 2, (y1 + y2) // 2


# ── Per-frame callback (called from detection thread) ─────────────────────

def _make_callback(source_id: int, db_path: str):
    """Returns a callback function bound to source_id."""

    def _log_future_exc(fut: asyncio.Future) -> None:
        exc = fut.exception()
        if exc is not None:
            logger.exception("Orchestrator _process failed on source %d", source_id, exc_info=exc)

    def on_result(result: PipelineResult) -> None:
        if _loop is None or _loop.is_closed():
            return
        fut = asyncio.run_coroutine_threadsafe(_process(result, db_path), _loop)
        fut.add_done_callback(_log_future_exc)

    return on_result


async def _process(result: PipelineResult, db_path: str) -> None:
    if not result.detections:
        return

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        # Load ROI zones for this source
        async with db.execute(
            "SELECT * FROM roi_zones WHERE source_id=?", (result.source_id,)
        ) as cur:
            rois = [dict(r) for r in await cur.fetchall()]

        # Load settings
        async with db.execute("SELECT key, value FROM settings") as cur:
            cfg = {r["key"]: r["value"] for r in await cur.fetchall()}

        night_start = int(cfg.get("night_start_hour", 20))
        night_end   = int(cfg.get("night_end_hour",   6))
        score_app   = int(cfg.get("alert_score_app",   2))
        score_wa    = int(cfg.get("alert_score_whatsapp", 3))

        for det in result.detections:
            cx, cy = _centroid(det.bbox)

            # Determine ROI membership
            matched_rois = [r for r in rois if loitering_engine.point_in_roi(cx, cy, r)]
            in_danger    = any(r["zone_type"] in ("red", "critical") for r in matched_rois)

            # Loitering
            loitering = False
            for roi in matched_rois:
                if det.track_id is not None:
                    loit = loitering_engine.update(result.source_id, det.track_id, roi["id"])
                    if loit:
                        loitering = True

            # Face classification with per-track caching
            x1, y1, x2, y2 = det.bbox
            crop_w, crop_h = x2 - x1, y2 - y1
            is_unknown = True

            # Check cache first (avoid re-running face engine on same track)
            cache_key = (result.source_id, det.track_id) if det.track_id is not None else None
            now = time.time()
            if cache_key and cache_key in _face_cache:
                cached_unknown, cached_ts = _face_cache[cache_key]
                if now - cached_ts < _FACE_CACHE_TTL:
                    is_unknown = cached_unknown
                    if not is_unknown:
                        continue  # Known face — skip
                else:
                    del _face_cache[cache_key]

            # Only run face recognition if crop is large enough
            if crop_w >= _MIN_FACE_CROP_PX and crop_h >= _MIN_FACE_CROP_PX:
                face_crop = result.frame[max(0, y1):y2, max(0, x1):x2]
                if face_crop.size > 0:
                    t0 = time.perf_counter()
                    loop = asyncio.get_event_loop()
                    classifications = await loop.run_in_executor(
                        None, face_engine.classify_faces_in_frame, result.frame, [det.bbox]
                    )
                    face_ms = (time.perf_counter() - t0) * 1000
                    if classifications:
                        _, is_known = classifications[0]
                        is_unknown = not is_known

                    # Cache result for this track
                    if cache_key:
                        _face_cache[cache_key] = (is_unknown, now)

                    # Log timing periodically
                    if det.track_id and det.track_id % 5 == 0:
                        logger.info("Face engine: %.1fms, is_unknown=%s", face_ms, is_unknown)

            # Known faces have access — skip alerting entirely
            if not is_unknown:
                continue

            # Score
            score = scoring.compute_score(
                is_unknown=is_unknown,
                in_danger_zone=in_danger,
                loitering=loitering,
                night_start=night_start,
                night_end=night_end,
            )

            if score == 0:
                continue  # nothing notable

            # Dedup identical alerts for same track within a short window so
            # the alert feed stays readable during demo.
            alert_type_tmp = "loitering" if loitering else ("unknown_face" if is_unknown else "detection")
            dedup_key = (result.source_id, det.track_id, alert_type_tmp)
            now_ts = time.time()
            last_ts = _last_alerts.get(dedup_key, 0.0)
            if now_ts - last_ts < _ALERT_DEDUP_SECONDS:
                continue
            _last_alerts[dedup_key] = now_ts

            # Save snapshot
            snapshot = _save_snapshot(result.frame, result.source_id)

            # Persist alert
            meta = json.dumps({
                "track_id": det.track_id,
                "confidence": det.confidence,
                "is_unknown": is_unknown,
                "loitering": loitering,
                "in_danger_zone": in_danger,
                "matched_rois": [r["name"] for r in matched_rois],
            })
            alert_type = alert_type_tmp

            async with db.execute(
                """INSERT INTO alerts
                   (source_id, alert_type, suspicion_score, snapshot_path, meta)
                   VALUES (?,?,?,?,?)""",
                (result.source_id, alert_type, score, snapshot, meta),
            ) as cur:
                alert_id = cur.lastrowid
            await db.commit()

            # Dispatch notifications
            msg = (
                f"[Score {score}] {alert_type.upper()} on source {result.source_id}. "
                f"{'Loitering detected. ' if loitering else ''}"
                f"{'Unknown person. ' if is_unknown else ''}"
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
    start_detection(source_id, _make_callback(source_id, "surveillance.db"))
    logger.info("Orchestrator activated for source %d", source_id)


def deactivate_source(source_id: int) -> None:
    _active.pop(source_id, None)
    stop_detection(source_id)
    logger.info("Orchestrator deactivated for source %d", source_id)
