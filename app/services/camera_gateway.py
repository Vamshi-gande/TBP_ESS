"""
app/services/camera_gateway.py
Manages live camera / video source connections.
Each source runs in its own background thread, continuously reading frames.
"""
import cv2
import threading
import time
import logging
from pathlib import Path
from typing import Dict, Optional, Generator
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
        uri: str | int = self.uri

    # Webcam source like "0", "1"
        if self.uri.isdigit():
            cam_index = int(self.uri)

        # Windows webcam backend
            cap = cv2.VideoCapture(cam_index, cv2.CAP_DSHOW)

        # Stable defaults
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 30)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        else:
            uri = self.uri
            cap = cv2.VideoCapture(uri)

        if not cap.isOpened():
            return False

        self._cap = cap
        return True

    def _read_loop(self) -> None:
        is_file_source = not self.uri.isdigit() and "://" not in self.uri

        while self._running:

            if self._cap is None or not self._cap.isOpened():
                if not self._open():
                    self._last_error = f"Cannot open source: {self.uri}"
                    logger.warning(
                        "CameraStream %d: reconnecting in %ds",
                        self.source_id,
                        _RECONNECT_DELAY
                    )
                    time.sleep(_RECONNECT_DELAY)
                    continue

                # Webcam warm-up time
                if self.uri.isdigit():
                    time.sleep(1.5)

            ret, frame = self._cap.read()

            if not ret or frame is None:

            # Loop video files
                if is_file_source and self._cap is not None:
                    self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, frame = self._cap.read()

                if not ret or frame is None:
                    logger.warning(
                        "CameraStream %d: frame read failed",
                        self.source_id
                    )
                    time.sleep(0.1)
                    continue

            with self._lock:
                self._frame = frame

        # Keep video files real-time paced
            if is_file_source:
                time.sleep(1 / 30.0)
            else:
                time.sleep(0.01)
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
    uri_val: str | int = uri
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


def mjpeg_generator(source_id: int) -> Generator[bytes, None, None]:
    """Yields MJPEG multipart boundary chunks for a StreamingResponse."""
    boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
    stream = get_stream(source_id)
    if stream is None:
        return
    while True:
        frame = stream.get_frame()
        if frame is None:
            time.sleep(0.05)
            continue
        jpeg = frame_to_jpeg(frame)
        yield boundary + jpeg + b"\r\n"
        time.sleep(0.033)  # ~30 fps cap
