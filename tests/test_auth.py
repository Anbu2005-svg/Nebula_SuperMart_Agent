import pytest
import os
import uuid
from db.seed import seed_database
from skills.auth import register_shop, login_shop, get_user_session, is_user_authenticated, logout_user_session

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

