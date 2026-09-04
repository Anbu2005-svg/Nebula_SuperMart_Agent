import pytest
import os
from db.seed import seed_database
from skills.auth import is_user_authenticated, authenticate_user, deauthenticate_user

TEST_DB = "test_auth.db"

@pytest.fixture(autouse=True)
def setup_test_db():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    seed_database(TEST_DB)
    import db.models
    orig_path = db.models.DEFAULT_DB_PATH
    db.models.DEFAULT_DB_PATH = TEST_DB
    
    import skills.auth
    orig_require = skills.auth.REQUIRE_AUTH
    skills.auth.REQUIRE_AUTH = True
    
    yield
    
    skills.auth.REQUIRE_AUTH = orig_require
    db.models.DEFAULT_DB_PATH = orig_path
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

def test_simple_user_auth_lifecycle():
    user_id = "test_evaluator_999"
    
    # 1. Initially unauthenticated
    deauthenticate_user(user_id)
    assert is_user_authenticated(user_id) is False

    # 2. Authenticate user via contact share
    authenticate_user(user_id, phone_number="+919876543210")
    assert is_user_authenticated(user_id) is True

    # 3. Deauthenticate user (logout)
    deauthenticate_user(user_id)
    assert is_user_authenticated(user_id) is False
