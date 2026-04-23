"""
app/api/routes/faces.py
POST   /face/register
GET    /face/list
DELETE /face/{id}
"""
import asyncio
import logging
import re
import shutil
import uuid
from pathlib import Path

import aiosqlite
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db.database import get_db
from app.models.schemas import FaceOut
from app.services import face_engine

router = APIRouter(prefix="/face", tags=["faces"])
settings = get_settings()
logger = logging.getLogger(__name__)


@router.post("/register", response_model=FaceOut)
async def register_face(
    name: str = Form(...),
    image: UploadFile = File(...),
    db: aiosqlite.Connection = Depends(get_db),
    _user=Depends(get_current_user),
):
    if not image.filename.lower().endswith((".jpg", ".jpeg", ".png")):
        raise HTTPException(status_code=400, detail="Image must be JPG or PNG")

    # Sanitize filename: remove spaces, special chars, add unique prefix
    safe_name = re.sub(r'[^\w.\-]', '_', image.filename)
    safe_name = f"{uuid.uuid4().hex[:8]}_{safe_name}"
    dest = settings.faces_dir / safe_name
    logger.info("Saving face image to: %s", dest)

    try:
        with dest.open("wb") as f:
            shutil.copyfileobj(image.file, f)
    except Exception as exc:
        logger.error("Failed to save face image: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to save image: {exc}")

    # Insert row first to get ID
    async with db.execute(
        "INSERT INTO known_faces (name, image_path) VALUES (?,?)",
        (name, str(dest)),
    ) as cur:
        face_id = cur.lastrowid
    await db.commit()
    logger.info("Face row inserted: id=%d name=%s", face_id, name)

    # Compute embedding (may take a moment on first run as models are downloaded)
    # Run in thread to avoid blocking the async event loop
    try:
        blob = await asyncio.to_thread(face_engine.register_face, face_id, name, str(dest))
    except Exception as exc:
        logger.error("Face embedding failed: %s", exc)
        await db.execute("DELETE FROM known_faces WHERE id=?", (face_id,))
        await db.commit()
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Face embedding failed: {exc}")

    if blob is None:
        # Remove DB row and file if no face found
        await db.execute("DELETE FROM known_faces WHERE id=?", (face_id,))
        await db.commit()
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="No face detected in the uploaded image")

    # Store embedding blob
    await db.execute(
        "UPDATE known_faces SET embedding=? WHERE id=?", (blob, face_id)
    )
    await db.commit()
    logger.info("Face registered successfully: id=%d name=%s", face_id, name)

    async with db.execute("SELECT * FROM known_faces WHERE id=?", (face_id,)) as cur:
        row = dict(await cur.fetchone())
    return FaceOut(id=row["id"], name=row["name"], image_path=row["image_path"], created_at=row["created_at"])


@router.get("/list", response_model=list[FaceOut])
async def list_faces(
    db: aiosqlite.Connection = Depends(get_db),
    _user=Depends(get_current_user),
):
    async with db.execute(
        "SELECT id, name, image_path, created_at FROM known_faces ORDER BY id DESC"
    ) as cur:
        rows = await cur.fetchall()
    return [FaceOut(**dict(r)) for r in rows]


@router.delete("/{face_id}", status_code=204)
async def delete_face(
    face_id: int,
    db: aiosqlite.Connection = Depends(get_db),
    _user=Depends(get_current_user),
):
    async with db.execute(
        "SELECT image_path FROM known_faces WHERE id=?", (face_id,)
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Face not found")

    # Remove image file
    Path(row["image_path"]).unlink(missing_ok=True)

    # Remove from in-memory registry
    face_engine.remove_face(face_id)

    await db.execute("DELETE FROM known_faces WHERE id=?", (face_id,))
    await db.commit()
