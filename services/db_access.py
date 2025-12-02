# services.db_access.py

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

DB_PATH = BASE / "mira.db"
SCHEMA = BASE / "schema.sql"
_write_lock = threading.Lock()

def connect(readonly=False):
    uri = f"file:{DB_PATH}?mode=rw"
    if not readonly:
        uri = f"file:{DB_PATH}?mode=rwc"
    conn = sqlite3.connect(uri, uri=True, timeout=30, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

@contextmanager
def write_connection(timeout=15):
    """
    SQLite3 allows for a single write connection
    """
    acquired = _write_lock.acquire(timeout=timeout)
    if not acquired:
        raise TimeoutError("Could not acquire DB write lock within timeout")
    try:
        conn = connect(readonly=False)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
    finally:
        _write_lock.release()

def init_db() -> None:
    """
    Create the database if it does not already exist and ensure singleton row.
    """
    print("[DB] Create if not exist.")
    with write_connection() as conn:
        with open(SCHEMA, "r", encoding="utf-8") as f:
            conn.executescript(f.read())

        # Ensure the singleton row exists
        row = conn.execute("SELECT id FROM settings WHERE id = 1").fetchone()
        if not row:
            conn.execute("""
                INSERT INTO settings (
                    id, stt, stt_mode, llm, llm_mode, llm_vl, llm_vl_mode,
                    tts, tts_mode,
                    smart_plug1_name, smart_plug1_ip,
                    smart_plug2_name, smart_plug2_ip,
                    smart_plug3_name, smart_plug3_ip,
                    smart_plug4_name, smart_plug4_ip,
                    user_name, user_birthday,
                    location_city, location_latitude, location_longitude,
                    schedule_monday, schedule_tuesday, schedule_wednesday,
                    schedule_thursday, schedule_friday, schedule_saturday,
                    schedule_sunday, additional_info
                )
                VALUES (
                    1, 'vosk', 'cpu', 'qwen3', 'gpu', 'qwen3_vl', 'cpu',
                    'xtts_v2', 'gpu',
                    '', '', '', '', '', '', '', '',
                    'User', 'Birthday',
                    '', '', '',
                    '', '', '', '', '', '', '',
                    ''
                )
            """)