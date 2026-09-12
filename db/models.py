import os
import json
import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "")
DEFAULT_DB_PATH = os.getenv("DB_PATH", "supermarket.db")


def get_db_connection():
    """Returns a psycopg2 Connection using DATABASE_URL with RealDictCursor for dict-like row access."""
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL is not set in environment variables!")
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    conn.autocommit = False
    return conn


def init_db(schema_file: Optional[str] = None):
    """Initializes PostgreSQL database using postgres_schema.sql."""
    if schema_file is None:
        schema_file = os.path.join(os.path.dirname(__file__), "postgres_schema.sql")

    with open(schema_file, "r", encoding="utf-8") as f:
        sql_script = f.read()

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql_script)
        conn.commit()
        cur.close()
    finally:
        conn.close()


@contextmanager
def immediate_transaction(conn):
    """
    Context manager for atomic PostgreSQL transactions.
    Commits on success, rolls back on exception.
    """
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
