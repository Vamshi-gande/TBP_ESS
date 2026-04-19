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
from typing import Dict, List, Optional

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


# ── Per-frame callback (called from detection thread) ─────────────────────

def _make_callback(source_id: int, db_path: str):
    """Returns a callback function bound to source_id."""

    def on_result(result: PipelineResult) -> None:
        if _loop is None or _loop.is_closed():
            return
        asyncio.run_coroutine_threadsafe(
            _process(result, db_path), _loop
        )

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

            # Face classification (lightweight crop)
            x1, y1, x2, y2 = det.bbox
            face_crop = result.frame[max(0, y1):y2, max(0, x1):x2]
            is_unknown = True
            if face_crop.size > 0:
                classifications = face_engine.classify_faces_in_frame(
                    result.frame, [det.bbox]
                )
                if classifications:
                    _, is_known = classifications[0]
                    is_unknown = not is_known

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
            alert_type = "loitering" if loitering else ("unknown_face" if is_unknown else "detection")

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
