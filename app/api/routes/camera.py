"""
app/api/routes/camera.py
POST /camera/connect
POST /video/upload
GET  /stream/live/{source_id}
GET  /source/frame-preview/{source_id}
GET  /camera/discover
"""
import shutil
from pathlib import Path
from typing import Optional

import aiosqlite
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse, Response

from app.api.deps import get_current_user, oauth2_scheme
from app.core.config import get_settings
from app.core.security import decode_token
from app.db.database import get_db
from app.models.schemas import SourceCreate, SourceOut
from app.services import camera_gateway, surveillance_orchestrator

router = APIRouter(tags=["camera"])
settings = get_settings()


def get_stream_user(
    bearer_token: Optional[str] = Depends(oauth2_scheme),
    query_token: Optional[str] = Query(default=None, alias="token"),
) -> dict:
    """Allow MJPEG auth from either Authorization header or ?token query."""
    token = bearer_token or query_token
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return payload


# ─── Connect a live camera ────────────────────────────────────────────────

@router.post("/camera/connect", response_model=SourceOut)
async def connect_camera(
    payload: SourceCreate,
    db: aiosqlite.Connection = Depends(get_db),
    _user=Depends(get_current_user),
):
    async with db.execute(
        "INSERT INTO sources (name, source_type, uri) VALUES (?,?,?)",
        (payload.name, payload.source_type, payload.uri),
    ) as cur:
        source_id = cur.lastrowid
    await db.commit()

    # Start streaming + detection
    camera_gateway.connect_source(source_id, payload.uri)
    surveillance_orchestrator.activate_source(source_id)

    async with db.execute("SELECT * FROM sources WHERE id=?", (source_id,)) as cur:
        row = dict(await cur.fetchone())
    return SourceOut(**row)


# ─── Upload an MP4 video ──────────────────────────────────────────────────

@router.post("/video/upload", response_model=SourceOut)
async def upload_video(
    name: str = Form(...),
    file: UploadFile = File(...),
    db: aiosqlite.Connection = Depends(get_db),
    _user=Depends(get_current_user),
):
    if not file.filename.lower().endswith((".mp4", ".avi", ".mkv", ".mov")):
        raise HTTPException(status_code=400, detail="Unsupported video format")

    dest = settings.uploads_dir / file.filename
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    async with db.execute(
        "INSERT INTO sources (name, source_type, uri) VALUES (?,?,?)",
        (name, "upload", str(dest)),
    ) as cur:
        source_id = cur.lastrowid
    await db.commit()

    camera_gateway.connect_source(source_id, str(dest))
    surveillance_orchestrator.activate_source(source_id)

    async with db.execute("SELECT * FROM sources WHERE id=?", (source_id,)) as cur:
        row = dict(await cur.fetchone())
    return SourceOut(**row)


# ─── Live MJPEG stream ────────────────────────────────────────────────────

@router.get("/stream/live/{source_id}")
async def live_stream(
    source_id: int,
    db: aiosqlite.Connection = Depends(get_db),
    _user=Depends(get_stream_user),
):
    """
    Returns an MJPEG stream for any source type.
    All sources are proxied through the backend MJPEG generator so that
    the dashboard can display them in a simple <img> tag with ?token= auth.
    """
    # Verify source exists
    async with db.execute(
        "SELECT source_type, uri FROM sources WHERE id=?",
        (source_id,),
    ) as cur:
        row = await cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Source not found")

    # All source types are streamed via the backend MJPEG generator
    stream = camera_gateway.get_stream(source_id)

    if stream is None:
        raise HTTPException(status_code=404, detail="Source not active")

    return StreamingResponse(
        camera_gateway.mjpeg_generator(source_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Connection": "keep-alive",
            "X-Content-Type-Options": "nosniff",
        },
    )


# ─── Preview frame ────────────────────────────────────────────────────────

@router.get("/source/frame-preview/{source_id}")
async def frame_preview(
    source_id: int,
    db: aiosqlite.Connection = Depends(get_db),
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
    async with db.execute("SELECT uri FROM sources WHERE id=?", (source_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Source not found")

    frame = camera_gateway.extract_preview_frame(row["uri"])
    if frame is None:
        raise HTTPException(status_code=503, detail="Cannot grab frame from source")

    return Response(content=camera_gateway.frame_to_jpeg(frame), media_type="image/jpeg")


# ─── Discover webcams ─────────────────────────────────────────────────────

@router.get("/camera/discover")
async def discover_webcams(
    _user=Depends(get_current_user),
):
    """Probe local webcam indices 0-9 and return available cameras.
    Useful for finding external USB webcams."""
    cameras = camera_gateway.discover_webcams()
    return {"cameras": cameras}


# ─── List / deactivate sources ────────────────────────────────────────────

@router.get("/sources", response_model=list[SourceOut])
async def list_sources(db: aiosqlite.Connection = Depends(get_db), _user=Depends(get_current_user)):
    async with db.execute("SELECT * FROM sources ORDER BY id DESC") as cur:
        rows = await cur.fetchall()
    return [SourceOut(**dict(r)) for r in rows]


@router.delete("/sources/{source_id}", status_code=204)
async def delete_source(
    source_id: int,
    db: aiosqlite.Connection = Depends(get_db),
    _user=Depends(get_current_user),
):
    surveillance_orchestrator.deactivate_source(source_id)
    camera_gateway.disconnect_source(source_id)
    await db.execute("DELETE FROM sources WHERE id=?", (source_id,))
    await db.commit()
