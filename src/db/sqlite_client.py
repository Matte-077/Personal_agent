import json
import logging
import sqlite3
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

from src.config import settings

logger = logging.getLogger(__name__)

_sqlite_connection: Optional[sqlite3.Connection] = None


def get_sqlite_path() -> Path:
    """Returns absolute path to local SQLite database file, ensuring parent directory exists."""
    path = Path(settings.SQLITE_DB_PATH)
    if not path.is_absolute():
        path = Path.cwd() / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def init_sqlite_schema(conn: sqlite3.Connection) -> None:
    """
    Initializes SQLite schema mirroring Supabase tables:
    - 'items' table with UNIQUE(user_id, source_url) constraint
    - Virtual 'items_fts' FTS5 table for fast full-text search
    - Automatic synchronization triggers between 'items' and 'items_fts'
    """
    cursor = conn.cursor()

    # 1. Primary items table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS items (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL DEFAULT 'default',
        status TEXT NOT NULL DEFAULT 'active',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        source_url TEXT,
        source_type TEXT NOT NULL,
        raw_text TEXT,
        category TEXT NOT NULL,
        subcategory TEXT,
        title TEXT NOT NULL,
        summary TEXT NOT NULL,
        tags TEXT NOT NULL DEFAULT '[]',
        metadata TEXT NOT NULL DEFAULT '{}',
        confidence REAL NOT NULL DEFAULT 1.0,
        embedding TEXT,
        CONSTRAINT items_user_id_source_url_key UNIQUE (user_id, source_url)
    );
    """)

    # Relational indices
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sqlite_items_user_status ON items(user_id, status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sqlite_items_category ON items(category);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sqlite_items_created_at ON items(created_at);")

    # 2. Virtual Full-Text Search FTS5 table
    has_fts5 = False
    try:
        cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(
            id UNINDEXED,
            title,
            summary,
            raw_text,
            tags
        );
        """)
        has_fts5 = True
    except Exception as e:
        logger.warning(f"FTS5 not available in SQLite: {e}. Falling back to standard LIKE text search.")

    if has_fts5:
        # Triggers to synchronize FTS5 index automatically
        cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_items_ai AFTER INSERT ON items BEGIN
            INSERT INTO items_fts(id, title, summary, raw_text, tags)
            VALUES (new.id, new.title, new.summary, new.raw_text, new.tags);
        END;
        """)

        cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_items_ad AFTER DELETE ON items BEGIN
            DELETE FROM items_fts WHERE id = old.id;
        END;
        """)

        cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_items_au AFTER UPDATE ON items BEGIN
            DELETE FROM items_fts WHERE id = old.id;
            INSERT INTO items_fts(id, title, summary, raw_text, tags)
            VALUES (new.id, new.title, new.summary, new.raw_text, new.tags);
        END;
        """)

    conn.commit()
    logger.info(f"SQLite schema initialized successfully (FTS5: {has_fts5})")


def get_sqlite_connection() -> sqlite3.Connection:
    """
    Returns an SQLite connection configured with row_factory = sqlite3.Row,
    enabling foreign keys and WAL mode for high concurrent performance.
    """
    global _sqlite_connection
    if _sqlite_connection is not None:
        return _sqlite_connection

    db_path = get_sqlite_path()
    conn = sqlite3.connect(
        str(db_path),
        check_same_thread=False,
        timeout=30.0,
    )
    conn.row_factory = sqlite3.Row

    # Performance tuning: WAL mode and foreign keys
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
    except Exception as e:
        logger.warning(f"Could not set PRAGMA WAL on SQLite: {e}")

    init_sqlite_schema(conn)
    _sqlite_connection = conn
    return _sqlite_connection


def reset_sqlite_connection() -> None:
    """Closes and resets active SQLite connection (used in tests or shutdown)."""
    global _sqlite_connection
    if _sqlite_connection is not None:
        try:
            _sqlite_connection.close()
        except Exception:
            pass
        _sqlite_connection = None

