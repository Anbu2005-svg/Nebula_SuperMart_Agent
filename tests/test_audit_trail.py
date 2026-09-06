import os
import json
import pytest
from db.seed import seed_database
from db.models import get_db_connection
from skills.billing import start_bill, add_item_to_bill, edit_item_qty, remove_item_from_bill, finalize_bill, preview_bill
from skills.inventory import receive_stock, add_product, get_stock
from skills.credit import charge_khata, record_payment
from skills.preferences import set_preference
from skills.audit import get_audit_trail

TEST_DB = "test_audit_trail.db"

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

def _fetch_events():
    """Read raw audit_log rows ordered oldest first."""
    conn = get_db_connection()
    try:
        cur = conn.execute("SELECT * FROM audit_log ORDER BY id ASC")
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

def test_audit_logs_bill_lifecycle():
    bill_id = start_bill(customer_name="Ravi Kumar")["bill_id"]
    add_item_to_bill(bill_id, "Maggi", 3)
    add_item_to_bill(bill_id, "Salt", 2)
    edit_item_qty(bill_id, "Maggi", new_qty=5)
    remove_item_from_bill(bill_id, "Salt")
    fin = finalize_bill(bill_id, payment_mode="cash")
    assert fin["bill_status"] == "finalized"

    events = _fetch_events()
    seq = [e["event_type"] for e in events]

    # Ordered lifecycle sequence
    assert seq == [
        "BILL_CREATED",
        "ITEM_ADDED",       # Maggi
        "ITEM_ADDED",       # Salt
        "ITEM_QTY_UPDATED", # Maggi 3 -> 5
        "ITEM_REMOVED",     # Salt
        "STOCK_DECREMENTED",# Maggi
        "BILL_FINALIZED"
    ]

    # BILL_CREATED details
    created = events[0]
    assert created["entity_type"] == "bill" and created["entity_id"] == bill_id
    assert json.loads(created["details"])["customer_name"] == "Ravi Kumar"

    # ITEM_ADDED for Maggi
    maggi_added = events[1]
    d = json.loads(maggi_added["details"])
    assert d["sku_id"] == "SKU-MAGGI-70" and d["qty"] == 3 and d["unit_price"] == 14.0

    # ITEM_QTY_UPDATED old -> new
    upd = events[3]
    assert upd["old_value"] == 3 and upd["new_value"] == 5

    # ITEM_REMOVED for Salt
    rem = events[4]
    assert json.loads(rem["details"])["sku_id"] == "SKU-SALT-01"

    # STOCK_DECREMENTED: Maggi 100 -> 95, references bill
    dec = events[5]
    assert dec["entity_type"] == "product" and dec["entity_id"] == "SKU-MAGGI-70"
    assert dec["old_value"] == 100.0 and dec["new_value"] == 95.0
    assert json.loads(dec["details"])["bill_id"] == bill_id

    # No decrement for the removed Salt item
    assert all(e["entity_id"] != "SKU-SALT-01" for e in events if e["event_type"] == "STOCK_DECREMENTED")

    # BILL_FINALIZED details
    fin_ev = events[6]
    fd = json.loads(fin_ev["details"])
    assert fd["payment_mode"] == "cash" and fd["customer_name"] == "Ravi Kumar"

def test_audit_no_log_on_oversell_rejection():
    bill_id = start_bill("Walk-in")["bill_id"]

    # Attempt to add more than stock (Salt stock = 50)
    res = add_item_to_bill(bill_id, "SKU-SALT-01", 500)
    assert res["status"] == "oversell_warning"

    # Drain Maggi stock, add to a second bill, then fail finalize
    drain_bill = start_bill("Drain Customer")["bill_id"]
    add_item_to_bill(drain_bill, "Maggi", 100)
    finalize_bill(drain_bill, payment_mode="cash")

    bill2 = start_bill("Another")["bill_id"]
    add_item_to_bill(bill2, "Maggi", 5)  # stock is now 0 -> rejected
    fin = finalize_bill(bill2, payment_mode="cash")  # empty bill rejected
    assert fin["status"] == "error"

    events = _fetch_events()
    b2_events = [e for e in events if e["entity_id"] == bill2 and e["event_type"] in ("ITEM_ADDED", "STOCK_DECREMENTED")]
    assert b2_events == []

    # Also no STOCK_DECREMENTED for the drained SKU from bill2
    assert all(e["entity_id"] != "SKU-MAGGI-70" for e in events if e["event_type"] == "STOCK_DECREMENTED" and json.loads(e["details"] or "{}").get("bill_id") == bill2)

def test_audit_logs_stock_receipt_and_product():
    # receive_stock on Butter (stock 20 -> 45)
    rec = receive_stock("SKU-BUTTER-500", qty=25.0, cost_price=235.0)
    assert rec["status"] == "success"

    events = _fetch_events()
    rcv = [e for e in events if e["event_type"] == "STOCK_RECEIVED"]
    assert len(rcv) == 1
    assert rcv[0]["entity_id"] == "SKU-BUTTER-500"
    assert rcv[0]["old_value"] == 20.0 and rcv[0]["new_value"] == 45.0
    d = json.loads(rcv[0]["details"])
    assert d["qty_received"] == 25.0

    # add_product
    add_res = add_product(name="Haldiram Bhujia 200g", category="Snacks & Packaged Food",
                          unit="packet", is_loose=False, cost_price=45.0, mrp=60.0,
                          gst_slab=12.0, hsn_code="2106", quantity=50.0, reorder_level=10.0)
    assert add_res["status"] == "success"

    events = _fetch_events()
    add_ev = [e for e in events if e["event_type"] == "PRODUCT_ADDED"]
    assert len(add_ev) == 1
    assert add_ev[0]["entity_id"] == add_res["sku_id"]
    assert add_ev[0]["old_value"] == 0 and add_ev[0]["new_value"] == 50.0

def test_audit_logs_khata_events():
    # Direct charge
    charge_khata("Priya Sharma", 350.0)
    # Payment
    record_payment("Priya Sharma", 200.0)
    # Finalize-path khata charge
    bill_id = start_bill(customer_name="Priya Sharma")["bill_id"]
    add_item_to_bill(bill_id, "Maggi", 2)
    fin = finalize_bill(bill_id, payment_mode="khata")
    assert fin["bill_status"] == "finalized"

    events = _fetch_events()
    khata_events = [e for e in events if e["event_type"] in ("KHATA_CHARGED", "KHATA_PAYMENT_RECORDED")]

    assert len(khata_events) == 3
    assert khata_events[0]["event_type"] == "KHATA_CHARGED"
    assert khata_events[0]["old_value"] == 250.0 and khata_events[0]["new_value"] == 600.0
    assert khata_events[1]["event_type"] == "KHATA_PAYMENT_RECORDED"
    assert khata_events[1]["old_value"] == 600.0 and khata_events[1]["new_value"] == 400.0

    # Finalize-path KHATA_CHARGED: 400 -> 400 + grand_total
    fin_charge = khata_events[2]
    assert json.loads(fin_charge["details"])["bill_id"] == bill_id
    grand_total = fin["summary"]["grand_total"]
    assert fin_charge["old_value"] == 400.0
    assert fin_charge["new_value"] == round(400.0 + grand_total, 2)

def test_get_audit_trail_filtering():
    # Sell Maggi and Butter
    b1 = start_bill("Customer 1")["bill_id"]
    add_item_to_bill(b1, "Maggi", 10)
    finalize_bill(b1, payment_mode="cash")
    b2 = start_bill("Customer 2")["bill_id"]
    add_item_to_bill(b2, "Butter", 1)
    finalize_bill(b2, payment_mode="cash")

    # Filter by product + event type
    res = get_audit_trail(query="Maggi", event_type="STOCK_DECREMENTED")
    assert res["status"] == "success"
    assert res["count"] >= 1
    for e in res["events"]:
        assert e["event_type"] == "STOCK_DECREMENTED"
        assert "Maggi" in e["entity_id"] or "Maggi" in json.dumps(e["details"])

    # Filter by bill id
    res_bill = get_audit_trail(query=b1)
    assert res_bill["status"] == "success"
    assert res_bill["count"] >= 1
    assert all(e["entity_id"] == b1 or b1 in json.dumps(e["details"] or {}) for e in res_bill["events"])

    # Empty result shape
    res_empty = get_audit_trail(query="NonExistentXYZ123")
    assert res_empty["status"] == "success"
    assert res_empty["count"] == 0
    assert res_empty["events"] == []

    # Limit clamping
    res_all = get_audit_trail()
    assert res_all["status"] == "success"
    assert res_all["count"] <= 100
    res_clamped_hi = get_audit_trail(limit=500)
    assert res_clamped_hi["status"] == "success" and res_clamped_hi["count"] <= 100
    res_clamped_lo = get_audit_trail(limit=0)
    assert res_clamped_lo["status"] == "success" and res_clamped_lo["count"] <= 1
