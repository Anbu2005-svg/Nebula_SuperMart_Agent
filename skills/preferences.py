from typing import Dict, Any, Optional
from db.models import get_db_connection, immediate_transaction
from skills.audit import _log_event

def set_preference(owner_id: str, key: str, value: str) -> Dict[str, Any]:
    """Set or update a persistent preference setting for the shop owner (Telegram user ID)."""
    clean_key = key.strip().lower()
    clean_val = value.strip()
    
    conn = get_db_connection()
    try:
        with immediate_transaction(conn):
            conn.execute("""
                INSERT INTO preferences (owner_id, key, value)
                VALUES (?, ?, ?)
                ON CONFLICT(owner_id, key) DO UPDATE SET value = excluded.value
            """, (str(owner_id), clean_key, clean_val))

            _log_event(conn, "PREFERENCE_SET", "owner", str(owner_id),
                       details={"key": clean_key, "value": clean_val})

        return {
            "status": "success",
            "message": f"Preference '{clean_key}' saved as '{clean_val}'.",
            "owner_id": str(owner_id),
            "key": clean_key,
            "value": clean_val
        }
    finally:
        conn.close()

def get_preference(owner_id: str, key: str) -> Dict[str, Any]:
    """Retrieve a persistent preference setting for the shop owner."""
    clean_key = key.strip().lower()
    conn = get_db_connection()
    try:
        cur = conn.execute("SELECT value FROM preferences WHERE owner_id = ? AND key = ?", (str(owner_id), clean_key))
        row = cur.fetchone()
        if not row:
            return {"status": "not_found", "message": f"Preference '{clean_key}' not set."}
        return {
            "status": "success",
            "owner_id": str(owner_id),
            "key": clean_key,
            "value": row["value"]
        }
    finally:
        conn.close()

def get_all_preferences(owner_id: str) -> Dict[str, str]:
    """Retrieve all persistent preferences for an owner as a dictionary."""
    conn = get_db_connection()
    try:
        cur = conn.execute("SELECT key, value FROM preferences WHERE owner_id = ?", (str(owner_id),))
        rows = cur.fetchall()
        return {r["key"]: r["value"] for r in rows}
    finally:
        conn.close()
