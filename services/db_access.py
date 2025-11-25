# services.db_access.py

import sqlite3
import threading
from contextlib import contextmanager
from services.globals import BASE_PATH

DB_PATH = BASE_PATH / "mira.db"
SCHEMA = BASE_PATH / "schema.sql"
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
    Create the database if it does not already exist.
    """
    with write_connection() as conn:
        with open(SCHEMA, "r", encoding="utf-8") as f:
            conn.executescript(f.read())