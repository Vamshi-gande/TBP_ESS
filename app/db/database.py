"""
app/db/database.py
SQLite connection pool via aiosqlite.  All tables are auto-created on startup.
"""
import aiosqlite
from pathlib import Path

DB_PATH = Path("./surveillance.db")


async def get_db() -> aiosqlite.Connection:
    """FastAPI dependency — yields a connection with row_factory set."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        yield db


async def init_db() -> None:
    """Called once at application startup to create all tables."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")

        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                username    TEXT UNIQUE NOT NULL,
                hashed_pw   TEXT NOT NULL,
                role        TEXT DEFAULT 'viewer',
                created_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS sources (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                source_type TEXT NOT NULL,   -- 'ip_camera' | 'esp32' | 'webcam' | 'upload'
                uri         TEXT NOT NULL,   -- URL or file path
                is_active   INTEGER DEFAULT 1,
                created_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS roi_zones (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id   INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                name        TEXT NOT NULL,
                zone_type   TEXT NOT NULL,   -- green | amber | red | critical
                x           INTEGER NOT NULL,
                y           INTEGER NOT NULL,
                width       INTEGER NOT NULL,
                height      INTEGER NOT NULL,
                created_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS known_faces (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                image_path  TEXT NOT NULL,
                embedding   BLOB,            -- serialized numpy array
                created_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS alerts (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id       INTEGER REFERENCES sources(id),
                alert_type      TEXT NOT NULL,   -- 'detection' | 'loitering' | 'unknown_face'
                suspicion_score INTEGER DEFAULT 0,
                snapshot_path   TEXT,
                clip_path       TEXT,
                meta            TEXT,            -- JSON blob
                notified        INTEGER DEFAULT 0,
                created_at      TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id   INTEGER REFERENCES sources(id),
                event_type  TEXT NOT NULL,
                detail      TEXT,
                created_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS settings (
                key         TEXT PRIMARY KEY,
                value       TEXT NOT NULL,
                updated_at  TEXT DEFAULT (datetime('now'))
            );

            INSERT OR IGNORE INTO settings (key, value) VALUES
                ('loitering_threshold', '30'),
                ('night_start_hour',    '20'),
                ('night_end_hour',      '6'),
                ('alert_score_app',     '2'),
                ('alert_score_whatsapp','3');
        """)
        await db.commit()

        # Seed default admin if none exists
        async with db.execute("SELECT id FROM users LIMIT 1") as cur:
            row = await cur.fetchone()

        if not row:
            from app.core.security import hash_password
            await db.execute(
                "INSERT INTO users (username, hashed_pw, role) VALUES (?,?,?)",
                ("admin", hash_password("admin123"), "admin"),
            )
            await db.commit()
