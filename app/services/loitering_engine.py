"""
app/services/loitering_engine.py
Tracks how long a person (identified by track_id) stays inside any ROI.
If the dwell time exceeds the configured threshold, loitering is flagged.
"""
import time
import threading
from typing import Dict, Tuple, Optional

_CLEANUP_INTERVAL = 60  # seconds between stale-entry cleanup

# key: (source_id, track_id, roi_id) → first_seen_timestamp
_dwell: Dict[Tuple[int, int, int], float] = {}
_lock = threading.Lock()
_threshold: int = 30   # default; updated from settings


def update_threshold(seconds: int) -> None:
    global _threshold
    _threshold = seconds


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


def cleanup_stale(max_age: float = 300.0) -> None:
    """Remove entries not updated for max_age seconds."""
    now = time.time()
    with _lock:
        stale = [k for k, t in _dwell.items() if now - t > max_age]
        for k in stale:
            del _dwell[k]


def get_dwell_seconds(source_id: int, track_id: int, roi_id: int) -> Optional[float]:
    key = (source_id, track_id, roi_id)
    with _lock:
        t = _dwell.get(key)
    if t is None:
        return None
    return time.time() - t
