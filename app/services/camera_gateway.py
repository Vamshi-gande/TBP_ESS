"""
app/services/camera_gateway.py
Manages live camera / video source connections.
Each source runs in its own background thread, continuously reading frames.
"""
import asyncio
import cv2
import threading
import time
import logging
from typing import AsyncGenerator, Dict, Optional, Union

import numpy as np

logger = logging.getLogger(__name__)

_RECONNECT_DELAY = 3  # seconds


class CameraStream:
    """Thread-safe frame buffer for a single video source."""

    def __init__(self, source_id: int, uri: str):
        self.source_id = source_id
        self.uri = uri
        self._cap: Optional[cv2.VideoCapture] = None
        self._frame: Optional[np.ndarray] = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_error: Optional[str] = None

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()
        logger.info("CameraStream %d started: %s", self.source_id, self.uri)

    def stop(self) -> None:
        self._running = False
        if self._cap:
            self._cap.release()
        logger.info("CameraStream %d stopped", self.source_id)

    # ── Internal loop ──────────────────────────────────────────────────────

    def _open(self) -> bool:
        uri: Union[str, int] = self.uri
        # Webcam index
        if self.uri.isdigit():
            uri = int(self.uri)
        cap = cv2.VideoCapture(uri)
        if not cap.isOpened():
            return False
        self._cap = cap
        return True

    def _read_loop(self) -> None:
        while self._running:
            if self._cap is None or not self._cap.isOpened():
                if not self._open():
                    self._last_error = f"Cannot open source: {self.uri}"
                    logger.warning("CameraStream %d: reconnecting in %ds", self.source_id, _RECONNECT_DELAY)
                    time.sleep(_RECONNECT_DELAY)
                    continue
            ret, frame = self._cap.read()
            if not ret:
                logger.warning("CameraStream %d: frame read failed, reconnecting", self.source_id)
                self._cap.release()
                self._cap = None
                time.sleep(_RECONNECT_DELAY)
                continue
            with self._lock:
                self._frame = frame

    # ── Public API ─────────────────────────────────────────────────────────

    def get_frame(self) -> Optional[np.ndarray]:
        with self._lock:
            return self._frame.copy() if self._frame is not None else None

    def is_alive(self) -> bool:
        return self._running and (self._thread is not None and self._thread.is_alive())

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error


# ── Registry ───────────────────────────────────────────────────────────────

_streams: Dict[int, CameraStream] = {}
_registry_lock = threading.Lock()


def connect_source(source_id: int, uri: str) -> CameraStream:
    with _registry_lock:
        if source_id in _streams:
            _streams[source_id].stop()
        stream = CameraStream(source_id, uri)
        stream.start()
        _streams[source_id] = stream
        return stream


def disconnect_source(source_id: int) -> None:
    with _registry_lock:
        stream = _streams.pop(source_id, None)
        if stream:
            stream.stop()


def get_stream(source_id: int) -> Optional[CameraStream]:
    return _streams.get(source_id)


def list_active() -> Dict[int, bool]:
    return {sid: s.is_alive() for sid, s in _streams.items()}


# ── Frame utilities ────────────────────────────────────────────────────────

def extract_preview_frame(uri: str) -> Optional[np.ndarray]:
    """Open a source once, grab a single frame, release immediately."""
    uri_val: Union[str, int] = uri
    if isinstance(uri, str) and uri.isdigit():
        uri_val = int(uri)
    cap = cv2.VideoCapture(uri_val)
    if not cap.isOpened():
        return None
    ret, frame = cap.read()
    cap.release()
    return frame if ret else None


def frame_to_jpeg(frame: np.ndarray, quality: int = 80) -> bytes:
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buf.tobytes()


async def mjpeg_generator(source_id: int) -> AsyncGenerator[bytes, None]:
    """Yields MJPEG multipart boundary chunks for a StreamingResponse.
    Uses asyncio.sleep() to avoid blocking the event loop."""
    boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
    stream = get_stream(source_id)
    if stream is None:
        return
    while stream.is_alive():
        frame = stream.get_frame()
        if frame is None:
            await asyncio.sleep(0.05)
            continue
        jpeg = frame_to_jpeg(frame)
        yield boundary + jpeg + b"\r\n"
        await asyncio.sleep(0.033)  # ~30 fps cap
