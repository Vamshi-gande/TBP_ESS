"""
app/api/routes/faces.py
POST   /face/register
GET    /face/list
DELETE /face/{id}
"""
import shutil
from pathlib import Path

import asyncpg
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db.database import get_db
from app.models.schemas import FaceOut
from app.services import face_engine

router = APIRouter(prefix="/face", tags=["faces"])
settings = get_settings()


@router.post("/register", response_model=FaceOut)
async def register_face(
    name: str = Form(...),
    image: UploadFile = File(...),
    conn: asyncpg.Connection = Depends(get_db),
    _user=Depends(get_current_user),
):
    if not image.filename.lower().endswith((".jpg", ".jpeg", ".png")):
        raise HTTPException(status_code=400, detail="Image must be JPG or PNG")

    # Save image to faces storage
    dest = settings.faces_dir / image.filename
    with dest.open("wb") as f:
        shutil.copyfileobj(image.file, f)

    # Insert row first to get ID
    face_id = await conn.fetchval(
        "INSERT INTO known_faces (name, image_path) VALUES ($1,$2) RETURNING id",
        name, str(dest),
    )

    # Compute embedding
    blob = face_engine.register_face(face_id, name, str(dest))
    if blob is None:
        # Remove DB row and file if no face found
        await conn.execute("DELETE FROM known_faces WHERE id=$1", face_id)
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="No face detected in the uploaded image")

    # Store embedding blob
    await conn.execute(
        "UPDATE known_faces SET embedding=$1 WHERE id=$2", blob, face_id
    )

    row = await conn.fetchrow("SELECT * FROM known_faces WHERE id=$1", face_id)
    return FaceOut(id=row["id"], name=row["name"], image_path=row["image_path"], created_at=str(row["created_at"]))


@router.get("/list", response_model=list[FaceOut])
async def list_faces(
    conn: asyncpg.Connection = Depends(get_db),
    _user=Depends(get_current_user),
):
    rows = await conn.fetch(
        "SELECT id, name, image_path, created_at FROM known_faces ORDER BY id DESC"
    )
    return [FaceOut(id=r["id"], name=r["name"], image_path=r["image_path"], created_at=str(r["created_at"])) for r in rows]


@router.delete("/{face_id}", status_code=204)
async def delete_face(
    face_id: int,
    conn: asyncpg.Connection = Depends(get_db),
    _user=Depends(get_current_user),
):
    row = await conn.fetchrow(
        "SELECT image_path FROM known_faces WHERE id=$1", face_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Face not found")

    # Remove image file
    Path(row["image_path"]).unlink(missing_ok=True)

    # Remove from in-memory registry
    face_engine.remove_face(face_id)

    await conn.execute("DELETE FROM known_faces WHERE id=$1", face_id)
