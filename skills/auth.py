import os
from typing import Optional
from db.models import get_db_connection, immediate_transaction

REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "false").lower() in ("true", "1", "yes")

def is_user_authenticated(telegram_id: str) -> bool:
    """Check if a Telegram user ID is authenticated in the database."""
    if not REQUIRE_AUTH:
        return True
        
    conn = get_db_connection()
    try:
        cur = conn.execute("SELECT 1 FROM authenticated_users WHERE telegram_id = ?", (str(telegram_id),))
        return cur.fetchone() is not None
    finally:
        conn.close()

def authenticate_user(telegram_id: str, phone_number: Optional[str] = None) -> bool:
    """Record user mobile authentication in database."""
    conn = get_db_connection()
    try:
        with immediate_transaction(conn):
            conn.execute("""
                INSERT INTO authenticated_users (telegram_id, phone_number)
                VALUES (?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET 
                    phone_number = COALESCE(excluded.phone_number, authenticated_users.phone_number),
                    authenticated_at = CURRENT_TIMESTAMP
            """, (str(telegram_id), phone_number))
        return True
    finally:
        conn.close()

def deauthenticate_user(telegram_id: str) -> bool:
    """Revoke user authentication (used by /logout command)."""
    conn = get_db_connection()
    try:
        with immediate_transaction(conn):
            conn.execute("DELETE FROM authenticated_users WHERE telegram_id = ?", (str(telegram_id),))
        return True
    finally:
        conn.close()
