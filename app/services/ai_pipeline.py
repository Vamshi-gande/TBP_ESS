"""
app/services/ai_pipeline.py
Continuous person detection using YOLOv8 Nano on GPU.
Runs per-source in background threads; other services consume results via callbacks.

Optimizations:
- Uses CUDA GPU for inference when available (GTX 1650)
- Resizes frames to 416px for faster detection
- Frame-skip: processes every 3rd frame, reuses last detections for skipped frames
"""
import threading
import time
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Callable, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class Detection:
    track_id: Optional[int]
    bbox: Tuple[int, int, int, int]   # x1, y1, x2, y2
    confidence: float
    label: str = "person"


@dataclass
class PipelineResult:
    source_id: int
    frame: np.ndarray
    detections: List[Detection] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


ResultCallback = Callable[[PipelineResult], None]

_workers: Dict[int, "DetectionWorker"] = {}
_workers_lock = threading.Lock()

# Lazy-loaded model shared across all workers
_model = None
_model_lock = threading.Lock()
_device = None    # "cuda" or "cpu"


def _get_model():
    global _model, _device
    with _model_lock:
        if _model is None:
            import torch
            from ultralytics import YOLO
            from app.core.config import get_settings

            # Determine device
            if torch.cuda.is_available():
                _device = "cuda"
                gpu_name = torch.cuda.get_device_name(0)
                vram = torch.cuda.get_device_properties(0).total_memory / (1024**3)
                logger.info("🚀 CUDA GPU detected: %s (%.1f GB VRAM)", gpu_name, vram)
            else:
                _device = "cpu"
                logger.warning("⚠️  No CUDA GPU found — running YOLO on CPU (slow)")

            # torch >=2.6 defaults weights_only=True, which rejects ultralytics' pickled
            # DetectionModel class. Load with weights_only=False (trusted local weight file).
            _orig_load = torch.load
            torch.load = lambda *a, **kw: _orig_load(*a, **{**kw, "weights_only": False})
            try:
                _model = YOLO(get_settings().YOLO_MODEL)
                # Move model to GPU
                if _device == "cuda":
                    _model.to(_device)
                    logger.info("YOLOv8 model loaded and moved to GPU")
                else:
                    logger.info("YOLOv8 model loaded (CPU)")
            finally:
                torch.load = _orig_load
        return _model


class DetectionWorker:
    def __init__(self, source_id: int, callback: ResultCallback):
        self.source_id = source_id
        self.callback = callback
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        from app.services.camera_gateway import get_stream
        from app.core.config import get_settings
        conf_threshold = get_settings().DETECTION_CONFIDENCE
        model = _get_model()

        frame_count = 0
        skip_interval = 2          # Process every 2nd frame (was every frame)
        last_detections: List[Detection] = []

        while self._running:
            stream = get_stream(self.source_id)
            if stream is None:
                time.sleep(0.5)
                continue
            frame = stream.get_frame()
            if frame is None:
                time.sleep(0.05)
                continue

            frame_count += 1

            # Frame skip: reuse last detections for intermediate frames
            if frame_count % skip_interval != 0 and last_detections:
                self.callback(PipelineResult(
                    source_id=self.source_id,
                    frame=frame,
                    detections=last_detections,
                ))
                time.sleep(0.03)
                continue

            try:
                t0 = time.perf_counter()
                results = model.track(
                    frame,
                    persist=True,
                    classes=[0],          # class 0 = person in COCO
                    conf=conf_threshold,
                    verbose=False,
                    imgsz=416,            # Smaller input = faster inference
                    device=_device,       # Use GPU
                )
                elapsed = (time.perf_counter() - t0) * 1000

                detections: List[Detection] = []
                if results and results[0].boxes is not None:
                    boxes = results[0].boxes
                    for i, box in enumerate(boxes):
                        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                        conf = float(box.conf[0])
                        track_id = int(box.id[0]) if box.id is not None else None
                        detections.append(Detection(
                            track_id=track_id,
                            bbox=(x1, y1, x2, y2),
                            confidence=conf,
                        ))

                last_detections = detections

                # Log timing periodically
                if frame_count % 30 == 0:
                    logger.info(
                        "YOLO source=%d: %.1fms (%s), %d persons",
                        self.source_id, elapsed, _device, len(detections)
                    )

                self.callback(PipelineResult(
                    source_id=self.source_id,
                    frame=frame,
                    detections=detections,
                ))
            except Exception as exc:
                logger.exception("Detection error on source %d: %s", self.source_id, exc)

            time.sleep(0.03)   # ~30 fps detection rate (GPU can handle this)


# ── Public API ────────────────────────────────────────────────────────────

def start_detection(source_id: int, callback: ResultCallback) -> None:
    with _workers_lock:
        if source_id in _workers:
            _workers[source_id].stop()
        worker = DetectionWorker(source_id, callback)
        worker.start()
        _workers[source_id] = worker
        logger.info("Detection started for source %d", source_id)


def stop_detection(source_id: int) -> None:
    with _workers_lock:
        w = _workers.pop(source_id, None)
        if w:
            w.stop()


def draw_detections(frame: np.ndarray, detections: List[Detection]) -> np.ndarray:
    """Utility: draw bounding boxes on a copy of frame."""
    import cv2
    out = frame.copy()
    for d in detections:
        x1, y1, x2, y2 = d.bbox
        label = f"{d.label} {d.track_id or ''} {d.confidence:.2f}"
        cv2.rectangle(out, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(out, label, (x1, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    return out
