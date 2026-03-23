"""Shared database utilities for dispatch-app reply scripts.

Provides common functions for dispatch-messages.db access, image handling,
and schema migrations. Used by reply-app and reply-dispatch-api.

This is the SINGLE SOURCE OF TRUTH for dispatch-messages.db schema.
All writers (reply-app, reply-dispatch-api, server.py) should import from here.
"""

import shutil
import sqlite3
from pathlib import Path

# Shared schema constants — imported by server.py to eliminate drift
CHAT_NOTES_SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_notes (
    chat_id TEXT PRIMARY KEY REFERENCES chats(id) ON DELETE CASCADE,
    content TEXT NOT NULL DEFAULT '',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
"""

_STATE_DIR = Path.home() / "dispatch" / "state"
DB_PATH = _STATE_DIR / "dispatch-messages.db"
IMAGE_DIR = _STATE_DIR / "dispatch-images"

# Backward compatibility: migrate old sven-* file names
_OLD_DB = _STATE_DIR / "sven-messages.db"
_OLD_IMG = _STATE_DIR / "sven-images"
if _OLD_DB.exists() and not DB_PATH.exists():
    try:
        _OLD_DB.rename(DB_PATH)
    except OSError:
        pass
if _OLD_IMG.exists() and not IMAGE_DIR.exists():
    try:
        _OLD_IMG.rename(IMAGE_DIR)
    except OSError:
        pass


def _get_conn() -> sqlite3.Connection:
    """Get a WAL-mode connection to dispatch-messages.db.

    WAL mode enables concurrent readers + writers without blocking,
    critical since multiple processes write to this DB (server.py,
    reply-app, reply-dispatch-api).
    """
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")  # Wait up to 5s on lock contention
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Initialize the SQLite database with current schema and migrations."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            audio_path TEXT,
            chat_id TEXT NOT NULL DEFAULT 'voice',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Migrations: add columns if table already exists without them
    columns = [row[1] for row in conn.execute("PRAGMA table_info(messages)").fetchall()]
    if "chat_id" not in columns:
        conn.execute("ALTER TABLE messages ADD COLUMN chat_id TEXT NOT NULL DEFAULT 'voice'")
    if "image_path" not in columns:
        conn.execute("ALTER TABLE messages ADD COLUMN image_path TEXT")
    if "status" not in columns:
        conn.execute("ALTER TABLE messages ADD COLUMN status TEXT DEFAULT 'complete'")
    if "failure_reason" not in columns:
        conn.execute("ALTER TABLE messages ADD COLUMN failure_reason TEXT")

    # Ensure indexes exist
    conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages(chat_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_chat_created ON messages(chat_id, created_at)")

    # Ensure chats table exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL DEFAULT 'New Chat',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Note: no default "voice" chat is auto-created. Chats are created on demand.
    # Migration: add last_opened_at column if missing
    chat_columns = [row[1] for row in conn.execute("PRAGMA table_info(chats)").fetchall()]
    if "last_opened_at" not in chat_columns:
        try:
            conn.execute("ALTER TABLE chats ADD COLUMN last_opened_at DATETIME")
        except Exception:
            pass  # Column already exists (race condition)
    # Chat notes table (1:1 with chats)
    conn.execute(CHAT_NOTES_SCHEMA)

    # Migration: add fork columns if missing
    if "forked_from" not in chat_columns:
        try:
            conn.execute("ALTER TABLE chats ADD COLUMN forked_from TEXT REFERENCES chats(id) ON DELETE SET NULL")
        except Exception:
            pass
    if "fork_message_id" not in chat_columns:
        try:
            conn.execute("ALTER TABLE chats ADD COLUMN fork_message_id TEXT")
        except Exception:
            pass

    conn.commit()
    conn.close()


def store_message(
    message_id: str,
    role: str,
    content: str,
    chat_id: str = "voice",
    audio_path: str | None = None,
    image_path: str | None = None,
):
    """Store a message in the dispatch-messages.db database."""
    conn = _get_conn()
    conn.execute(
        "INSERT INTO messages (id, role, content, audio_path, chat_id, image_path) VALUES (?, ?, ?, ?, ?, ?)",
        (message_id, role, content, audio_path, chat_id, image_path),
    )
    conn.execute(
        "UPDATE chats SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (chat_id,),
    )
    conn.commit()
    conn.close()


def store_user_message(
    message_id: str,
    content: str,
    chat_id: str = "voice",
    image_path: str | None = None,
):
    """Store a user message. Convenience wrapper for store_message(role='user')."""
    store_message(message_id, "user", content, chat_id, image_path=image_path)


def copy_image_to_canonical(source_path: str, message_id: str, chat_id: str) -> str | None:
    """Copy an image file to the canonical dispatch-images directory.

    Images are organized by chat_id: ~/dispatch/state/dispatch-images/{chat_id}/{message_id}{ext}
    Returns the canonical path on success, None on failure.
    """
    src = Path(source_path)
    if not src.exists():
        return None

    dest_dir = IMAGE_DIR / chat_id
    dest_dir.mkdir(parents=True, exist_ok=True)

    ext = src.suffix.lower() or ".jpg"
    dest = dest_dir / f"{message_id}{ext}"

    try:
        shutil.copy2(src, dest)
        return str(dest)
    except Exception:
        return None


def get_chat_title(chat_id: str) -> str | None:
    """Look up a chat's title from the chats table."""
    conn = _get_conn()
    row = conn.execute("SELECT title FROM chats WHERE id = ?", (chat_id,)).fetchone()
    conn.close()
    return row[0] if row else None
