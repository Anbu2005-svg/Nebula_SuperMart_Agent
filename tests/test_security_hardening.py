import os
import math
import uuid
import pytest
from skills.auth import (
    _hash_password,
    _verify_password,
    _check_rate_limit,
    _record_failed_attempt,
    _reset_failed_attempts,
    register_shop,
    login_shop,
    logout_user_session
)
from skills.billing import add_item_to_bill, edit_item_qty, start_bill
from skills.credit import charge_khata, record_payment
from skills.inventory import add_product, receive_stock, update_gst_slab
from skills.analytics import daily_summary
from bot import is_safe_generated_file


def test_pbkdf2_hashing_and_verification():
    pwd = "SecureSupermarketPassword2026!"
    h = _hash_password(pwd)
    assert h.startswith("pbkdf2$")
    assert len(h.split("$")) == 3

    # Verification passes for correct password
    valid, needs_upgrade = _verify_password(pwd, h)
    assert valid is True
    assert needs_upgrade is False

    # Verification fails for incorrect password
    valid_wrong, _ = _verify_password("WrongPassword", h)
    assert valid_wrong is False


def test_legacy_hash_backward_compatibility_and_upgrade():
    import hashlib
    pwd = "LegacyShopPassword"
    legacy_salt = "supermarket_ops_salt_2026"
    legacy_hash = hashlib.sha256((pwd + legacy_salt).encode("utf-8")).hexdigest()

    # Legacy hash should verify and flag needs_upgrade
    valid, needs_upgrade = _verify_password(pwd, legacy_hash)
    assert valid is True
    assert needs_upgrade is True

    # Wrong password on legacy hash fails
    valid_wrong, _ = _verify_password("WrongPwd", legacy_hash)
    assert valid_wrong is False


def test_brute_force_login_lockout():
    identifier = f"test_bf_{uuid.uuid4().hex[:6]}"
    _reset_failed_attempts(identifier)

    # First 4 failed attempts should not trigger lockout
    for _ in range(4):
        _record_failed_attempt(identifier)
        assert _check_rate_limit(identifier) is None

    # 5th failed attempt triggers lockout
    _record_failed_attempt(identifier)
    lockout_msg = _check_rate_limit(identifier)
    assert lockout_msg is not None
    assert "Too many failed login attempts" in lockout_msg

    # Resetting clears lockout
    _reset_failed_attempts(identifier)
    assert _check_rate_limit(identifier) is None


def test_billing_numeric_injection_and_nan_guards():
    # Negative qty
    res_neg = add_item_to_bill("BILL-FAKE", "SKU-SALT-01", -5.0)
    assert res_neg["status"] == "error"

    # Zero qty
    res_zero = add_item_to_bill("BILL-FAKE", "SKU-SALT-01", 0.0)
    assert res_zero["status"] == "error"

    # NaN qty
    res_nan = add_item_to_bill("BILL-FAKE", "SKU-SALT-01", float("nan"))
    assert res_nan["status"] == "error"

    # Inf qty
    res_inf = add_item_to_bill("BILL-FAKE", "SKU-SALT-01", float("inf"))
    assert res_inf["status"] == "error"

    # Edit item qty NaN
    res_edit_nan = edit_item_qty("BILL-FAKE", "SKU-SALT-01", float("nan"))
    assert res_edit_nan["status"] == "error"


def test_credit_numeric_injection_and_nan_guards():
    # Charge khata NaN / Inf / Negative
    assert charge_khata("Test Cust", float("nan"))["status"] == "error"
    assert charge_khata("Test Cust", float("inf"))["status"] == "error"
    assert charge_khata("Test Cust", -100.0)["status"] == "error"
    assert charge_khata("Test Cust", 0.0)["status"] == "error"

    # Record payment NaN / Inf / Negative
    assert record_payment("Test Cust", float("nan"))["status"] == "error"
    assert record_payment("Test Cust", float("inf"))["status"] == "error"
    assert record_payment("Test Cust", -50.0)["status"] == "error"
    assert record_payment("Test Cust", 0.0)["status"] == "error"


def test_inventory_numeric_injection_and_nan_guards():
    # Negative / NaN cost price in add_product
    res = add_product("SecItem", "General", "piece", False, -10.0, 50.0, 5.0, "1234")
    assert res["status"] == "error"

    res_nan = add_product("SecItem", "General", "piece", False, float("nan"), 50.0, 5.0, "1234")
    assert res_nan["status"] == "error"

    res_zero_mrp = add_product("SecItem", "General", "piece", False, 10.0, 0.0, 5.0, "1234")
    assert res_zero_mrp["status"] == "error"

    # Receive stock NaN / Inf / Negative
    res_rcv_nan = receive_stock("SKU-SALT-01", float("nan"))
    assert res_rcv_nan["status"] == "error"

    res_rcv_neg = receive_stock("SKU-SALT-01", -10.0)
    assert res_rcv_neg["status"] == "error"


def test_analytics_invalid_date_validation():
    # Invalid date string should return clean error dict instead of crashing
    res = daily_summary("invalid-date-format")
    assert res["status"] == "error"
    assert "Invalid date format" in res["message"]

    res2 = daily_summary("2026/13/45")
    assert res2["status"] == "error"


def test_path_traversal_defense():
    os.makedirs("generated_docs", exist_ok=True)
    test_doc = os.path.join("generated_docs", "test_safe_invoice.pdf")
    with open(test_doc, "w") as f:
        f.write("safe")

    try:
        # Legitimate file inside generated_docs is accepted
        assert is_safe_generated_file(test_doc) is True

        # Path traversal attempts are rejected
        assert is_safe_generated_file("../.env") is False
        assert is_safe_generated_file("../../boot.ini") is False
        assert is_safe_generated_file("generated_docs/../../.env") is False
        assert is_safe_generated_file("") is False
        assert is_safe_generated_file(None) is False
    finally:
        if os.path.exists(test_doc):
            os.remove(test_doc)
