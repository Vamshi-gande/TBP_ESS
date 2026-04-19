"""
app/db/database.py
PostgreSQL connection pool via asyncpg.  All tables are auto-created on startup.
"""
import asyncpg
import logging
from typing import Optional

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


async def init_pool() -> asyncpg.Pool:
    """Create the asyncpg connection pool.  Called once at app startup."""
    global _pool
    settings = get_settings()
    _pool = await asyncpg.create_pool(
        dsn=settings.DATABASE_URL,
        min_size=2,
        max_size=10,
    )
    logger.info("PostgreSQL pool created (%s)", settings.DATABASE_URL.split("@")[-1])
    return _pool


async def close_pool() -> None:
    """Shut down the pool.  Called on app shutdown."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("PostgreSQL pool closed")


def get_pool() -> asyncpg.Pool:
    """Return the live pool (for use in route dependencies)."""
    if _pool is None:
        raise RuntimeError("Database pool not initialised — call init_pool() first")
    return _pool


async def get_db():
    """FastAPI dependency — yields a connection from the pool."""
    async with _pool.acquire() as conn:
        yield conn


async def init_db() -> None:
    """Called once at application startup to create all tables."""
    async with _pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id          SERIAL PRIMARY KEY,
                username    TEXT UNIQUE NOT NULL,
                hashed_pw   TEXT NOT NULL,
                role        TEXT DEFAULT 'viewer',
                created_at  TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS sources (
                id          SERIAL PRIMARY KEY,
                name        TEXT NOT NULL,
                source_type TEXT NOT NULL,
                uri         TEXT NOT NULL,
                is_active   BOOLEAN DEFAULT TRUE,
                created_at  TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS roi_zones (
                id          SERIAL PRIMARY KEY,
                source_id   INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                name        TEXT NOT NULL,
                zone_type   TEXT NOT NULL,
                x           INTEGER NOT NULL,
                y           INTEGER NOT NULL,
                width       INTEGER NOT NULL,
                height      INTEGER NOT NULL,
                created_at  TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS known_faces (
                id          SERIAL PRIMARY KEY,
                name        TEXT NOT NULL,
                image_path  TEXT NOT NULL,
                embedding   BYTEA,
                created_at  TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS alerts (
                id              SERIAL PRIMARY KEY,
                source_id       INTEGER REFERENCES sources(id),
                alert_type      TEXT NOT NULL,
                suspicion_score INTEGER DEFAULT 0,
                snapshot_path   TEXT,
                clip_path       TEXT,
                meta            TEXT,
                notified        BOOLEAN DEFAULT FALSE,
                created_at      TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS history (
                id          SERIAL PRIMARY KEY,
                source_id   INTEGER REFERENCES sources(id),
                event_type  TEXT NOT NULL,
                detail      TEXT,
                created_at  TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS settings (
                key         TEXT PRIMARY KEY,
                value       TEXT NOT NULL,
                updated_at  TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS face_sightings (
                id              SERIAL PRIMARY KEY,
                embedding_hash  TEXT NOT NULL,
                source_id       INTEGER REFERENCES sources(id),
                snapshot_path   TEXT,
                sighting_count  INTEGER DEFAULT 1,
                first_seen      TIMESTAMPTZ DEFAULT NOW(),
                last_seen       TIMESTAMPTZ DEFAULT NOW(),
                escalated       BOOLEAN DEFAULT FALSE
            );
        """)

        # Create index for fast sighting lookups
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_face_sightings_hash
                ON face_sightings(embedding_hash);
        """)

        # Seed default settings
        await conn.execute("""
            INSERT INTO settings (key, value) VALUES
                ('loitering_threshold', '30'),
                ('night_start_hour',    '20'),
                ('night_end_hour',      '6'),
                ('alert_score_app',     '2'),
                ('alert_score_whatsapp','3')
            ON CONFLICT (key) DO NOTHING;
        """)

        # Seed default admin if none exists
        row = await conn.fetchrow("SELECT id FROM users LIMIT 1")
        if not row:
            from app.core.security import hash_password
            await conn.execute(
                "INSERT INTO users (username, hashed_pw, role) VALUES ($1, $2, $3)",
                "admin", hash_password("admin123"), "admin",
            )

    logger.info("Database schema initialised")
