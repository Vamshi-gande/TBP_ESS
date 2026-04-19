"""
app/api/routes/roi.py
POST   /roi/save
GET    /roi/list/{source_id}
PUT    /roi/update/{id}
DELETE /roi/{id}
"""
import asyncpg
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.db.database import get_db
from app.models.schemas import ROICreate, ROIOut, ROIUpdate

router = APIRouter(prefix="/roi", tags=["roi"])


@router.post("/save", response_model=ROIOut)
async def save_roi(
    payload: ROICreate,
    conn: asyncpg.Connection = Depends(get_db),
    _user=Depends(get_current_user),
):
    # Verify source exists
    src = await conn.fetchrow("SELECT id FROM sources WHERE id=$1", payload.source_id)
    if not src:
        raise HTTPException(status_code=404, detail="Source not found")

    roi_id = await conn.fetchval(
        """INSERT INTO roi_zones (source_id, name, zone_type, x, y, width, height)
           VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id""",
        payload.source_id, payload.name, payload.zone_type,
        payload.x, payload.y, payload.width, payload.height,
    )

    row = await conn.fetchrow("SELECT * FROM roi_zones WHERE id=$1", roi_id)
    return ROIOut(**dict(row))


@router.get("/list/{source_id}", response_model=list[ROIOut])
async def list_roi(source_id: int, conn: asyncpg.Connection = Depends(get_db)):
    rows = await conn.fetch(
        "SELECT * FROM roi_zones WHERE source_id=$1 ORDER BY id", source_id
    )
    return [ROIOut(**dict(r)) for r in rows]


@router.put("/update/{roi_id}", response_model=ROIOut)
async def update_roi(
    roi_id: int,
    payload: ROIUpdate,
    conn: asyncpg.Connection = Depends(get_db),
    _user=Depends(get_current_user),
):
    existing = await conn.fetchrow("SELECT * FROM roi_zones WHERE id=$1", roi_id)
    if not existing:
        raise HTTPException(status_code=404, detail="ROI not found")

    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if updates:
        set_parts = []
        vals = []
        for i, (k, v) in enumerate(updates.items(), start=1):
            set_parts.append(f"{k}=${i}")
            vals.append(v)
        vals.append(roi_id)
        await conn.execute(
            f"UPDATE roi_zones SET {', '.join(set_parts)} WHERE id=${len(vals)}",
            *vals,
        )

    row = await conn.fetchrow("SELECT * FROM roi_zones WHERE id=$1", roi_id)
    return ROIOut(**dict(row))


@router.delete("/{roi_id}", status_code=204)
async def delete_roi(
    roi_id: int,
    conn: asyncpg.Connection = Depends(get_db),
    _user=Depends(get_current_user),
):
    await conn.execute("DELETE FROM roi_zones WHERE id=$1", roi_id)
