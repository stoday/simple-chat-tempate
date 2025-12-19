import os
import sqlite3
from pathlib import Path
from typing import Generator

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB = BASE_DIR / "simplechat.db"
DB_PATH = Path(os.environ.get("SIMPLECHAT_DB_PATH", DEFAULT_DB))

USER_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS user (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    display_name TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_login_at TEXT
);
"""

CONVERSATION_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS conversation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL DEFAULT 'New Chat',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(user_id) REFERENCES user(id) ON DELETE CASCADE
);
"""

MESSAGE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS message (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    sender_type TEXT NOT NULL CHECK(sender_type IN ('user','assistant')),
    content TEXT NOT NULL,
    conversation_id INTEGER,
    status TEXT NOT NULL DEFAULT 'completed',
    parent_message_id INTEGER,
    stopped_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(user_id) REFERENCES user(id) ON DELETE CASCADE
);
"""

MESSAGE_FILE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS message_file (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL,
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    mime_type TEXT,
    size_bytes INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(message_id) REFERENCES message(id) ON DELETE CASCADE
);
"""


def init_db() -> None:
    """Create the SQLite database file and ensure required tables exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute(USER_TABLE_SQL)
        conn.execute(CONVERSATION_TABLE_SQL)
        conn.execute(MESSAGE_TABLE_SQL)
        conn.execute(MESSAGE_FILE_TABLE_SQL)
        ensure_message_columns(conn)
        conn.commit()


def ensure_message_columns(conn: sqlite3.Connection) -> None:
    info = conn.execute("PRAGMA table_info(message)").fetchall()
    columns = {row[1] for row in info}
    if "conversation_id" not in columns:
        conn.execute("ALTER TABLE message ADD COLUMN conversation_id INTEGER")
    if "status" not in columns:
        conn.execute("ALTER TABLE message ADD COLUMN status TEXT NOT NULL DEFAULT 'completed'")
    if "parent_message_id" not in columns:
        conn.execute("ALTER TABLE message ADD COLUMN parent_message_id INTEGER")
    if "stopped_at" not in columns:
        conn.execute("ALTER TABLE message ADD COLUMN stopped_at TEXT")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def get_db() -> Generator[sqlite3.Connection, None, None]:
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()
