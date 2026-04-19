"""
app/api/routes/camera.py
POST /camera/connect
POST /video/upload
GET  /stream/live/{source_id}
GET  /source/frame-preview/{source_id}
"""
import shutil
from pathlib import Path

import asyncpg
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse, Response

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db.database import get_db
from app.models.schemas import SourceCreate, SourceOut
from app.services import camera_gateway, surveillance_orchestrator

router = APIRouter(tags=["camera"])
settings = get_settings()


# ─── Connect a live camera ────────────────────────────────────────────────

@router.post("/camera/connect", response_model=SourceOut)
async def connect_camera(
    payload: SourceCreate,
    conn: asyncpg.Connection = Depends(get_db),
    _user=Depends(get_current_user),
):
    source_id = await conn.fetchval(
        "INSERT INTO sources (name, source_type, uri) VALUES ($1,$2,$3) RETURNING id",
        payload.name, payload.source_type, payload.uri,
    )

    # Start streaming + detection
    camera_gateway.connect_source(source_id, payload.uri)
    surveillance_orchestrator.activate_source(source_id)

    row = await conn.fetchrow("SELECT * FROM sources WHERE id=$1", source_id)
    return SourceOut(**dict(row))


# ─── Upload an MP4 video ──────────────────────────────────────────────────

@router.post("/video/upload", response_model=SourceOut)
async def upload_video(
    name: str = Form(...),
    file: UploadFile = File(...),
    conn: asyncpg.Connection = Depends(get_db),
    _user=Depends(get_current_user),
):
    if not file.filename.lower().endswith((".mp4", ".avi", ".mkv", ".mov")):
        raise HTTPException(status_code=400, detail="Unsupported video format")

    dest = settings.uploads_dir / file.filename
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    source_id = await conn.fetchval(
        "INSERT INTO sources (name, source_type, uri) VALUES ($1,$2,$3) RETURNING id",
        name, "upload", str(dest),
    )

    camera_gateway.connect_source(source_id, str(dest))
    surveillance_orchestrator.activate_source(source_id)

    row = await conn.fetchrow("SELECT * FROM sources WHERE id=$1", source_id)
    return SourceOut(**dict(row))


# ─── Live MJPEG stream ────────────────────────────────────────────────────

@router.get("/stream/live/{source_id}")
async def live_stream(
    source_id: int,
    _user=Depends(get_current_user),
):
    stream = camera_gateway.get_stream(source_id)
    if stream is None:
        raise HTTPException(status_code=404, detail="Source not active")

    return StreamingResponse(
        camera_gateway.mjpeg_generator(source_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


# ─── Preview frame ────────────────────────────────────────────────────────

@router.get("/source/frame-preview/{source_id}")
async def frame_preview(
    source_id: int,
    conn: asyncpg.Connection = Depends(get_db),
):
    """Returns a single JPEG snapshot for the visual ROI editor."""
    # Try live stream first
    stream = camera_gateway.get_stream(source_id)
    if stream:
        frame = stream.get_frame()
        if frame is not None:
            return Response(
                content=camera_gateway.frame_to_jpeg(frame),
                media_type="image/jpeg",
            )

    # Fallback: open source uri directly
    row = await conn.fetchrow("SELECT uri FROM sources WHERE id=$1", source_id)
    if not row:
        raise HTTPException(status_code=404, detail="Source not found")

    frame = camera_gateway.extract_preview_frame(row["uri"])
    if frame is None:
        raise HTTPException(status_code=503, detail="Cannot grab frame from source")

    return Response(content=camera_gateway.frame_to_jpeg(frame), media_type="image/jpeg")


# ─── List / deactivate sources ────────────────────────────────────────────

@router.get("/sources", response_model=list[SourceOut])
async def list_sources(conn: asyncpg.Connection = Depends(get_db), _user=Depends(get_current_user)):
    rows = await conn.fetch("SELECT * FROM sources ORDER BY id DESC")
    return [SourceOut(**dict(r)) for r in rows]


@router.delete("/sources/{source_id}", status_code=204)
async def delete_source(
    source_id: int,
    conn: asyncpg.Connection = Depends(get_db),
    _user=Depends(get_current_user),
):
    surveillance_orchestrator.deactivate_source(source_id)
    camera_gateway.disconnect_source(source_id)
    await conn.execute("DELETE FROM sources WHERE id=$1", source_id)
