import uuid
from typing import Dict, Any, List, Optional
from db.models import get_db_connection, immediate_transaction
from skills.audit import _log_event


def get_stock(query: str) -> Dict[str, Any]:
    """Get stock information for a product by SKU ID or product name search."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        # Search by exact SKU first
        cur.execute("SELECT * FROM products WHERE sku_id = %s", (query.strip(),))
        product = cur.fetchone()

        if not product:
            # Search by name (fuzzy case-insensitive using ILIKE)
            cur.execute("SELECT * FROM products WHERE name ILIKE %s ORDER BY name ASC LIMIT 5", (f"%{query.strip()}%",))
            products = cur.fetchall()
            if not products:
                return {"status": "error", "message": f"No product found matching '{query}'"}
            if len(products) > 1:
                matches = [{"sku_id": p["sku_id"], "name": p["name"], "quantity": p["quantity"], "mrp": p["mrp"]} for p in products]
                return {
                    "status": "multiple_matches",
                    "message": f"Found multiple products matching '{query}'. Please specify SKU or exact name.",
                    "matches": matches
                }
            product = products[0]

        cur.close()
        return {
            "status": "success",
            "product": {
                "sku_id": product["sku_id"],
                "name": product["name"],
                "category": product["category"],
                "unit": product["unit"],
                "is_loose": bool(product["is_loose"]),
                "cost_price": product["cost_price"],
                "mrp": product["mrp"],
                "gst_slab": product["gst_slab"],
                "hsn_code": product["hsn_code"],
                "quantity": product["quantity"],
                "reorder_level": product["reorder_level"],
                "is_low_stock": product["quantity"] <= product["reorder_level"]
            }
        }
    finally:
        conn.close()


def receive_stock(sku_id: str, qty: float, cost_price: Optional[float] = None, mrp: Optional[float] = None) -> Dict[str, Any]:
    """Receive inventory stock (increases stock quantity). Updates cost_price and optional mrp."""
    if qty <= 0:
        return {"status": "error", "message": "Received quantity must be positive"}

    conn = get_db_connection()
    try:
        with immediate_transaction(conn):
            cur = conn.cursor()
            cur.execute("SELECT * FROM products WHERE sku_id = %s", (sku_id.strip(),))
            product = cur.fetchone()
            if not product:
                cur.execute("SELECT * FROM products WHERE name ILIKE %s", (f"%{sku_id.strip()}%",))
                product = cur.fetchone()
                if not product:
                    return {"status": "error", "message": f"Product SKU '{sku_id}' not found. Add the product first."}

            real_sku = product["sku_id"]
            new_qty = product["quantity"] + qty
            new_cost = cost_price if cost_price is not None else product["cost_price"]
            new_mrp = mrp if mrp is not None else product["mrp"]

            if new_cost > new_mrp:
                return {"status": "error", "message": f"Cost price ({new_cost}) cannot exceed MRP ({new_mrp})"}

            cur.execute("""
                UPDATE products
                SET quantity = %s, cost_price = %s, mrp = %s
                WHERE sku_id = %s
            """, (new_qty, new_cost, new_mrp, real_sku))

            _log_event(conn, "STOCK_RECEIVED", "product", real_sku,
                       details={"product_name": product["name"], "qty_received": qty,
                                "cost_price": new_cost, "mrp": new_mrp},
                       old_value=product["quantity"], new_value=new_qty)
            cur.close()

            return {
                "status": "success",
                "message": f"Received {qty} {product['unit']} of {product['name']}. New quantity: {new_qty}",
                "sku_id": real_sku,
                "name": product["name"],
                "previous_quantity": product["quantity"],
                "new_quantity": new_qty,
                "cost_price": new_cost,
                "mrp": new_mrp
            }
    finally:
        conn.close()


def add_product(
    name: str,
    category: str,
    unit: str,
    is_loose: bool,
    cost_price: float,
    mrp: float,
    gst_slab: float,
    hsn_code: str,
    quantity: float = 0.0,
    reorder_level: float = 10.0,
    sku_id: Optional[str] = None
) -> Dict[str, Any]:
    """Add a new product SKU to the catalog."""
    if cost_price > mrp:
        return {"status": "error", "message": f"Cost price ({cost_price}) cannot exceed MRP ({mrp})"}
    if gst_slab not in [0, 5, 12, 18]:
        return {"status": "error", "message": "GST slab must be one of: 0, 5, 12, 18"}

    generated_sku = sku_id.strip() if sku_id else f"SKU-{uuid.uuid4().hex[:6].upper()}"

    conn = get_db_connection()
    try:
        with immediate_transaction(conn):
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO products (sku_id, name, category, unit, is_loose, cost_price, mrp, gst_slab, hsn_code, quantity, reorder_level)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (generated_sku, name.strip(), category.strip(), unit.strip(), is_loose, cost_price, mrp, gst_slab, hsn_code.strip(), quantity, reorder_level))

            _log_event(conn, "PRODUCT_ADDED", "product", generated_sku,
                       details={"name": name, "category": category, "mrp": mrp, "gst_slab": gst_slab},
                       old_value=0, new_value=quantity)
            cur.close()

            return {
                "status": "success",
                "message": f"Product '{name}' added successfully with SKU: {generated_sku}",
                "sku_id": generated_sku,
                "name": name,
                "mrp": mrp,
                "quantity": quantity
            }
    except Exception as e:
        return {"status": "error", "message": f"Failed to add product: {str(e)}"}
    finally:
        conn.close()


def list_low_stock() -> Dict[str, Any]:
    """List all products where current stock level is less than or equal to reorder level."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM products WHERE quantity <= reorder_level ORDER BY quantity ASC")
        products = cur.fetchall()
        cur.close()

        items = [{
            "sku_id": p["sku_id"],
            "name": p["name"],
            "quantity": p["quantity"],
            "unit": p["unit"],
            "reorder_level": p["reorder_level"]
        } for p in products]

        return {"status": "success", "count": len(items), "low_stock_items": items}
    finally:
        conn.close()


def list_all_products(category: Optional[str] = None) -> Dict[str, Any]:
    """List all available products in inventory with stock levels, MRPs, units, and categories."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        if category:
            cur.execute("SELECT * FROM products WHERE category ILIKE %s ORDER BY name ASC", (f"%{category.strip()}%",))
        else:
            cur.execute("SELECT * FROM products ORDER BY category ASC, name ASC")
        products = cur.fetchall()
        cur.close()

        items = [{
            "sku_id": p["sku_id"],
            "name": p["name"],
            "category": p["category"],
            "quantity": p["quantity"],
            "unit": p["unit"],
            "mrp": p["mrp"],
            "cost_price": p["cost_price"],
            "gst_slab": p["gst_slab"],
            "hsn_code": p["hsn_code"],
            "is_low_stock": p["quantity"] <= p["reorder_level"]
        } for p in products]

        return {"status": "success", "count": len(items), "products": items}
    finally:
        conn.close()


def search_products(query: str) -> Dict[str, Any]:
    """Search products catalog by query string."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM products WHERE name ILIKE %s OR category ILIKE %s OR sku_id ILIKE %s ORDER BY name ASC",
            (f"%{query}%", f"%{query}%", f"%{query}%"))
        products = cur.fetchall()
        cur.close()

        items = [{
            "sku_id": p["sku_id"],
            "name": p["name"],
            "category": p["category"],
            "quantity": p["quantity"],
            "unit": p["unit"],
            "mrp": p["mrp"],
            "cost_price": p["cost_price"],
            "gst_slab": p["gst_slab"]
        } for p in products]

        return {"status": "success", "count": len(items), "products": items}
    finally:
        conn.close()
