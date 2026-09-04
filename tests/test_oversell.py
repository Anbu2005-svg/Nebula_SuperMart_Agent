import pytest
import os
from db.models import init_db, get_db_connection
from db.seed import seed_database
from skills.billing import start_bill, add_item_to_bill, finalize_bill, preview_bill
from skills.inventory import get_stock

TEST_DB = "test_supermarket.db"

@pytest.fixture(autouse=True)
def setup_test_db():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    seed_database(TEST_DB)
    # Monkeypatch DEFAULT_DB_PATH in models
    import db.models
    orig_path = db.models.DEFAULT_DB_PATH
    db.models.DEFAULT_DB_PATH = TEST_DB
    yield
    db.models.DEFAULT_DB_PATH = orig_path
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

def test_oversell_guard_refusal():
    # Attempting to add/finalize more items than available in stock
    stock_info = get_stock("SKU-SALT-01")
    curr_qty = stock_info["product"]["quantity"] # Should be 50.0
    
    # 1. Start bill
    bill_res = start_bill()
    bill_id = bill_res["bill_id"]
    
    # 2. Add 100 items (exceeds stock of 50)
    add_res = add_item_to_bill(bill_id, "SKU-SALT-01", 100)
    assert add_res["status"] == "oversell_warning"
    assert "exceeds available stock" in add_res["message"] or "Only" in add_res["message"]

def test_stock_decrements_on_finalization():
    stock_info = get_stock("SKU-SALT-01")
    initial_qty = stock_info["product"]["quantity"]
    
    bill_res = start_bill()
    bill_id = bill_res["bill_id"]
    
    add_item_to_bill(bill_id, "SKU-SALT-01", 5)
    fin_res = finalize_bill(bill_id, payment_mode="cash")
    assert fin_res["bill_status"] == "finalized"
    
    stock_after = get_stock("SKU-SALT-01")
    assert stock_after["product"]["quantity"] == initial_qty - 5
