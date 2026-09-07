import pytest
import os
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

from skills.auth import register_shop, login_shop, get_user_session, is_user_authenticated, logout_user_session

def test_multi_shop_auth_lifecycle():
    user_id = "test_telegram_owner_101"
    shop_name = "SuperMart Central"
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
