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
from app.services.ai_pipeline import (
    PipelineResult, Detection, draw_detections, start_detection, stop_detection,
)
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


def set_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


# ── Helpers ───────────────────────────────────────────────────────────────

def _save_snapshot(
    frame: np.ndarray,
    source_id: int,
    detections: Optional[List[Detection]] = None,
) -> Optional[str]:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = settings.snapshots_dir / f"src{source_id}_{ts}.jpg"
    annotated = draw_detections(frame, detections) if detections else frame
    ok = cv2.imwrite(str(path), annotated)
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

        async with db.execute(
            "SELECT * FROM roi_zones WHERE source_id=?", (result.source_id,)
        ) as cur:
            rois = [dict(r) for r in await cur.fetchall()]

        async with db.execute("SELECT key, value FROM settings") as cur:
            cfg = {r["key"]: r["value"] for r in await cur.fetchall()}

        night_start = int(cfg.get("night_start_hour", 20))
        night_end   = int(cfg.get("night_end_hour",   6))
        score_app   = int(cfg.get("alert_score_app",   2))
        score_wa    = int(cfg.get("alert_score_whatsapp", 3))

        # ── Face classification: one batched call per frame ──────────────
        # We resolve which detections are missing a fresh cache hit and
        # classify all of those bboxes together. Big win for multi-person.
        now = time.time()
        to_classify_idx: List[int] = []
        to_classify_bboxes: List[Tuple[int, int, int, int]] = []
        is_unknown_per_det: List[bool] = [True] * len(result.detections)

        for i, det in enumerate(result.detections):
            cache_key = (result.source_id, det.track_id) if det.track_id is not None else None
            if cache_key and cache_key in _face_cache:
                cached_unknown, cached_ts = _face_cache[cache_key]
                if now - cached_ts < _FACE_CACHE_TTL:
                    is_unknown_per_det[i] = cached_unknown
                    continue
                del _face_cache[cache_key]
            to_classify_idx.append(i)
            to_classify_bboxes.append(det.bbox)

        if to_classify_bboxes:
            t0 = time.perf_counter()
            loop = asyncio.get_running_loop()
            classifications = await loop.run_in_executor(
                None, face_engine.classify_faces_in_frame,
                result.frame, to_classify_bboxes,
            )
            face_ms = (time.perf_counter() - t0) * 1000
            for slot, (_, is_known) in zip(to_classify_idx, classifications):
                is_unknown_per_det[slot] = not is_known
                det = result.detections[slot]
                cache_key = (result.source_id, det.track_id) if det.track_id is not None else None
                if cache_key:
                    _face_cache[cache_key] = (is_unknown_per_det[slot], now)
            logger.debug(
                "Face engine: %d bboxes in %.1fms (%.1fms each)",
                len(to_classify_bboxes), face_ms,
                face_ms / max(1, len(to_classify_bboxes)),
            )

        # ── Per-detection scoring + alerting ─────────────────────────────
        for i, det in enumerate(result.detections):
            is_unknown = is_unknown_per_det[i]
            cx, cy = _centroid(det.bbox)

            matched_rois = [r for r in rois if loitering_engine.point_in_roi(cx, cy, r)]
            in_danger    = any(r["zone_type"] in ("red", "critical") for r in matched_rois)

            loitering = False
            for roi in matched_rois:
                if det.track_id is not None:
                    if loitering_engine.update(result.source_id, det.track_id, roi["id"]):
                        loitering = True

            if not is_unknown:
                # Known face — let them through, nothing to alert on.
                continue

            score = scoring.compute_score(
                is_unknown=is_unknown,
                in_danger_zone=in_danger,
                loitering=loitering,
                night_start=night_start,
                night_end=night_end,
            )
            if score == 0:
                continue

            alert_type = "loitering" if loitering else "unknown_face"
            dedup_key = (result.source_id, det.track_id, alert_type)
            now_ts = time.time()
            if now_ts - _last_alerts.get(dedup_key, 0.0) < _ALERT_DEDUP_SECONDS:
                continue
            _last_alerts[dedup_key] = now_ts

            snapshot = _save_snapshot(result.frame, result.source_id, result.detections)

            meta = json.dumps({
                "track_id": det.track_id,
                "confidence": det.confidence,
                "is_unknown": is_unknown,
                "loitering": loitering,
                "in_danger_zone": in_danger,
                "matched_rois": [r["name"] for r in matched_rois],
            })

            async with db.execute(
                """INSERT INTO alerts
                   (source_id, alert_type, suspicion_score, snapshot_path, meta)
                   VALUES (?,?,?,?,?)""",
                (result.source_id, alert_type, score, snapshot, meta),
            ) as cur:
                alert_id = cur.lastrowid
            await db.commit()

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
