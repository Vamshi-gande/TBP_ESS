"""
app/api/routes/alerts.py
GET /alerts
GET /alerts/{id}
GET /history
"""
from typing import Optional

import aiosqlite
from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse

from app.api.deps import get_current_user
from app.db.database import get_db
from app.models.schemas import AlertOut, HistoryOut

router = APIRouter(tags=["alerts"])


@router.get("/alerts", response_model=list[AlertOut])
async def get_alerts(
    source_id: Optional[int] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: aiosqlite.Connection = Depends(get_db),
    _user=Depends(get_current_user),
):
    if source_id is not None:
        async with db.execute(
            "SELECT * FROM alerts WHERE source_id=? ORDER BY id DESC LIMIT ? OFFSET ?",
            (source_id, limit, offset),
        ) as cur:
            rows = await cur.fetchall()
    else:
        async with db.execute(
            "SELECT * FROM alerts ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ) as cur:
            rows = await cur.fetchall()

    return [
        AlertOut(
            id=r["id"],
            source_id=r["source_id"],
            alert_type=r["alert_type"],
            suspicion_score=r["suspicion_score"],
            snapshot_path=r["snapshot_path"],
            clip_path=r["clip_path"],
            meta=r["meta"],
            notified=bool(r["notified"]),
            created_at=r["created_at"],
        )
        for r in rows
    ]


@router.get("/alerts/{alert_id}/snapshot")
async def alert_snapshot(
    alert_id: int,
    db: aiosqlite.Connection = Depends(get_db),
    _user=Depends(get_current_user),
):
    async with db.execute(
        "SELECT snapshot_path FROM alerts WHERE id=?", (alert_id,)
    ) as cur:
        row = await cur.fetchone()
    if not row or not row["snapshot_path"]:
        from fastapi import HTTPException
        raise HTTPException(404, "Snapshot not found")
    return FileResponse(row["snapshot_path"], media_type="image/jpeg")


@router.get("/history", response_model=list[HistoryOut])
async def get_history(
    source_id: Optional[int] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    db: aiosqlite.Connection = Depends(get_db),
    _user=Depends(get_current_user),
):
    if source_id is not None:
        async with db.execute(
            "SELECT * FROM history WHERE source_id=? ORDER BY id DESC LIMIT ? OFFSET ?",
            (source_id, limit, offset),
        ) as cur:
            rows = await cur.fetchall()
    else:
        async with db.execute(
            "SELECT * FROM history ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ) as cur:
            rows = await cur.fetchall()

    return [
        HistoryOut(
            id=r["id"],
            source_id=r["source_id"],
            event_type=r["event_type"],
            detail=r["detail"],
            created_at=r["created_at"],
        )
        for r in rows
    ]
