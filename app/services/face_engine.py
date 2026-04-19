"""
app/services/face_engine.py
Registers known residents and classifies faces in detection frames
as known or unknown.

Migrated from face_recognition to DeepFace.
"""

import logging
import pickle
import threading
import time
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from deepface import DeepFace

logger = logging.getLogger(__name__)

_UNKNOWN_LABEL = "unknown"
_TOLERANCE = 0.35              # cosine distance threshold
_UNKNOWN_MEMORY_SECONDS = 120

# In-memory registry loaded from DB on startup / updated on register
_known_embeddings: List[np.ndarray] = []
_known_names: List[str] = []
_known_ids: List[int] = []
_registry_lock = threading.Lock()

# Recurring unknown tracker
_unknown_tracker: Dict[int, float] = {}
_unknown_lock = threading.Lock()

# DeepFace model
_MODEL_NAME = "Facenet512"


# ── Helpers ──────────────────────────────────────────────────────────────

def _normalize(vec: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vec)
    if norm == 0:
        return vec
    return vec / norm


def _cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    a = _normalize(a)
    b = _normalize(b)
    return 1.0 - float(np.dot(a, b))


def _extract_embedding(img) -> Optional[np.ndarray]:
    try:
        reps = DeepFace.represent(
            img_path=img,
            model_name=_MODEL_NAME,
            enforce_detection=False,
            detector_backend="opencv"
        )

        if not reps:
            return None

        emb = reps[0]["embedding"]
        return np.array(emb, dtype=np.float32)

    except Exception as exc:
        logger.warning("DeepFace embedding failed: %s", exc)
        return None


# ── Bootstrap ────────────────────────────────────────────────────────────

def load_known_faces_from_db(rows) -> None:
    """rows = list of dicts with keys: id, name, embedding (bytes blob)"""
    global _known_embeddings, _known_names, _known_ids

    embeddings, names, ids = [], [], []

    for row in rows:
        if row["embedding"]:
            try:
                emb = pickle.loads(row["embedding"])
                embeddings.append(emb)
                names.append(row["name"])
                ids.append(row["id"])
            except Exception:
                pass

    with _registry_lock:
        _known_embeddings = embeddings
        _known_names = names
        _known_ids = ids

    logger.info("Loaded %d known faces", len(embeddings))


# ── Registration ────────────────────────────────────────────────────────

def encode_face_from_path(image_path: str) -> Optional[np.ndarray]:
    """Return face embedding or None if no face found."""
    img = cv2.imread(image_path)

    if img is None:
        return None

    return _extract_embedding(img)


def register_face(face_id: int, name: str, image_path: str) -> Optional[bytes]:
    """Compute embedding, update in-memory registry, return serialized bytes for DB."""
    emb = encode_face_from_path(image_path)

    if emb is None:
        return None

    blob = pickle.dumps(emb)

    with _registry_lock:
        _known_embeddings.append(emb)
        _known_names.append(name)
        _known_ids.append(face_id)

    return blob


def remove_face(face_id: int) -> None:
    with _registry_lock:
        try:
            idx = _known_ids.index(face_id)
            _known_embeddings.pop(idx)
            _known_names.pop(idx)
            _known_ids.pop(idx)
        except ValueError:
            pass


# ── Recognition ─────────────────────────────────────────────────────────

def classify_faces_in_frame(
    frame: np.ndarray,
    bbox_list: List[Tuple[int, int, int, int]],
) -> List[Tuple[str, bool]]:
    """
    Returns list of (name, is_known) for each bbox.
    bbox format: (x1, y1, x2, y2) YOLO style
    """

    if not bbox_list:
        return []

    results = []

    with _registry_lock:
        known = list(zip(_known_embeddings, _known_names))

    for (x1, y1, x2, y2) in bbox_list:
        crop = frame[y1:y2, x1:x2]

        if crop.size == 0:
            results.append((_UNKNOWN_LABEL, False))
            continue

        emb = _extract_embedding(crop)

        if emb is None:
            results.append((_UNKNOWN_LABEL, False))
            continue

        if not known:
            results.append((_UNKNOWN_LABEL, False))
            continue

        distances = [
            _cosine_distance(k_emb, emb)
            for k_emb, _ in known
        ]

        best_idx = int(np.argmin(distances))

        if distances[best_idx] <= _TOLERANCE:
            results.append((known[best_idx][1], True))
        else:
            results.append((_UNKNOWN_LABEL, False))

    return results


# ── Unknown-face memory ─────────────────────────────────────────────────

def record_unknown(track_id: int) -> bool:
    """Returns True if this unknown has been seen before (recurring)."""
    now = time.time()

    with _unknown_lock:
        expired = [
            k for k, t in _unknown_tracker.items()
            if now - t > _UNKNOWN_MEMORY_SECONDS
        ]

        for k in expired:
            del _unknown_tracker[k]

        recurring = track_id in _unknown_tracker
        _unknown_tracker[track_id] = now

        return recurring