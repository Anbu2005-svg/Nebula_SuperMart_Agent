import pytest
import os
from db.seed import seed_database
from skills.billing import start_bill, add_item_to_bill, finalize_bill, preview_bill
from skills.inventory import get_stock

TEST_DB = "test_idempotency.db"

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

def test_idempotency_prevents_double_billing():
    stock_info = get_stock("SKU-MILK-1L")
    initial_qty = stock_info["product"]["quantity"]
    
    bill_res = start_bill()
    bill_id = bill_res["bill_id"]
    add_item_to_bill(bill_id, "SKU-MILK-1L", 2)
    
    # First finalization with update_id "UPDATE_12345"
    res1 = finalize_bill(bill_id, payment_mode="upi", idempotency_key="UPDATE_12345")
    assert res1["bill_status"] == "finalized"
    
    stock_mid = get_stock("SKU-MILK-1L")
    assert stock_mid["product"]["quantity"] == initial_qty - 2
    
    # Retried finalization with SAME update_id "UPDATE_12345"
    res2 = finalize_bill(bill_id, payment_mode="upi", idempotency_key="UPDATE_12345")
    assert res2["bill_status"] == "finalized"
    
    # Verify stock was NOT decremented a second time!
    stock_final = get_stock("SKU-MILK-1L")
    assert stock_final["product"]["quantity"] == initial_qty - 2
