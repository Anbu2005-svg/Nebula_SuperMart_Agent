import os
from db.models import get_db_connection, init_db

SAMPLE_PRODUCTS = [
    {
        "sku_id": "SKU-ATTA-10",
        "name": "Aashirvaad Whole Wheat Atta 10kg",
        "category": "Grains & Flour",
        "unit": "packet",
        "is_loose": False,
        "cost_price": 380.0,
        "mrp": 440.0,
        "gst_slab": 5.0,
        "hsn_code": "1101",
        "quantity": 30.0,
        "reorder_level": 5.0
    },
    {
        "sku_id": "SKU-SALT-01",
        "name": "Tata Iodized Salt 1kg",
        "category": "Pantry Basics",
        "unit": "packet",
        "is_loose": False,
        "cost_price": 20.0,
        "mrp": 28.0,
        "gst_slab": 0.0,
        "hsn_code": "2501",
        "quantity": 50.0,
        "reorder_level": 10.0
    },
    {
        "sku_id": "SKU-BUTTER-500",
        "name": "Amul Pasteurised Butter 500g",
        "category": "Dairy",
        "unit": "packet",
        "is_loose": False,
        "cost_price": 235.0,
        "mrp": 275.0,
        "gst_slab": 12.0,
        "hsn_code": "0405",
        "quantity": 20.0,
        "reorder_level": 5.0
    },
    {
        "sku_id": "SKU-OIL-1L",
        "name": "Fortune Sunlite Sunflower Oil 1L",
        "category": "Edible Oils",
        "unit": "litre",
        "is_loose": False,
        "cost_price": 125.0,
        "mrp": 155.0,
        "gst_slab": 5.0,
        "hsn_code": "1512",
        "quantity": 40.0,
        "reorder_level": 8.0
    },
    {
        "sku_id": "SKU-MAGGI-70",
        "name": "Maggi 2-Minute Instant Noodles 70g",
        "category": "Snacks & Packaged Food",
        "unit": "packet",
        "is_loose": False,
        "cost_price": 12.0,
        "mrp": 14.0,
        "gst_slab": 18.0,
        "hsn_code": "1902",
        "quantity": 100.0,
        "reorder_level": 20.0
    },
    {
        "sku_id": "SKU-MILK-1L",
        "name": "Amul Taaza Toned Milk 1L",
        "category": "Dairy",
        "unit": "packet",
        "is_loose": False,
        "cost_price": 54.0,
        "mrp": 56.0,
        "gst_slab": 0.0,
        "hsn_code": "0401",
        "quantity": 25.0,
        "reorder_level": 10.0
    },
    {
        "sku_id": "SKU-SUGAR-1K",
        "name": "Refined White Sugar 1kg",
        "category": "Pantry Basics",
        "unit": "kg",
        "is_loose": True,
        "cost_price": 40.0,
        "mrp": 48.0,
        "gst_slab": 5.0,
        "hsn_code": "1701",
        "quantity": 60.0,
        "reorder_level": 15.0
    },
    {
        "sku_id": "SKU-TEA-250",
        "name": "Brooke Bond Red Label Tea 250g",
        "category": "Beverages",
        "unit": "packet",
        "is_loose": False,
        "cost_price": 110.0,
        "mrp": 140.0,
        "gst_slab": 5.0,
        "hsn_code": "0902",
        "quantity": 15.0,
        "reorder_level": 5.0
    },
    {
        "sku_id": "SKU-SOAP-125",
        "name": "Dettol Original Bathing Soap 125g",
        "category": "Personal Care",
        "unit": "piece",
        "is_loose": False,
        "cost_price": 38.0,
        "mrp": 48.0,
        "gst_slab": 18.0,
        "hsn_code": "3401",
        "quantity": 40.0,
        "reorder_level": 10.0
    },
    {
        "sku_id": "SKU-RICE-5K",
        "name": "India Gate Basmati Rice Feast Rozzana 5kg",
        "category": "Grains & Flour",
        "unit": "packet",
        "is_loose": False,
        "cost_price": 390.0,
        "mrp": 475.0,
        "gst_slab": 5.0,
        "hsn_code": "1006",
        "quantity": 12.0,
        "reorder_level": 4.0
    }
]

SAMPLE_CUSTOMERS = [
    {"name": "Ravi Kumar", "khata_balance": 0.0},
    {"name": "Priya Sharma", "khata_balance": 250.0},
    {"name": "Suresh Patel", "khata_balance": 0.0}
]


def seed_database(db_path=None):
    """Initialize schema and seed PostgreSQL database with sample products and customers."""
    print("Initializing PostgreSQL schema...")
    init_db()
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        # Seed Products — upsert using ON CONFLICT
        for p in SAMPLE_PRODUCTS:
            cur.execute("""
                INSERT INTO products (sku_id, name, category, unit, is_loose, cost_price, mrp, gst_slab, hsn_code, quantity, reorder_level)
                VALUES (%(sku_id)s, %(name)s, %(category)s, %(unit)s, %(is_loose)s, %(cost_price)s, %(mrp)s, %(gst_slab)s, %(hsn_code)s, %(quantity)s, %(reorder_level)s)
                ON CONFLICT (sku_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    category = EXCLUDED.category,
                    cost_price = EXCLUDED.cost_price,
                    mrp = EXCLUDED.mrp,
                    gst_slab = EXCLUDED.gst_slab,
                    quantity = EXCLUDED.quantity,
                    reorder_level = EXCLUDED.reorder_level
            """, p)

        # Seed Customers — upsert
        for c in SAMPLE_CUSTOMERS:
            cur.execute("""
                INSERT INTO customers (name, khata_balance)
                VALUES (%(name)s, %(khata_balance)s)
                ON CONFLICT (name) DO UPDATE SET
                    khata_balance = EXCLUDED.khata_balance
            """, c)

        conn.commit()
        cur.close()
        print(f"PostgreSQL database seeded with {len(SAMPLE_PRODUCTS)} products and {len(SAMPLE_CUSTOMERS)} customers.")
    except Exception as e:
        conn.rollback()
        print(f"Seeding error: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    seed_database()
