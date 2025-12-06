# services.db_access.py

import sqlite3
import re
from typing import Dict, List
import threading
from contextlib import contextmanager
from pathlib import Path
import shutil
from datetime import datetime

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

########################################################################################
"""#########################   Ensure DB isn't stale     ############################"""
########################################################################################
def create_backup() -> Path:
    """
    Creates a backup of mira.db (and WAL/journal if present) in BASE.
    Only backs up if mira.db exists.
    Uses 'mira.db.bak' as primary name; if that exists, uses timestamped fallback.
    Returns path to the main backup file (e.g., mira.db.bak).
    """
    if not DB_PATH.exists():
        print("[DB] No database yet — skipping backup.")
        return DB_PATH  # no-op

    # Primary backup name
    bak_path = BASE / "mira.db.bak"

    # If .bak already exists, use timestamped name to avoid overwriting
    if bak_path.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        bak_path = BASE / f"mira.db.bak.{timestamp}"
        print(f"[DB] mira.db.bak exists — using {bak_path.name}")

    print(f"[DB] Backing up database to: {bak_path}")
    shutil.copy2(DB_PATH, bak_path)

    # Also copy WAL/SHM if present (critical for consistency in WAL mode)
    for suffix in [".db-wal", ".db-shm"]:
        src = DB_PATH.with_suffix(suffix)
        if src.exists():
            dst = bak_path.with_suffix(suffix.replace(".db", ""))
            shutil.copy2(src, dst)
            print(f"[DB] Copied: {dst.name}")

    return bak_path

def _strip_sql_comments(sql: str) -> str:
    """
    Remove SQL comments (-- to end of line) and normalize whitespace.
    Does NOT handle /* */ (you don’t use them).
    """
    # Remove -- comments (but preserve ' inside strings like 'now','localtime')
    no_comments = re.sub(r'--.*$', '', sql, flags=re.MULTILINE)
    # Collapse multi-whitespace + newlines into single spaces
    normalized = re.sub(r'\s+', ' ', no_comments).strip()
    return normalized


def _parse_create_table_statements(schema_sql: str) -> Dict[str, str]:
    """Extract CREATE TABLE statements (name → full CREATE SQL, with comments stripped)."""
    # Normalize first
    clean_sql = _strip_sql_comments(schema_sql)

    # Match: CREATE TABLE [IF NOT EXISTS] <name> ( <body> );
    # Use non-greedy match for body, and allow semicolon or EOF
    pattern = re.compile(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:`?(\w+)`?)\s*\((.*?)\)\s*;",
        re.IGNORECASE | re.DOTALL
    )
    tables = {}
    for match in pattern.finditer(clean_sql):
        name = match.group(1)
        body = match.group(2)
        # Reconstruct clean CREATE (without -- comments)
        full = f"CREATE TABLE {name} ({body});"
        tables[name] = full
    return tables

def _extract_column_names_from_create(create_sql: str) -> List[str]:
    """
    Extract column names from a CREATE TABLE (name TYPE ...) statement.
    Handles DEFAULT(...), CHECK(...), PRIMARY KEY(...), etc.
    Assumes comments already stripped.
    """
    # Extract body between first '(' and last ')'
    match = re.search(r'\((.*)\);?$', create_sql.strip(), re.DOTALL)
    if not match:
        return []
    body = match.group(1)

    # Split on commas, but only at top level (not inside (...))
    # Simple stack-based split
    columns = []
    paren_level = 0
    start = 0
    for i, ch in enumerate(body):
        if ch == '(':
            paren_level += 1
        elif ch == ')':
            paren_level -= 1
        elif ch == ',' and paren_level == 0:
            # End of a column definition
            col_def = body[start:i].strip()
            if col_def and not col_def.upper().startswith(('PRIMARY KEY', 'FOREIGN KEY', 'CHECK', 'UNIQUE')):
                # Extract first identifier (may be quoted)
                name_match = re.match(r'^["`]?([a-zA-Z_]\w*)["`]?', col_def)
                if name_match:
                    columns.append(name_match.group(1))
            start = i + 1

    # Last column
    col_def = body[start:].strip()
    if col_def and not col_def.upper().startswith(('PRIMARY KEY', 'FOREIGN KEY', 'CHECK', 'UNIQUE')):
        name_match = re.match(r'^["`]?([a-zA-Z_]\w*)["`]?', col_def)
        if name_match:
            columns.append(name_match.group(1))

    return columns

def _get_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    """Get current column names for a table."""
    try:
        cursor = conn.execute(f"PRAGMA table_info({table});")
        return [row[1] for row in cursor.fetchall()]
    except sqlite3.OperationalError:
        return []  # Table doesn't exist

def _get_create_sql_from_schema_for_table(schema_sql: str, table: str) -> str:
    tables = _parse_create_table_statements(schema_sql)
    return tables.get(table, "")

def _migrate_table(conn: sqlite3.Connection, table: str, schema_sql: str) -> None:
    desired_create = _get_create_sql_from_schema_for_table(schema_sql, table)
    if not desired_create:
        print(f"[DB] Warning: No CREATE statement found for '{table}' in schema.")
        return

    current_cols = _get_columns(conn, table)
    if not current_cols:
        print(f"[DB] Creating table '{table}' (missing).")
        conn.executescript(desired_create)
        return

    # Use robust column extractor
    desired_cols = _extract_column_names_from_create(desired_create)

    if not desired_cols:
        print(f"[DB] Could not extract columns for '{table}'. Skipping migration.")
        return

    # Compare
    missing_in_db = set(desired_cols) - set(current_cols)
    extra_in_db = set(current_cols) - set(desired_cols)

    if not missing_in_db and not extra_in_db:
        print(f"[DB] Table '{table}' schema OK.")
        return

    print(f"[DB] Schema mismatch for '{table}':")
    if missing_in_db:
        print(f"[DB] Missing columns: {sorted(missing_in_db)}")
    if extra_in_db:
        print(f"[DB] Extra columns: {sorted(extra_in_db)} (will be dropped)")

    # Safe migration...
    backup_dir = create_backup()
    print(f"[DB] Pre-migration backup completed: {backup_dir}")
    temp_table = f"{table}_migrate_temp"

    # 1. Create new table (use desired_create as-is — it's clean)
    new_table_def = desired_create.replace(
        f"CREATE TABLE {table} ",
        f"CREATE TABLE {temp_table} "
    )
    conn.executescript(new_table_def)

    # 2. Copy overlapping data
    overlap_cols = [col for col in current_cols if col in desired_cols]
    if overlap_cols:
        cols_str = ", ".join(overlap_cols)
        conn.execute(f"INSERT INTO {temp_table} ({cols_str}) SELECT {cols_str} FROM {table};")
    else:
        print(f"[DB] No overlapping columns: No data preserved for '{table}'.")

    # 3. Swap
    conn.execute(f"DROP TABLE {table};")
    conn.execute(f"ALTER TABLE {temp_table} RENAME TO {table};")
    print(f"[DB] Table '{table}' migrated successfully.")

def init_db() -> None:
    """
    Create the database if it does not already exist and ensure singleton row.
    Also verifies and migrates schema to match SCHEMA file.
    """
    print("[DB] Create if not exist.")
    with write_connection() as conn:
        with open(SCHEMA, "r", encoding="utf-8") as f:
            schema_sql = f.read()

        # Run initial schema (will create tables if missing)
        conn.executescript(schema_sql)

        # Ensure the singleton row exists
        row = conn.execute("SELECT id FROM settings WHERE id = 1").fetchone()
        if not row:
            print("[DB] Insert default settings.")
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

        print("[DB] Verifying health and syncing schema...")

        schema_tables = list(_parse_create_table_statements(schema_sql).keys())
        print(f"[DB] Checking tables: {schema_tables}")

        for table in schema_tables:
            _migrate_table(conn, table, schema_sql)

        print("[DB] Schema sync complete.")

if __name__ == "__main__":
    with open(SCHEMA) as f:
        sql = f.read()
    tables = _parse_create_table_statements(sql)
    for name, stmt in tables.items():
        cols = _extract_column_names_from_create(stmt)
        print(f"{name}: {cols}")