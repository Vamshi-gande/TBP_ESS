"""
app/services/loitering_engine.py
Tracks how long a person (identified by track_id) stays inside any ROI.
If the dwell time exceeds the configured threshold, loitering is flagged.

Includes a periodic cleanup timer that removes stale entries automatically.
"""
import time
import threading
import logging
from typing import Dict, Tuple, Optional

logger = logging.getLogger(__name__)

_CLEANUP_INTERVAL = 60  # seconds between stale-entry cleanup
_STALE_AGE = 300.0      # entries older than this are cleaned up

# key: (source_id, track_id, roi_id) → first_seen_timestamp
_dwell: Dict[Tuple[int, int, int], float] = {}
_lock = threading.Lock()
_threshold: int = 30   # default; updated from settings

# Cleanup timer
_cleanup_timer: Optional[threading.Timer] = None
_timer_running = False


def update_threshold(seconds: int) -> None:
    global _threshold
    _threshold = seconds
    logger.info("Loitering threshold updated to %ds", seconds)


def point_in_roi(cx: int, cy: int, roi: dict) -> bool:
    """Check if centroid (cx, cy) is inside an ROI dict."""
    return (
        roi["x"] <= cx <= roi["x"] + roi["width"]
        and roi["y"] <= cy <= roi["y"] + roi["height"]
    )


def update(source_id: int, track_id: int, roi_id: int) -> bool:
    """
    Call every frame for each (track, roi) pair that overlaps.
    Returns True if this track has been loitering (dwell >= threshold).
    """
    key = (source_id, track_id, roi_id)
    now = time.time()
    with _lock:
        if key not in _dwell:
            _dwell[key] = now
        return (now - _dwell[key]) >= _threshold


def clear_track(source_id: int, track_id: int) -> None:
    """Remove all dwell entries for a track that left all ROIs."""
    prefix = (source_id, track_id)
    with _lock:
        stale = [k for k in _dwell if k[:2] == prefix]
        for k in stale:
            del _dwell[k]


def cleanup_stale(max_age: Optional[float] = None) -> None:
    """Remove entries not updated for max_age seconds."""
    age = max_age if max_age is not None else _STALE_AGE
    now = time.time()
    with _lock:
        stale = [k for k, t in _dwell.items() if now - t > age]
        for k in stale:
            del _dwell[k]
    if stale:
        logger.debug("Cleaned up %d stale loitering entries", len(stale))


def get_dwell_seconds(source_id: int, track_id: int, roi_id: int) -> Optional[float]:
    key = (source_id, track_id, roi_id)
    with _lock:
        t = _dwell.get(key)
    if t is None:
        return None
    return time.time() - t


# ── Periodic cleanup timer ─────────────────────────────────────────────

def _cleanup_loop() -> None:
    """Runs cleanup_stale periodically in a background thread."""
    global _cleanup_timer
    if not _timer_running:
        return
    cleanup_stale()
    _cleanup_timer = threading.Timer(_CLEANUP_INTERVAL, _cleanup_loop)
    _cleanup_timer.daemon = True
    _cleanup_timer.start()


def start_cleanup_timer() -> None:
    """Start the periodic cleanup timer."""
    global _timer_running, _cleanup_timer
    _timer_running = True
    _cleanup_timer = threading.Timer(_CLEANUP_INTERVAL, _cleanup_loop)
    _cleanup_timer.daemon = True
    _cleanup_timer.start()
    logger.info("Loitering cleanup timer started (interval=%ds)", _CLEANUP_INTERVAL)


def stop_cleanup_timer() -> None:
    """Stop the periodic cleanup timer."""
    global _timer_running, _cleanup_timer
    _timer_running = False
    if _cleanup_timer:
        _cleanup_timer.cancel()
        _cleanup_timer = None
    logger.info("Loitering cleanup timer stopped")
