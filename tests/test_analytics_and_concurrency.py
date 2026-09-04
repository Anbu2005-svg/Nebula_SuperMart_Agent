import os
import pytest
import threading
from db.seed import seed_database
from skills.billing import start_bill, add_item_to_bill, finalize_bill
from skills.analytics import daily_summary, close_day

TEST_DB = "test_analytics_conc.db"

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

def test_daily_summary_and_close_day():
    # Cut a cash bill
    b1 = start_bill("Customer 1")["bill_id"]
    add_item_to_bill(b1, "Maggi", 10)
    finalize_bill(b1, payment_mode="cash")

    # Cut a UPI bill
    b2 = start_bill("Customer 2")["bill_id"]
    add_item_to_bill(b2, "Amul Butter", 2)
    finalize_bill(b2, payment_mode="upi")

    # Get daily summary
    summary = daily_summary()
    assert summary["status"] == "success"
    assert summary["summary"]["total_bills"] == 2
    assert summary["summary"]["total_revenue"] == (10 * 14.0) + (2 * 275.0)

    # Close day
    closed = close_day()
    assert closed["status"] == "success"
    assert closed["summary"]["total_bills"] == 2

def test_concurrency_transaction_lock():
    results = []

    def make_sale(cust_name):
        try:
            b_id = start_bill(cust_name)["bill_id"]
            add_item_to_bill(b_id, "Tata Salt", 1)
            res = finalize_bill(b_id, payment_mode="cash")
            results.append(res["status"])
        except Exception as e:
            results.append("error")

    threads = []
    for i in range(5):
        t = threading.Thread(target=make_sale, args=(f"Cashier Thread {i}",))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    assert len(results) == 5
    assert all(status == "success" for status in results)
