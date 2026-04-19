"""
app/models/schemas.py
All Pydantic request / response schemas.
"""
from typing import Optional, List, Any
from pydantic import BaseModel, Field
from datetime import datetime


# ─── Auth ────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ─── Sources ─────────────────────────────────────────────────────────────────

class SourceCreate(BaseModel):
    name: str
    source_type: str = Field(..., pattern="^(ip_camera|esp32|webcam|upload)$")
    uri: str


class SourceOut(BaseModel):
    id: int
    name: str
    source_type: str
    uri: str
    is_active: bool
    created_at: str


# ─── ROI ─────────────────────────────────────────────────────────────────────

class ROICreate(BaseModel):
    source_id: int
    name: str
    zone_type: str = Field(..., pattern="^(green|amber|red|critical)$")
    x: int
    y: int
    width: int
    height: int


class ROIUpdate(BaseModel):
    name: Optional[str] = None
    zone_type: Optional[str] = Field(None, pattern="^(green|amber|red|critical)$")
    x: Optional[int] = None
    y: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None


class ROIOut(BaseModel):
    id: int
    source_id: int
    name: str
    zone_type: str
    x: int
    y: int
    width: int
    height: int
    created_at: str


# ─── Faces ───────────────────────────────────────────────────────────────────

class FaceOut(BaseModel):
    id: int
    name: str
    image_path: str
    created_at: str


# ─── Alerts ──────────────────────────────────────────────────────────────────

class AlertOut(BaseModel):
    id: int
    source_id: Optional[int]
    alert_type: str
    suspicion_score: int
    snapshot_path: Optional[str]
    clip_path: Optional[str]
    meta: Optional[str]
    notified: bool
    created_at: str


# ─── History ─────────────────────────────────────────────────────────────────

class HistoryOut(BaseModel):
    id: int
    source_id: Optional[int]
    event_type: str
    detail: Optional[str]
    created_at: str


# ─── Settings ────────────────────────────────────────────────────────────────

class SettingUpdate(BaseModel):
    key: str
    value: str


class SettingOut(BaseModel):
    key: str
    value: str
    updated_at: str


# ─── WebSocket Event ─────────────────────────────────────────────────────────

class WSAlert(BaseModel):
    event: str = "alert"
    alert_id: int
    source_id: Optional[int]
    alert_type: str
    suspicion_score: int
    snapshot_path: Optional[str]
    message: str
    timestamp: str
