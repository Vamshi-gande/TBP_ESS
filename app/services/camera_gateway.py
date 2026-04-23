"""
app/services/camera_gateway.py
Manages live camera / video source connections.
Supports:
- Laptop webcams (0,1,2...)
- DroidCam webcam
- IP Webcam (/video MJPEG)
- Uploaded/local video files
"""

import cv2
import threading
import time
import logging
from typing import Dict, Optional, Generator
import numpy as np

logger = logging.getLogger(__name__)

_RECONNECT_DELAY = 3


class CameraStream:
    def __init__(self, source_id: int, uri: str):
        self.source_id = source_id
        self.uri = uri.strip()
        self._cap: Optional[cv2.VideoCapture] = None
        self._frame: Optional[np.ndarray] = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_error: Optional[str] = None

    # ──────────────────────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────────────────────

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

    # ──────────────────────────────────────────────────────────────
    # Source open logic
    # ──────────────────────────────────────────────────────────────

    def _open(self) -> bool:
        uri = self.uri

        try:
            # Local webcam source: "0", "1"
            if uri.isdigit():
                cam_index = int(uri)

                cap = cv2.VideoCapture(cam_index, cv2.CAP_DSHOW)

                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                cap.set(cv2.CAP_PROP_FPS, 30)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            # IP Webcam / HTTP / RTSP / DroidCam URL
            elif uri.startswith("http://") or uri.startswith("https://") or uri.startswith("rtsp://"):
                cap = cv2.VideoCapture(uri, cv2.CAP_FFMPEG)

            # Uploaded file / mp4 / avi
            else:
                cap = cv2.VideoCapture(uri)

            if not cap.isOpened():
                return False

            self._cap = cap
            self._last_error = None
            return True

        except Exception as exc:
            self._last_error = str(exc)
            return False

    # ──────────────────────────────────────────────────────────────
    # Read loop
    # ──────────────────────────────────────────────────────────────

    def _read_loop(self) -> None:
        is_file_source = (
            not self.uri.isdigit()
            and not self.uri.startswith("http://")
            and not self.uri.startswith("https://")
            and not self.uri.startswith("rtsp://")
        )

        while self._running:

            if self._cap is None or not self._cap.isOpened():

                if not self._open():
                    logger.warning(
                        "CameraStream %d reconnecting in %ds",
                        self.source_id,
                        _RECONNECT_DELAY
                    )
                    time.sleep(_RECONNECT_DELAY)
                    continue

                # warm-up for webcam
                if self.uri.isdigit():
                    time.sleep(1.5)

            ret, frame = self._cap.read()

            if not ret or frame is None:

                # loop local files
                if is_file_source and self._cap is not None:
                    self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, frame = self._cap.read()

                if not ret or frame is None:
                    logger.warning(
                        "CameraStream %d frame read failed",
                        self.source_id
                    )

                    # reconnect network cams
                    if not is_file_source:
                        if self._cap:
                            self._cap.release()
                            self._cap = None

                    time.sleep(0.2)
                    continue

            with self._lock:
                self._frame = frame

            if is_file_source:
                time.sleep(1 / 30.0)
            else:
                time.sleep(0.01)

    # ──────────────────────────────────────────────────────────────
    # Public
    # ──────────────────────────────────────────────────────────────

    def get_frame(self) -> Optional[np.ndarray]:
        with self._lock:
            return self._frame.copy() if self._frame is not None else None

    def is_alive(self) -> bool:
        return self._running and self._thread is not None and self._thread.is_alive()

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error


# ──────────────────────────────────────────────────────────────
# Registry
# ──────────────────────────────────────────────────────────────

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


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def extract_preview_frame(uri: str) -> Optional[np.ndarray]:

    stream = CameraStream(-1, uri)

    if not stream._open():
        return None

    ret, frame = stream._cap.read()
    stream._cap.release()

    return frame if ret else None


def frame_to_jpeg(frame: np.ndarray, quality: int = 80) -> bytes:
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buf.tobytes()


def mjpeg_generator(source_id: int) -> Generator[bytes, None, None]:

    stream = get_stream(source_id)

    if stream is None:
        return

    no_frame_count = 0
    max_no_frame = 600  # ~30 seconds at 0.05s sleep

    while stream.is_alive():
        frame = stream.get_frame()

        if frame is None:
            no_frame_count += 1
            if no_frame_count >= max_no_frame:
                logger.warning(
                    "mjpeg_generator: source %d timed out waiting for frames",
                    source_id,
                )
                break

            # Yield a placeholder frame so the <img> tag stays alive
            if no_frame_count % 20 == 1:  # every ~1 second
                placeholder = _make_placeholder_frame(
                    f"Source {source_id}: waiting for camera..."
                )
                jpeg = frame_to_jpeg(placeholder)
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + jpeg +
                    b"\r\n"
                )

            time.sleep(0.05)
            continue

        no_frame_count = 0  # reset on successful frame
        jpeg = frame_to_jpeg(frame)

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n"
            + jpeg +
            b"\r\n"
        )

        time.sleep(0.033)


def _make_placeholder_frame(text: str = "Waiting for camera...") -> np.ndarray:
    """Create a dark placeholder frame with centered text."""
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    frame[:] = (20, 20, 30)  # dark background

    # Draw text centered
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.7
    thickness = 2
    text_size = cv2.getTextSize(text, font, font_scale, thickness)[0]
    x = (640 - text_size[0]) // 2
    y = (480 + text_size[1]) // 2
    cv2.putText(frame, text, (x, y), font, font_scale, (100, 200, 255), thickness)
    return frame


def discover_webcams(max_index: int = 10) -> list:
    """Probe camera indices 0..max_index-1 via DirectShow and return available ones."""
    available = []
    for idx in range(max_index):
        try:
            cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
            if cap.isOpened():
                ret, _ = cap.read()
                if ret:
                    # Try to get a friendly name (not always available)
                    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    available.append({
                        "index": idx,
                        "name": f"Camera {idx}",
                        "resolution": f"{w}x{h}",
                    })
            cap.release()
        except Exception:
            pass
    return available