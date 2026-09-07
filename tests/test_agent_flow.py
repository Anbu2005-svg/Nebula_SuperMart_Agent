import os
import pytest
from db.seed import seed_database
from skills.billing import start_bill, add_item_to_bill, preview_bill, finalize_bill
from skills.credit import charge_khata, get_khata_balance, record_payment
from skills.preferences import set_preference, get_preference
from docgen.invoice_template import generate_pdf_invoice
from docgen.deck_builder import generate_analysis_pptx

TEST_DB = "test_end_to_end.db"

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

def test_full_billing_and_pdf_flow():
    # 1. Start bill
    bill_res = start_bill(customer_name="Ravi Kumar")
    bill_id = bill_res["bill_id"]
    assert bill_id.startswith("BILL-")

    # 2. Add items
    add_item_to_bill(bill_id, "Aashirvaad Whole Wheat Atta", 2)
    add_item_to_bill(bill_id, "Amul Pasteurised Butter", 1)

    # 3. Preview bill
    prev = preview_bill(bill_id)
    assert prev["status"] == "success"
    assert len(prev["items"]) == 2
    assert prev["summary"]["grand_total"] > 0

    # 4. Finalize bill
    fin = finalize_bill(bill_id, payment_mode="upi")
    assert fin["bill_status"] == "finalized"

    # 5. Generate PDF
    pdf_path = generate_pdf_invoice(bill_id)
    assert os.path.exists(pdf_path)
    assert pdf_path.endswith(".pdf")

def test_khata_credit_lifecycle():
    b_start = get_khata_balance("Priya Sharma").get("khata_balance", 0.0)
    # 1. Charge Khata
    chg = charge_khata("Priya Sharma", 350.0)
    assert chg["status"] == "success"
    
    # 2. Check balance
    bal1 = get_khata_balance("Priya Sharma")
    assert bal1["khata_balance"] == b_start + 350.0

    # 3. Record payment
    pmt = record_payment("Priya Sharma", 200.0)
    assert pmt["status"] == "success"

    # 4. Verify balance
    bal2 = get_khata_balance("Priya Sharma")
    assert bal2["khata_balance"] == b_start + 150.0

def test_pptx_generation():
    deck_path = generate_analysis_pptx("Today")
    assert os.path.exists(deck_path)
    assert deck_path.endswith(".pptx")

def test_preferences_persistence():
    set_preference("owner_123", "default_payment_mode", "upi")
    pref = get_preference("owner_123", "default_payment_mode")
    assert pref["status"] == "success"
    assert pref["value"] == "upi"

def test_list_all_products():
    from skills.inventory import list_all_products
    res = list_all_products()
    assert res["status"] == "success"
    assert res["count"] >= 10
    assert len(res["products"]) >= 10

def test_add_product_and_receive_stock():
    from skills.inventory import add_product, receive_stock, get_stock
    import uuid

    unique_name = f"Test Bhujia {uuid.uuid4().hex[:6]}"

    # 1. Add product
    add_res = add_product(
        name=unique_name,
        category="Snacks & Packaged Food",
        unit="packet",
        is_loose=False,
        cost_price=45.0,
        mrp=60.0,
        gst_slab=12.0,
        hsn_code="2106",
        quantity=50.0,
        reorder_level=10.0
    )
    assert add_res["status"] == "success"
    sku = add_res["sku_id"]

    # 2. Check stock
    stk = get_stock(sku)
    assert stk["status"] == "success"
    assert stk["product"]["quantity"] == 50.0

    # 3. Receive extra stock
    rec = receive_stock(sku, qty=25.0, cost_price=45.0)
    assert rec["status"] == "success"
    assert rec["new_quantity"] == 75.0
