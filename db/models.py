import os
import sqlite3
from contextlib import contextmanager
from typing import Optional

DEFAULT_DB_PATH = "supermarket.db"

def get_db_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Returns a sqlite3 Connection with WAL mode enabled and Row factory configured."""
    if db_path is None:
        db_path = os.getenv("DB_PATH", DEFAULT_DB_PATH)
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

def init_db(db_path: str = DEFAULT_DB_PATH, schema_file: Optional[str] = None):
    """Initializes SQLite database using schema.sql."""
    if schema_file is None:
        schema_file = os.path.join(os.path.dirname(__file__), "schema.sql")
    
    with open(schema_file, "r", encoding="utf-8") as f:
        sql_script = f.read()
    
    conn = get_db_connection(db_path)
    try:
        conn.executescript(sql_script)
        conn.commit()
    finally:
        conn.close()

@contextmanager
def immediate_transaction(conn: sqlite3.Connection):
    """
    Context manager that executes 'BEGIN IMMEDIATE' to acquire a write lock upfront,
    preventing concurrent race conditions on SQLite database writes.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
