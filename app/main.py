"""
app/main.py
FastAPI application factory with lifespan startup/shutdown.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.db.database import init_db
from app.services import face_engine, loitering_engine, surveillance_orchestrator

settings = get_settings()
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────
    logger.info("Starting surveillance backend…")

    # Create storage directories
    for d in [
        settings.uploads_dir,
        settings.snapshots_dir,
        settings.clips_dir,
        settings.faces_dir,
    ]:
        d.mkdir(parents=True, exist_ok=True)

    # Init database
    await init_db()

    # Share event loop with orchestrator
    loop = asyncio.get_event_loop()
    surveillance_orchestrator.set_event_loop(loop)

    # Load known faces into memory
    async with aiosqlite.connect("surveillance.db") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, name, embedding FROM known_faces"
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]
    face_engine.load_known_faces_from_db(rows)

    # Load loitering threshold from settings
    async with aiosqlite.connect("surveillance.db") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT value FROM settings WHERE key='loitering_threshold'"
        ) as cur:
            row = await cur.fetchone()
    if row:
        loitering_engine.update_threshold(int(row["value"]))

    # Re-activate sources that were active before restart
    async with aiosqlite.connect("surveillance.db") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, uri FROM sources WHERE is_active=1"
        ) as cur:
            sources = [dict(r) for r in await cur.fetchall()]

    from app.services import camera_gateway
    seen_webcam_indices = set()
    for src in sources:
        try:
            # Skip duplicate webcam indices to avoid DSHOW conflicts
            uri = src["uri"].strip()
            if uri.isdigit():
                cam_idx = int(uri)
                if cam_idx in seen_webcam_indices:
                    logger.warning(
                        "Skipping source %d: webcam index %d already in use",
                        src["id"], cam_idx,
                    )
                    continue
                seen_webcam_indices.add(cam_idx)

            camera_gateway.connect_source(src["id"], src["uri"])
            surveillance_orchestrator.activate_source(src["id"])
            logger.info("Auto-resumed source %d: %s", src["id"], src["uri"])
        except Exception as exc:
            logger.error(
                "Failed to auto-resume source %d (%s): %s",
                src["id"], src["uri"], exc,
            )

    logger.info("Backend ready.")
    yield

    # ── Shutdown ─────────────────────────────────────────────────────────
    logger.info("Shutting down…")
    from app.services import camera_gateway as cg
    for sid in list(cg._streams.keys()):
        cg.disconnect_source(sid)


# ── App factory ───────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title="Smart Surveillance Backend",
        version="1.0.0",
        description="AI-powered home surveillance: cameras, ROI, YOLO detection, face recognition, alerts.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Static file serving for snapshots / clips
    Path(settings.STORAGE_BASE).mkdir(parents=True, exist_ok=True)
    app.mount("/storage", StaticFiles(directory=settings.STORAGE_BASE), name="storage")

    # Serve the scripts directory (dashboard, ROI editor, etc.)
    scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
    if scripts_dir.is_dir():
        app.mount("/scripts", StaticFiles(directory=str(scripts_dir), html=True), name="scripts")

    # Register routers
    from app.api.routes.auth import router as auth_router
    from app.api.routes.camera import router as camera_router
    from app.api.routes.roi import router as roi_router
    from app.api.routes.faces import router as faces_router
    from app.api.routes.alerts import router as alerts_router
    from app.api.routes.settings_route import router as settings_router
    from app.api.routes.websocket_route import router as ws_router

    app.include_router(auth_router)
    app.include_router(camera_router)
    app.include_router(roi_router)
    app.include_router(faces_router)
    app.include_router(alerts_router)
    app.include_router(settings_router)
    app.include_router(ws_router)

    @app.get("/health", tags=["meta"])
    async def health():
        return {"status": "ok", "version": "1.0.0"}

    @app.get("/dashboard", tags=["meta"])
    async def dashboard_redirect():
        return RedirectResponse(url="/scripts/dashboard.html")

    return app


app = create_app()
