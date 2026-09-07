import os
import hashlib
from typing import Optional, Dict, Any
from db.models import get_db_connection, immediate_transaction


def _hash_password(password: str) -> str:
    """Hash password using SHA-256 with salt."""
    salt = "supermarket_ops_salt_2026"
    return hashlib.sha256((password + salt).encode('utf-8')).hexdigest()


def register_shop(
    shop_name: str,
    password: str,
    shop_address: Optional[str] = None,
    shop_gstin: Optional[str] = None
) -> Dict[str, Any]:
    """Register a new supermarket shop in the system."""
    name = shop_name.strip()
    if not name or not password.strip():
        return {"status": "error", "message": "Shop name and password are mandatory fields!"}

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT shop_id FROM shops WHERE LOWER(shop_name) = %s", (name.lower(),))
        if cur.fetchone():
            cur.close()
            return {"status": "error", "message": f"Shop '{name}' already exists. Please choose Login instead."}

        pwd_hash = _hash_password(password.strip())
        with immediate_transaction(conn):
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO shops (shop_name, password_hash, shop_address, shop_gstin)
                VALUES (%s, %s, %s, %s)
                RETURNING shop_id
            """, (name, pwd_hash,
                  shop_address.strip() if shop_address else None,
                  shop_gstin.strip() if shop_gstin else None))
            shop_id = cur.fetchone()["shop_id"]
            cur.close()

        return {
            "status": "success",
            "message": f"Shop '{name}' registered successfully!",
            "shop_id": shop_id,
            "shop_name": name
        }
    finally:
        conn.close()


def login_shop(telegram_id: str, shop_name: str, password: str) -> Dict[str, Any]:
    """Authenticate Telegram user to an existing shop using credentials."""
    name = shop_name.strip()
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM shops WHERE LOWER(shop_name) = %s", (name.lower(),))
        shop = cur.fetchone()
        cur.close()
        if not shop:
            return {"status": "error", "message": f"Shop '{name}' not found. Please check spelling or sign up as a New Shop."}

        if shop["password_hash"] != _hash_password(password.strip()):
            return {"status": "error", "message": "Invalid password for this shop!"}

        with immediate_transaction(conn):
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO user_sessions (telegram_id, shop_id)
                VALUES (%s, %s)
                ON CONFLICT (telegram_id) DO UPDATE SET
                    shop_id = EXCLUDED.shop_id,
                    authenticated_at = CURRENT_TIMESTAMP
            """, (str(telegram_id), shop["shop_id"]))
            cur.close()

        return {
            "status": "success",
            "message": f"Successfully logged into '{shop['shop_name']}'!",
            "shop_id": shop["shop_id"],
            "shop_name": shop["shop_name"]
        }
    finally:
        conn.close()


def get_user_session(telegram_id: str) -> Optional[Dict[str, Any]]:
    """Fetch active shop session for a Telegram user."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT s.* FROM user_sessions us
            JOIN shops s ON us.shop_id = s.shop_id
            WHERE us.telegram_id = %s
        """, (str(telegram_id),))
        shop = cur.fetchone()
        cur.close()
        if shop:
            return {
                "shop_id": shop["shop_id"],
                "shop_name": shop["shop_name"],
                "shop_address": shop["shop_address"],
                "shop_gstin": shop["shop_gstin"]
            }
        return None
    finally:
        conn.close()


def is_user_authenticated(telegram_id: str) -> bool:
    """Check if a Telegram user has an active shop session."""
    return get_user_session(telegram_id) is not None


def logout_user_session(telegram_id: str) -> bool:
    """End active shop session for Telegram user."""
    conn = get_db_connection()
    try:
        with immediate_transaction(conn):
            cur = conn.cursor()
            cur.execute("DELETE FROM user_sessions WHERE telegram_id = %s", (str(telegram_id),))
            cur.close()
        return True
    finally:
        conn.close()
