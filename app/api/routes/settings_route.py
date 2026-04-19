"""
app/api/routes/settings_route.py
POST /settings/update
GET  /settings
"""
import aiosqlite
from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.db.database import get_db
from app.models.schemas import SettingOut, SettingUpdate
from app.services import loitering_engine

router = APIRouter(prefix="/settings", tags=["settings"])

_ALLOWED_KEYS = {
    "loitering_threshold",
    "night_start_hour",
    "night_end_hour",
    "alert_score_app",
    "alert_score_whatsapp",
}


@router.get("", response_model=list[SettingOut])
async def get_settings_all(
    db: aiosqlite.Connection = Depends(get_db),
    _user=Depends(get_current_user),
):
    async with db.execute("SELECT * FROM settings ORDER BY key") as cur:
        rows = await cur.fetchall()
    return [SettingOut(key=r["key"], value=r["value"], updated_at=r["updated_at"]) for r in rows]


@router.post("/update", response_model=SettingOut)
async def update_setting(
    payload: SettingUpdate,
    db: aiosqlite.Connection = Depends(get_db),
    _user=Depends(get_current_user),
):
    from fastapi import HTTPException
    if payload.key not in _ALLOWED_KEYS:
        raise HTTPException(status_code=400, detail=f"Unknown setting key: {payload.key}")

    await db.execute(
        """INSERT INTO settings (key, value, updated_at)
           VALUES (?, ?, datetime('now'))
           ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
        (payload.key, payload.value),
    )
    await db.commit()

    # Apply live
    if payload.key == "loitering_threshold":
        loitering_engine.update_threshold(int(payload.value))

    async with db.execute("SELECT * FROM settings WHERE key=?", (payload.key,)) as cur:
        row = dict(await cur.fetchone())
    return SettingOut(**row)
