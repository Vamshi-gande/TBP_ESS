"""
app/api/routes/roi.py
POST   /roi/save
GET    /roi/list/{source_id}
PUT    /roi/update/{id}
DELETE /roi/{id}
"""
from fastapi import APIRouter, Depends, HTTPException
import aiosqlite

from app.api.deps import get_current_user
from app.db.database import get_db
from app.models.schemas import ROICreate, ROIOut, ROIUpdate

router = APIRouter(prefix="/roi", tags=["roi"])


@router.post("/save", response_model=ROIOut)
async def save_roi(
    payload: ROICreate,
    db: aiosqlite.Connection = Depends(get_db),
    _user=Depends(get_current_user),
):
    # Verify source exists
    async with db.execute("SELECT id FROM sources WHERE id=?", (payload.source_id,)) as cur:
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Source not found")

    async with db.execute(
        """INSERT INTO roi_zones (source_id, name, zone_type, x, y, width, height)
           VALUES (?,?,?,?,?,?,?)""",
        (payload.source_id, payload.name, payload.zone_type,
         payload.x, payload.y, payload.width, payload.height),
    ) as cur:
        roi_id = cur.lastrowid
    await db.commit()

    async with db.execute("SELECT * FROM roi_zones WHERE id=?", (roi_id,)) as cur:
        row = dict(await cur.fetchone())
    return ROIOut(**row)


@router.get("/list/{source_id}", response_model=list[ROIOut])
async def list_roi(source_id: int, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute(
        "SELECT * FROM roi_zones WHERE source_id=? ORDER BY id", (source_id,)
    ) as cur:
        rows = await cur.fetchall()
    return [ROIOut(**dict(r)) for r in rows]


@router.put("/update/{roi_id}", response_model=ROIOut)
async def update_roi(
    roi_id: int,
    payload: ROIUpdate,
    db: aiosqlite.Connection = Depends(get_db),
    _user=Depends(get_current_user),
):
    async with db.execute("SELECT * FROM roi_zones WHERE id=?", (roi_id,)) as cur:
        existing = await cur.fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="ROI not found")

    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if updates:
        set_clause = ", ".join(f"{k}=?" for k in updates)
        await db.execute(
            f"UPDATE roi_zones SET {set_clause} WHERE id=?",
            [*updates.values(), roi_id],
        )
        await db.commit()

    async with db.execute("SELECT * FROM roi_zones WHERE id=?", (roi_id,)) as cur:
        row = dict(await cur.fetchone())
    return ROIOut(**row)


@router.delete("/{roi_id}", status_code=204)
async def delete_roi(
    roi_id: int,
    db: aiosqlite.Connection = Depends(get_db),
    _user=Depends(get_current_user),
):
    await db.execute("DELETE FROM roi_zones WHERE id=?", (roi_id,))
    await db.commit()
