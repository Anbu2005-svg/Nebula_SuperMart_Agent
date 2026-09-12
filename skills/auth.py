import os
import time
import hmac
import hashlib
from typing import Optional, Dict, Any, Tuple
from db.models import get_db_connection, immediate_transaction

# In-memory tracking for failed login attempts to prevent brute-force attacks
# {identifier: {"count": int, "locked_until": float}}
_FAILED_LOGIN_ATTEMPTS: Dict[str, Dict[str, Any]] = {}
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION_SECONDS = 300  # 5 minutes


def _hash_password(password: str) -> str:
    """Hash password using PBKDF2-HMAC-SHA256 with 100,000 iterations and a cryptographically secure random salt."""
    salt = os.urandom(16).hex()
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000).hex()
    return f"pbkdf2${salt}${derived}"


def _verify_password(password: str, stored_hash: str) -> Tuple[bool, bool]:
    """
    Verify password against stored hash using constant-time comparison.
    Returns (is_valid, needs_upgrade).
    Supports backward compatibility with legacy SHA-256 hashes and indicates when upgrade is needed.
    """
    if not stored_hash or not password:
        return False, False

    if stored_hash.startswith("pbkdf2$"):
        try:
            parts = stored_hash.split("$")
            if len(parts) != 3:
                return False, False
            salt = parts[1]
            expected_derived = parts[2]
            computed_derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000).hex()
            is_valid = hmac.compare_digest(computed_derived, expected_derived)
            return is_valid, False
        except Exception:
            return False, False
    else:
        # Legacy SHA-256 with static salt
        legacy_salt = "supermarket_ops_salt_2026"
        legacy_hash = hashlib.sha256((password + legacy_salt).encode("utf-8")).hexdigest()
        is_valid = hmac.compare_digest(stored_hash, legacy_hash)
        return is_valid, True


def _check_rate_limit(identifier: str) -> Optional[str]:
    """Check if identifier is currently locked out from login attempts."""
    now = time.time()
    record = _FAILED_LOGIN_ATTEMPTS.get(identifier)
    if record and record.get("locked_until", 0) > now:
        remaining = int(record["locked_until"] - now)
        return f"Too many failed login attempts. Account temporarily locked for {remaining} seconds. Please try again later."
    return None


def _record_failed_attempt(identifier: str) -> None:
    """Record a failed login attempt and apply lockout if threshold exceeded."""
    now = time.time()
    record = _FAILED_LOGIN_ATTEMPTS.get(identifier, {"count": 0, "locked_until": 0})
    if record.get("locked_until", 0) <= now:
        record["count"] = record.get("count", 0) + 1
        if record["count"] >= MAX_LOGIN_ATTEMPTS:
            record["locked_until"] = now + LOCKOUT_DURATION_SECONDS
    _FAILED_LOGIN_ATTEMPTS[identifier] = record


def _reset_failed_attempts(identifier: str) -> None:
    """Clear failed login attempts on successful authentication."""
    _FAILED_LOGIN_ATTEMPTS.pop(identifier, None)


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
    """Authenticate Telegram user to an existing shop using credentials with rate-limit brute-force protection."""
    name = shop_name.strip()
    lockout_msg = _check_rate_limit(f"{telegram_id}:{name.lower()}")
    if lockout_msg:
        return {"status": "error", "message": lockout_msg}

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM shops WHERE LOWER(shop_name) = %s", (name.lower(),))
        shop = cur.fetchone()
        cur.close()
        if not shop:
            _record_failed_attempt(f"{telegram_id}:{name.lower()}")
            return {"status": "error", "message": f"Shop '{name}' not found. Please check spelling or sign up as a New Shop."}

        is_valid, needs_upgrade = _verify_password(password.strip(), shop["password_hash"])
        if not is_valid:
            _record_failed_attempt(f"{telegram_id}:{name.lower()}")
            return {"status": "error", "message": "Invalid password for this shop!"}

        # Clear failed attempt counter on success
        _reset_failed_attempts(f"{telegram_id}:{name.lower()}")

        # Auto-upgrade legacy SHA-256 hash to modern PBKDF2-HMAC-SHA256
        if needs_upgrade:
            new_hash = _hash_password(password.strip())
            with immediate_transaction(conn):
                cur_up = conn.cursor()
                cur_up.execute("UPDATE shops SET password_hash = %s WHERE shop_id = %s", (new_hash, shop["shop_id"]))
                cur_up.close()

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


SESSION_EXPIRY_HOURS = 24


def cleanup_expired_sessions() -> int:
    """Purge all user sessions older than 24 hours from PostgreSQL."""
    conn = get_db_connection()
    try:
        with immediate_transaction(conn):
            cur = conn.cursor()
            cur.execute("DELETE FROM user_sessions WHERE authenticated_at < (CURRENT_TIMESTAMP - INTERVAL '24 hours')")
            deleted_count = cur.rowcount
            cur.close()
        return deleted_count
    except Exception:
        return 0
    finally:
        conn.close()


def get_user_session(telegram_id: str) -> Optional[Dict[str, Any]]:
    """Fetch active shop session for a Telegram user. Purges and returns None if expired (> 24 hours)."""
    cleanup_expired_sessions()
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT s.*, us.authenticated_at FROM user_sessions us
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
                "shop_gstin": shop["shop_gstin"],
                "authenticated_at": shop["authenticated_at"]
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
