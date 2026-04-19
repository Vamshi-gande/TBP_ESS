"""
app/services/motion_detector.py
MOG2 background subtraction for pre-filtering frames before YOLO.

Per the project spec, MOG2 models each pixel's history using Gaussian
distributions to learn the background and identify moving objects.
This filters out static frames so YOLO only runs when motion is detected,
reducing compute by ~90%.
"""
import cv2
import logging
import numpy as np
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Minimum contour area to consider as valid motion (filters insects/noise)
_MIN_CONTOUR_AREA = 500

# Per-source MOG2 state
_subtractors: Dict[int, cv2.BackgroundSubtractorMOG2] = {}


def get_or_create_subtractor(source_id: int) -> cv2.BackgroundSubtractorMOG2:
    """Get or create a MOG2 subtractor for a source."""
    if source_id not in _subtractors:
        sub = cv2.createBackgroundSubtractorMOG2(
            history=500,
            varThreshold=25,
            detectShadows=True,
        )
        _subtractors[source_id] = sub
        logger.info("MOG2 subtractor created for source %d", source_id)
    return _subtractors[source_id]


def detect_motion(
    source_id: int,
    frame: np.ndarray,
    min_area: int = _MIN_CONTOUR_AREA,
) -> Tuple[bool, List[Tuple[int, int, int, int]]]:
    """
    Apply MOG2 background subtraction to a frame.

    Returns:
        (has_motion, bounding_boxes)
        - has_motion: True if significant motion is detected
        - bounding_boxes: list of (x, y, w, h) for each moving blob
    """
    sub = get_or_create_subtractor(source_id)

    # Apply background subtraction
    fg_mask = sub.apply(frame)

    # Remove shadows (MOG2 marks shadows as 127, foreground as 255)
    _, thresh = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)

    # Morphological operations to clean up noise
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    thresh = cv2.dilate(thresh, kernel, iterations=2)

    # Find contours
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    bboxes = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < min_area:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        bboxes.append((x, y, w, h))

    return len(bboxes) > 0, bboxes


def reset_source(source_id: int) -> None:
    """Remove MOG2 state for a disconnected source."""
    _subtractors.pop(source_id, None)
    logger.info("MOG2 subtractor reset for source %d", source_id)


def get_foreground_mask(source_id: int, frame: np.ndarray) -> Optional[np.ndarray]:
    """Get the foreground mask for visualization/debugging."""
    sub = get_or_create_subtractor(source_id)
    return sub.apply(frame)
