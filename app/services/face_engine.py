"""
app/services/face_engine.py
Registers known residents and classifies faces in detection frames as known
or unknown.

Pipeline:
- YOLO gives us a *person* bounding box (head + torso + legs).
- We crop the upper portion of that bbox (where a face would be) and run an
  OpenCV Haar cascade to find the actual face. Haar ships with opencv-python,
  is fast on CPU, and handles ESP32-CAM resolutions fine.
- The face crop is then fed to DeepFace (Facenet512). Embedding dimension is
  validated against what the registry expects so a stale blob from a previous
  model can never crash the pipeline silently.
"""

import logging
import pickle
import threading
import time
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

_UNKNOWN_LABEL = "unknown"
_TOLERANCE = 0.30              # cosine distance threshold for Facenet512
_UNKNOWN_MEMORY_SECONDS = 120
_MIN_PERSON_CROP_PX = 60       # skip person crops smaller than this
_MIN_FACE_PX = 24              # smallest face size Haar will accept

_MODEL_NAME = "Facenet512"
_EMBED_DIM = 512               # must match _MODEL_NAME's output_shape

# In-memory registry loaded from DB on startup / updated on register
_known_embeddings: List[np.ndarray] = []
_known_names: List[str] = []
_known_ids: List[int] = []
_registry_lock = threading.Lock()

# Recurring unknown tracker
_unknown_tracker: Dict[int, float] = {}
_unknown_lock = threading.Lock()

# Model warm-up flag
_model_warmed = False
_warmup_lock = threading.Lock()

# Lazy-loaded Haar cascade
_face_cascade: Optional[cv2.CascadeClassifier] = None
_cascade_lock = threading.Lock()


# ── Helpers ──────────────────────────────────────────────────────────────

def _normalize(vec: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vec)
    if norm == 0:
        return vec
    return vec / norm


def _cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    return 1.0 - float(np.dot(_normalize(a), _normalize(b)))


def _get_cascade() -> cv2.CascadeClassifier:
    global _face_cascade
    with _cascade_lock:
        if _face_cascade is None:
            path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            _face_cascade = cv2.CascadeClassifier(path)
        return _face_cascade


def _detect_face_in_person_crop(person_crop: np.ndarray) -> Optional[np.ndarray]:
    """Look for a face in the upper portion of a person crop. Returns the face
    BGR sub-image (with a small margin) or None if nothing usable is found."""
    if person_crop.size == 0:
        return None

    h, w = person_crop.shape[:2]
    # Faces live in the top of a person bbox — crop to upper 60% to cut work
    upper = person_crop[: max(1, int(h * 0.6)), :]

    cascade = _get_cascade()
    gray = cv2.cvtColor(upper, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)

    faces = cascade.detectMultiScale(
        gray,
        scaleFactor=1.15,
        minNeighbors=4,
        minSize=(_MIN_FACE_PX, _MIN_FACE_PX),
    )
    if len(faces) == 0:
        return None

    # Prefer the largest face — most likely the actual subject
    fx, fy, fw, fh = max(faces, key=lambda b: b[2] * b[3])

    # Add a small margin so DeepFace gets some context around the face
    margin = int(0.1 * max(fw, fh))
    x1 = max(0, fx - margin)
    y1 = max(0, fy - margin)
    x2 = min(upper.shape[1], fx + fw + margin)
    y2 = min(upper.shape[0], fy + fh + margin)
    return upper[y1:y2, x1:x2]


def _warmup_model():
    """Pre-load the recognition model so the first real call is fast."""
    global _model_warmed
    with _warmup_lock:
        if _model_warmed:
            return
        try:
            from deepface import DeepFace
            dummy = np.full((160, 160, 3), 128, dtype=np.uint8)
            DeepFace.represent(
                img_path=dummy,
                model_name=_MODEL_NAME,
                enforce_detection=False,
                detector_backend="skip",
            )
            _model_warmed = True
            logger.info("DeepFace %s model pre-warmed", _MODEL_NAME)
        except Exception as exc:
            logger.warning("Model warmup failed (will retry on first use): %s", exc)


def _embed_face(face_crop: np.ndarray) -> Optional[np.ndarray]:
    """Compute an embedding for a real face crop. Returns None on failure."""
    try:
        from deepface import DeepFace

        # Facenet512 input is 160x160; DeepFace handles resize, but downscaling
        # very large crops first saves memory churn.
        h, w = face_crop.shape[:2]
        if max(h, w) > 320:
            scale = 320.0 / max(h, w)
            face_crop = cv2.resize(face_crop, None, fx=scale, fy=scale,
                                   interpolation=cv2.INTER_AREA)

        reps = DeepFace.represent(
            img_path=face_crop,
            model_name=_MODEL_NAME,
            enforce_detection=False,
            detector_backend="skip",  # the crop IS already a face
        )
        if not reps:
            return None

        emb = np.array(reps[0]["embedding"], dtype=np.float32)
        if emb.shape[0] != _EMBED_DIM:
            logger.error("Embedding dim %d != expected %d", emb.shape[0], _EMBED_DIM)
            return None
        return emb
    except Exception as exc:
        logger.warning("Embedding extraction failed: %s", exc)
        return None


# ── Bootstrap ────────────────────────────────────────────────────────────

def load_known_faces_from_db(rows) -> List[Tuple[int, bytes]]:
    """Load known faces into the in-memory registry.

    Any blob whose dimension does not match the current model is re-encoded
    from the original image_path on disk. Returns a list of
    (face_id, new_blob) pairs that the caller should persist back to the DB.
    Entries that cannot be recovered are dropped from the registry.
    """
    global _known_embeddings, _known_names, _known_ids

    embeddings: List[np.ndarray] = []
    names: List[str] = []
    ids: List[int] = []
    rewrites: List[Tuple[int, bytes]] = []

    for row in rows:
        face_id = row["id"]
        name = row["name"]
        blob = row["embedding"]
        image_path = row.get("image_path") if isinstance(row, dict) else None

        emb: Optional[np.ndarray] = None
        if blob:
            try:
                emb = pickle.loads(blob)
                if not isinstance(emb, np.ndarray) or emb.shape[0] != _EMBED_DIM:
                    logger.warning(
                        "Face id=%s name=%s has stale embedding "
                        "(dim=%s, expected %d) — re-encoding",
                        face_id, name,
                        getattr(emb, "shape", ["?"])[0] if emb is not None else "?",
                        _EMBED_DIM,
                    )
                    emb = None
            except Exception as exc:
                logger.warning("Face id=%s blob unpickle failed: %s", face_id, exc)
                emb = None

        if emb is None and image_path:
            emb = encode_face_from_path(image_path)
            if emb is not None:
                rewrites.append((face_id, pickle.dumps(emb)))
                logger.info("Re-encoded face id=%s name=%s", face_id, name)

        if emb is None:
            logger.warning(
                "Face id=%s name=%s could not be loaded — dropping from registry",
                face_id, name,
            )
            continue

        embeddings.append(emb)
        names.append(name)
        ids.append(face_id)

    with _registry_lock:
        _known_embeddings = embeddings
        _known_names = names
        _known_ids = ids

    logger.info("Loaded %d known faces (re-encoded %d)", len(embeddings), len(rewrites))

    threading.Thread(target=_warmup_model, daemon=True).start()
    return rewrites


# ── Registration ────────────────────────────────────────────────────────

def encode_face_from_path(image_path: str) -> Optional[np.ndarray]:
    """Locate and embed the face in a registration image."""
    img = cv2.imread(image_path)
    if img is None:
        logger.warning("Could not read registration image: %s", image_path)
        return None

    # For registration we let DeepFace do the face detection (opencv backend)
    # so the user can upload a wider photo and we still find the face.
    try:
        from deepface import DeepFace
        reps = DeepFace.represent(
            img_path=img,
            model_name=_MODEL_NAME,
            enforce_detection=False,
            detector_backend="opencv",
        )
        if not reps:
            return None
        emb = np.array(reps[0]["embedding"], dtype=np.float32)
        if emb.shape[0] != _EMBED_DIM:
            logger.error("Registration produced %d-dim embedding (expected %d)",
                         emb.shape[0], _EMBED_DIM)
            return None
        return emb
    except Exception as exc:
        logger.warning("Registration embedding failed: %s", exc)
        return None


def register_face(face_id: int, name: str, image_path: str) -> Optional[bytes]:
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
    """For each (x1,y1,x2,y2) person bbox return (name, is_known).

    Iterates every bbox so multi-person frames are fully handled in one call.
    Any dim-mismatched registry entry is skipped, never raised.
    """
    if not bbox_list:
        return []

    with _registry_lock:
        # Filter defensively — only compare against entries that match the
        # current model's dimension. Cannot crash even if registry got dirty.
        known = [
            (e, n) for e, n in zip(_known_embeddings, _known_names)
            if isinstance(e, np.ndarray) and e.shape[0] == _EMBED_DIM
        ]

    results: List[Tuple[str, bool]] = []
    H, W = frame.shape[:2]

    for (x1, y1, x2, y2) in bbox_list:
        x1 = max(0, x1); y1 = max(0, y1)
        x2 = min(W, x2); y2 = min(H, y2)
        if (x2 - x1) < _MIN_PERSON_CROP_PX or (y2 - y1) < _MIN_PERSON_CROP_PX:
            results.append((_UNKNOWN_LABEL, False))
            continue

        person_crop = frame[y1:y2, x1:x2]
        face_crop = _detect_face_in_person_crop(person_crop)
        if face_crop is None or face_crop.size == 0:
            # No face visible in this person bbox — not recognisable, but
            # don't pretend they're "unknown" either; the caller decides.
            results.append((_UNKNOWN_LABEL, False))
            continue

        emb = _embed_face(face_crop)
        if emb is None or not known:
            results.append((_UNKNOWN_LABEL, False))
            continue

        distances = [_cosine_distance(k_emb, emb) for k_emb, _ in known]
        best_idx = int(np.argmin(distances))
        if distances[best_idx] <= _TOLERANCE:
            results.append((known[best_idx][1], True))
        else:
            results.append((_UNKNOWN_LABEL, False))

    return results


# ── Unknown-face memory ─────────────────────────────────────────────────

def record_unknown(track_id: int) -> bool:
    """Returns True if this unknown has been seen recently (recurring)."""
    now = time.time()
    with _unknown_lock:
        expired = [k for k, t in _unknown_tracker.items()
                   if now - t > _UNKNOWN_MEMORY_SECONDS]
        for k in expired:
            del _unknown_tracker[k]
        recurring = track_id in _unknown_tracker
        _unknown_tracker[track_id] = now
        return recurring
