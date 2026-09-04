import os
import pytest
from db.seed import seed_database
from skills.billing import (
    start_bill,
    add_item_to_bill,
    edit_item_qty,
    remove_item_from_bill,
    preview_bill,
    finalize_bill
)

TEST_DB = "test_billing_edge.db"

@pytest.fixture(autouse=True)
def setup_test_db():
    import db.models
    orig_path = db.models.DEFAULT_DB_PATH
    db.models.DEFAULT_DB_PATH = TEST_DB
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    seed_database(TEST_DB)
    yield
    db.models.DEFAULT_DB_PATH = orig_path
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

def test_edit_and_remove_item_from_bill():
    bill_res = start_bill("Anita Roy")
    bill_id = bill_res["bill_id"]

    # 1. Add item
    add_item_to_bill(bill_id, "Sugar", 5)
    add_item_to_bill(bill_id, "Salt", 2)

    # 2. Edit quantity
    edit_res = edit_item_qty(bill_id, "Sugar", new_qty=10)
    assert edit_res["status"] == "success"

    prev1 = preview_bill(bill_id)
    assert prev1["summary"]["subtotal"] == (10 * 48.0) + (2 * 28.0)

    # 3. Remove item
    rem_res = remove_item_from_bill(bill_id, "Salt")
    assert rem_res["status"] == "success"

    prev2 = preview_bill(bill_id)
    assert len(prev2["items"]) == 1
    assert prev2["items"][0]["name"] == "Refined White Sugar 1kg"

def test_finalize_bill_invalid_payment_mode():
    bill_res = start_bill("Walk-in")
    bill_id = bill_res["bill_id"]
    add_item_to_bill(bill_id, "Sugar", 1)

    fin = finalize_bill(bill_id, payment_mode="bitcoin")
    assert fin["status"] == "error"
    assert "Invalid payment mode" in fin["message"]

def test_finalize_nonexistent_bill():
    fin = finalize_bill("BILL-INVALID-999", payment_mode="cash")
    assert fin["status"] == "error"
    assert "not found" in fin["message"]
