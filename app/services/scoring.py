"""
app/services/scoring.py
Computes a suspicion score for each detection event.

Score breakdown:
  +1  unknown person
  +1  inside red / critical zone
  +1  night time
  +1  loitering detected

Thresholds (from DB settings):
  0-1 → log only
  2   → app alert (WebSocket)
  3+  → app alert + WhatsApp / SMS
"""
from datetime import datetime


def compute_score(
    is_unknown: bool,
    in_danger_zone: bool,   # zone_type in ('red', 'critical')
    loitering: bool,
    night_start: int = 20,
    night_end: int = 6,
) -> int:
    score = 0
    if is_unknown:
        score += 1
    if in_danger_zone:
        score += 1
    if _is_night(night_start, night_end):
        score += 1
    if loitering:
        score += 1
    return score


def _is_night(start_hour: int, end_hour: int) -> bool:
    """Returns True if current local hour is within the night window."""
    h = datetime.now().hour
    if start_hour > end_hour:          # e.g. 20 → 6 (crosses midnight)
        return h >= start_hour or h < end_hour
    return start_hour <= h < end_hour  # e.g. 22 → 5 same day


def score_label(score: int) -> str:
    if score <= 1:
        return "low"
    if score == 2:
        return "medium"
    return "high"
