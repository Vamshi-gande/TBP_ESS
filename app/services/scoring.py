"""
app/services/scoring.py
Three-Signal Scoring System (aligned with project specification).

Signal 1 — TIME:       +1 if detection occurs during night hours
Signal 2 — BEHAVIOR:   +1 if loitering OR erratic movement detected
Signal 3 — FREQUENCY:  +1 if face is unknown / novel

Maximum score = 3.

Score outcomes:
  0 → silent log (nothing notable)
  1 → snapshot saved to disk
  2 → WhatsApp snapshot + app alert
  3 → WhatsApp video + buzzer + app alert
"""
from datetime import datetime


def compute_score(
    is_unknown: bool,
    is_night: bool,
    loitering: bool,
) -> int:
    """Compute the Three-Signal suspicion score (0–3)."""
    score = 0

    # Signal 1: TIME — nighttime detection
    if is_night:
        score += 1

    # Signal 2: BEHAVIOR — loitering or erratic motion
    if loitering:
        score += 1

    # Signal 3: FREQUENCY — unknown / novel face
    if is_unknown:
        score += 1

    return score


def is_night_time(night_start: int = 20, night_end: int = 6) -> bool:
    """Returns True if current local hour is within the night window."""
    h = datetime.now().hour
    if night_start > night_end:          # e.g. 20 → 6 (crosses midnight)
        return h >= night_start or h < night_end
    return night_start <= h < night_end  # e.g. 6 → 18 (same day)


def score_label(score: int) -> str:
    if score == 0:
        return "none"
    if score == 1:
        return "low"
    if score == 2:
        return "medium"
    return "high"
