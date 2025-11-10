import sqlite3
from contextlib import contextmanager

DB_PATH = "bot_data.sqlite"

@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY,
              telegram_id INTEGER UNIQUE,
              username TEXT,
              full_name TEXT,
              consent INTEGER DEFAULT 0,
              source TEXT,
              stage TEXT,
              created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY,
              telegram_id INTEGER,
              event TEXT,
              meta TEXT,
              created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()

def upsert_user(telegram_id: int, username: str | None, full_name: str | None, source: str | None = None):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO users (telegram_id, username, full_name, source)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
              username=excluded.username,
              full_name=excluded.full_name,
              source=COALESCE(users.source, excluded.source)
            """ ,
            (telegram_id, username or "", full_name or "", source),
        )
        conn.commit()

def set_consent(telegram_id: int, consent: bool):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET consent=? WHERE telegram_id=?", (1 if consent else 0, telegram_id))
        conn.commit()

def set_stage(telegram_id: int, stage: str):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET stage=? WHERE telegram_id=?", (stage, telegram_id))
        conn.commit()

def log_event(telegram_id: int, event: str, meta: str | None = None):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO events (telegram_id, event, meta) VALUES (?, ?, ?)", (telegram_id, event, meta))
        conn.commit()
