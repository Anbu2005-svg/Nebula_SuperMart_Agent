import os
import pytest
from db.seed import seed_database
from skills.inventory import add_product, receive_stock, search_products, list_low_stock, get_stock

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

def test_search_products():
    res = search_products("Amul")
    assert res["status"] == "success"
    assert res["count"] == 2
    names = [p["name"] for p in res["products"]]
    assert "Amul Taaza Toned Milk 1L" in names
    assert "Amul Pasteurised Butter 500g" in names

def test_list_low_stock():
    # Artificially set a product stock low
    import db.models
    conn = db.models.get_db_connection()
    conn.execute("UPDATE products SET quantity = 2 WHERE sku_id = 'SKU-RICE-5K'")
    conn.commit()
    conn.close()

    res = list_low_stock()
    assert res["status"] == "success"
    assert res["count"] == 1
    assert "India Gate Basmati Rice" in res["low_stock_items"][0]["name"]
