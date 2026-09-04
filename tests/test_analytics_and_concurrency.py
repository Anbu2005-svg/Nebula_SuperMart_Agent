import os
import pytest
import threading
from db.seed import seed_database
from skills.billing import start_bill, add_item_to_bill, finalize_bill
from skills.analytics import daily_summary, close_day

TEST_DB = "test_analytics_conc.db"

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

def test_daily_summary_and_close_day():
    initial_summary = daily_summary()
    initial_bills = initial_summary["total_bills"]
    initial_sales = initial_summary["total_sales"]

    # Cut a cash bill (Maggi 10 pkts @ 14 = 140 subtotal + 18% GST 25.2 = 165.20 total)
    b1 = start_bill("Customer 1")["bill_id"]
    add_item_to_bill(b1, "Maggi", 10)
    finalize_bill(b1, payment_mode="cash")

    # Cut a UPI bill (Butter 2 pkts @ 275 = 550 subtotal + 12% GST 66.0 = 616.00 total)
    b2 = start_bill("Customer 2")["bill_id"]
    add_item_to_bill(b2, "Butter", 2)
    finalize_bill(b2, payment_mode="upi")

    # Get daily summary
    summary = daily_summary()
    assert summary["status"] == "success"
    assert summary["total_bills"] == initial_bills + 2
    assert round(summary["total_sales"], 2) == round(initial_sales + 165.20 + 616.00, 2)

    # Close day
    closed = close_day()
    assert closed["status"] == "success"
    assert closed["total_bills"] == initial_bills + 2

def test_concurrency_transaction_lock():
    import db.models
    orig_path = db.models.DEFAULT_DB_PATH
    results = []

    def make_sale(cust_name):
        db.models.DEFAULT_DB_PATH = TEST_DB
        try:
            b_id = start_bill("Ravi Kumar")["bill_id"]
            add_res = add_item_to_bill(b_id, "Salt", 1)
            res = finalize_bill(b_id, payment_mode="cash")
            results.append(res)
        except Exception as e:
            results.append({"status": "exception", "message": str(e)})

    threads = []
    for i in range(5):
        t = threading.Thread(target=make_sale, args=(f"Cashier Thread {i}",))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    db.models.DEFAULT_DB_PATH = orig_path
    assert len(results) == 5
    statuses = [r if isinstance(r, str) else r.get("status") for r in results]
    assert all(s == "success" or s == "finalized" for s in statuses), f"Thread results: {results}"
