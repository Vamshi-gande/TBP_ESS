"""
app/core/config.py
Central configuration loaded from environment / .env file.
"""
from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    APP_SECRET_KEY: str = "change-me"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    DEBUG: bool = False

    # Twilio
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_WHATSAPP: str = "whatsapp:+14155238886"
    TWILIO_FROM_SMS: str = ""
    ALERT_PHONE_WHATSAPP: str = ""
    ALERT_PHONE_SMS: str = ""

    # AI
    YOLO_MODEL: str = "yolov8n.pt"
    DETECTION_CONFIDENCE: float = 0.5
    LOITERING_THRESHOLD_SECONDS: int = 30

    # Storage
    STORAGE_BASE: str = "./storage"

    # Auth
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    @property
    def uploads_dir(self) -> Path:
        return Path(self.STORAGE_BASE) / "uploads"

    @property
    def snapshots_dir(self) -> Path:
        return Path(self.STORAGE_BASE) / "snapshots"

    @property
    def clips_dir(self) -> Path:
        return Path(self.STORAGE_BASE) / "clips"

    @property
    def faces_dir(self) -> Path:
        return Path(self.STORAGE_BASE) / "faces"


@lru_cache
def get_settings() -> Settings:
    return Settings()
