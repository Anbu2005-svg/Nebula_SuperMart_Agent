import pytest
import os
import uuid
from datetime import datetime, timedelta
from db.seed import seed_database
from skills.auth import (
    register_shop,
    login_shop,
    get_user_session,
    is_user_authenticated,
    logout_user_session,
    logout_all_sessions,
    get_latest_morning_cutoff_ist,
    IST
)

TEST_DB = "test_auth.db"

@pytest.fixture(autouse=True)
def setup_test_db():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    seed_database(TEST_DB)
    import db.models
    orig_path = db.models.DEFAULT_DB_PATH
    db.models.DEFAULT_DB_PATH = TEST_DB
    
    yield
    
    db.models.DEFAULT_DB_PATH = orig_path
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


def test_multi_shop_auth_lifecycle():
    # Use unique IDs per test run to avoid conflicts with shared cloud DB
    run_id = uuid.uuid4().hex[:8]
    user_id = f"test_telegram_owner_{run_id}"
    shop_name = f"SuperMart Test {run_id}"
    password = "SecretPassword123"

    # 1. Initially unauthenticated
    logout_user_session(user_id)
    assert is_user_authenticated(user_id) is False

    # 2. Register Shop
    reg_res = register_shop(shop_name=shop_name, password=password, shop_address="456 Main St", shop_gstin="33AABCU9603R1ZM")
    assert reg_res["status"] == "success"

    # 3. Login to Shop
    login_res = login_shop(telegram_id=user_id, shop_name=shop_name, password=password)
    assert login_res["status"] == "success"
    assert is_user_authenticated(user_id) is True

    # 4. Session Lookup
    session = get_user_session(user_id)
    assert session["shop_name"] == shop_name

    # 5. Logout
    logout_user_session(user_id)
    assert is_user_authenticated(user_id) is False

def test_logout_and_chat_clear_preserves_database_inventory():
    run_id = uuid.uuid4().hex[:8]
    user_id = f"test_user_persistent_{run_id}"
    shop_name = f"Persistent Store {run_id}"
    password = "Pass123Password"

    register_shop(shop_name=shop_name, password=password)
    login_shop(telegram_id=user_id, shop_name=shop_name, password=password)

    from skills.inventory import list_all_products
    # 1. Fetch products before logout/clear
    prods_before = list_all_products()
    assert prods_before["status"] == "success"
    initial_count = prods_before["count"]
    assert initial_count > 0

    # 2. Clear conversation memory (Simulating chat delete / reset)
    from agent.control_loop import clear_conversation
    clear_conversation(12345678)

    # 3. Logout user session
    logout_user_session(user_id)

    # 4. Verify Database Inventory Stock is 100% Intact & Unmodified
    prods_after = list_all_products()
    assert prods_after["status"] == "success"
    assert prods_after["count"] == initial_count


def test_24h_session_expiration():
    user_id = "test_user_expiry_777"
    shop_name = "Expiry Test Shop"
    password = "Password777"

    register_shop(shop_name=shop_name, password=password)
    login_shop(telegram_id=user_id, shop_name=shop_name, password=password)

    # 1. Freshly logged in -> active session
    assert is_user_authenticated(user_id) is True

    # 2. Simulate 25 hours elapsed by updating authenticated_at in database
    from db.models import get_db_connection, immediate_transaction
    conn = get_db_connection()
    try:
        with immediate_transaction(conn):
            cur = conn.cursor()
            cur.execute(
                "UPDATE user_sessions SET authenticated_at = (CURRENT_TIMESTAMP - INTERVAL '25 hours') WHERE telegram_id = %s",
                (str(user_id),)
            )
            cur.close()
    finally:
        conn.close()

    # 3. Next session lookup should automatically purge expired session and return None
    session = get_user_session(user_id)
    assert session is None
    assert is_user_authenticated(user_id) is False


def test_daily_morning_logout_cutoff_calculation():
    # 1. When time is after 04:30 AM IST (e.g. 10:00 AM IST), cutoff is today at 04:30 AM IST
    after_cutoff = datetime(2026, 9, 12, 10, 0, tzinfo=IST)
    cutoff = get_latest_morning_cutoff_ist(after_cutoff, reset_hour=4, reset_minute=30)
    assert cutoff == datetime(2026, 9, 12, 4, 30, tzinfo=IST)

    # 2. When time is before 04:30 AM IST (e.g. 02:15 AM IST), cutoff was yesterday at 04:30 AM IST
    before_cutoff = datetime(2026, 9, 12, 2, 15, tzinfo=IST)
    cutoff_prev = get_latest_morning_cutoff_ist(before_cutoff, reset_hour=4, reset_minute=30)
    assert cutoff_prev == datetime(2026, 9, 11, 4, 30, tzinfo=IST)


def test_logout_all_sessions_purges_all_users():
    run_id = uuid.uuid4().hex[:6]
    u1 = f"user_all_1_{run_id}"
    u2 = f"user_all_2_{run_id}"
    s1 = f"Shop All 1 {run_id}"
    s2 = f"Shop All 2 {run_id}"

    register_shop(s1, "Pass12345!")
    register_shop(s2, "Pass12345!")

    login_shop(u1, s1, "Pass12345!")
    login_shop(u2, s2, "Pass12345!")

    assert is_user_authenticated(u1) is True
    assert is_user_authenticated(u2) is True

    # Morning reset triggered
    deleted = logout_all_sessions()
    assert deleted >= 2

    # Both users are now logged out
    assert is_user_authenticated(u1) is False
    assert is_user_authenticated(u2) is False


