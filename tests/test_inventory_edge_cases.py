import os
import pytest
from db.seed import seed_database
from skills.inventory import add_product, receive_stock, search_products, list_low_stock, get_stock, update_gst_slab

TEST_DB = "test_inventory_edge.db"

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

def test_add_product_cost_exceeds_mrp():
    res = add_product("Overpriced Item", "Pantry", "packet", False, cost_price=150.0, mrp=100.0, gst_slab=5.0, hsn_code="1234")
    assert res["status"] == "error"
    assert "cannot exceed MRP" in res["message"]

def test_add_product_invalid_gst_slab():
    res = add_product("Invalid GST Item", "Pantry", "packet", False, cost_price=50.0, mrp=100.0, gst_slab=8.0, hsn_code="1234")
    assert res["status"] == "error"
    assert "GST slab must be one of" in res["message"]

def test_receive_stock_negative_qty():
    res = receive_stock("SKU-MILK-01", qty=-5.0, cost_price=40.0)
    assert res["status"] == "error"
    assert "positive" in res["message"]


def test_receive_stock_cost_cannot_exceed_mrp():
    res = receive_stock("SKU-MAGGI-70", qty=5.0, cost_price=20.0, mrp=14.0)
    assert res["status"] == "error"
    assert "cannot exceed MRP" in res["message"]

def test_search_products():
    res = search_products("Amul")
    assert res["status"] == "success"
    assert res["count"] >= 2
    names = [p["name"] for p in res["products"]]
    assert "Amul Taaza Toned Milk 1L" in names
    assert "Amul Pasteurised Butter 100g" in names

def test_list_low_stock():
    # Artificially set a product stock low using psycopg2
    import db.models
    conn = db.models.get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE products SET quantity = 2 WHERE sku_id = 'SKU-RICE-1K'")
    conn.commit()
    conn.close()

    res = list_low_stock()
    assert res["status"] == "success"
    # SKU-RICE-1K has reorder_level=10 and we set quantity=2, so it must appear
    assert any("Rice" in item["name"] for item in res["low_stock_items"])

def test_update_gst_slab():
    res = update_gst_slab(new_gst_slab=5.0, sku_or_name="Sugar")
    assert res["status"] == "success"
    assert res["new_gst_slab"] == 5.0
    st = get_stock("Sugar")
    assert st["product"]["gst_slab"] == 5.0

