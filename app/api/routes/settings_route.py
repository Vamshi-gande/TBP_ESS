"""
app/api/routes/settings_route.py
POST /settings/update
GET  /settings
"""
import asyncpg
from fastapi import APIRouter, Depends, HTTPException

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
    conn: asyncpg.Connection = Depends(get_db),
    _user=Depends(get_current_user),
):
    rows = await conn.fetch("SELECT * FROM settings ORDER BY key")
    return [SettingOut(key=r["key"], value=r["value"], updated_at=str(r["updated_at"])) for r in rows]


@router.post("/update", response_model=SettingOut)
async def update_setting(
    payload: SettingUpdate,
    conn: asyncpg.Connection = Depends(get_db),
    _user=Depends(get_current_user),
):
    if payload.key not in _ALLOWED_KEYS:
        raise HTTPException(status_code=400, detail=f"Unknown setting key: {payload.key}")

    await conn.execute(
        """INSERT INTO settings (key, value, updated_at)
           VALUES ($1, $2, NOW())
           ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value, updated_at=EXCLUDED.updated_at""",
        payload.key, payload.value,
    )

    # Apply live
    if payload.key == "loitering_threshold":
        loitering_engine.update_threshold(int(payload.value))

    row = await conn.fetchrow("SELECT * FROM settings WHERE key=$1", payload.key)
    return SettingOut(key=row["key"], value=row["value"], updated_at=str(row["updated_at"]))
