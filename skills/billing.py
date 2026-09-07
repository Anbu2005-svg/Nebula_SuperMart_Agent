import uuid
import sqlite3
from typing import Dict, Any, List, Optional
from db.models import get_db_connection, immediate_transaction
from skills.audit import _log_event

def _calculate_gst(line_subtotal: float, gst_slab: float) -> Dict[str, float]:
    """
    Pure function for GST calculation.
    Returns dict with rounded line_subtotal, cgst, sgst, line_gst, and line_total.
    Intra-state GST split: CGST = SGST = (line_subtotal * slab / 100) / 2.
    """
    subtotal = round(line_subtotal, 2)
    gst_total = subtotal * (gst_slab / 100.0)
    cgst = round(gst_total / 2.0, 2)
    sgst = round(gst_total / 2.0, 2)
    total_tax = cgst + sgst
    line_total = round(subtotal + total_tax, 2)
    
    return {
        "subtotal": subtotal,
        "cgst": cgst,
        "sgst": sgst,
        "total_tax": total_tax,
        "line_total": line_total
    }

def start_bill(customer_name: Optional[str] = None) -> Dict[str, Any]:
    """Start a new draft bill. Optionally associate with a customer name."""
    conn = get_db_connection()
    try:
        bill_id = f"BILL-{uuid.uuid4().hex[:8].upper()}"
        customer_id = None
        with immediate_transaction(conn):
            if customer_name:
                cur = conn.execute("SELECT customer_id FROM customers WHERE name LIKE ?", (f"%{customer_name.strip()}%",))
                cust = cur.fetchone()
                if cust:
                    customer_id = cust["customer_id"]
                else:
                    cur = conn.execute("INSERT INTO customers (name) VALUES (?)", (customer_name.strip(),))
                    customer_id = cur.lastrowid

            conn.execute("""
                INSERT INTO bills (bill_id, status, customer_id, subtotal, cgst, sgst, total)
                VALUES (?, 'draft', ?, 0.0, 0.0, 0.0, 0.0)
            """, (bill_id, customer_id))

            _log_event(conn, "BILL_CREATED", "bill", bill_id,
                       details={"customer_name": customer_name})
            
        return {
            "status": "success",
            "message": f"Draft bill created successfully with ID: {bill_id}",
            "bill_id": bill_id,
            "customer_name": customer_name
        }
    finally:
        conn.close()

def _resolve_sku(conn: sqlite3.Connection, sku_or_name: str) -> Optional[sqlite3.Row]:
    """Helper to resolve SKU ID or product name to a product record."""
    cur = conn.execute("SELECT * FROM products WHERE sku_id = ?", (sku_or_name.strip(),))
    product = cur.fetchone()
    if not product:
        cur = conn.execute("SELECT * FROM products WHERE name LIKE ? LIMIT 1", (f"%{sku_or_name.strip()}%",))
        product = cur.fetchone()
    return product

def add_item_to_bill(bill_id: str, sku_or_name: str, qty: float) -> Dict[str, Any]:
    """Add an item to a draft bill. Performs stock warning check and cost price guard check."""
    if qty <= 0:
        return {"status": "error", "message": "Item quantity must be greater than zero"}
        
    conn = get_db_connection()
    try:
        # Check bill state
        cur = conn.execute("SELECT * FROM bills WHERE bill_id = ?", (bill_id.strip(),))
        bill = cur.fetchone()
        if not bill:
            return {"status": "error", "message": f"Bill '{bill_id}' not found."}
        if bill["status"] != "draft":
            return {"status": "error", "message": f"Bill '{bill_id}' is already {bill['status']} and cannot be edited."}
            
        product = _resolve_sku(conn, sku_or_name)
        if not product:
            return {"status": "error", "message": f"Product matching '{sku_or_name}' not found."}
            
        # Oversell soft check during draft addition
        if qty > product["quantity"]:
            return {
                "status": "oversell_warning",
                "message": f"Cannot add {qty} {product['unit']} of {product['name']}. Only {product['quantity']} available in stock.",
                "available_stock": product["quantity"],
                "requested_qty": qty
            }
            
        # Below-cost guard check
        unit_price = product["mrp"]
        if unit_price < product["cost_price"]:
            return {
                "status": "error",
                "message": f"Selling price ({unit_price}) is below cost price ({product['cost_price']}) for product '{product['name']}'."
            }
            
        line_subtotal = qty * unit_price
        gst_info = _calculate_gst(line_subtotal, product["gst_slab"])
        
        with immediate_transaction(conn):
            # Check if item already exists in bill
            cur = conn.execute("SELECT * FROM bill_items WHERE bill_id = ? AND sku_id = ?", (bill_id.strip(), product["sku_id"]))
            existing = cur.fetchone()
            
            if existing:
                new_qty = existing["qty"] + qty
                if new_qty > product["quantity"]:
                    return {
                        "status": "oversell_warning",
                        "message": f"Updating total item qty to {new_qty} exceeds available stock ({product['quantity']}).",
                        "available_stock": product["quantity"]
                    }
                new_subtotal = new_qty * unit_price
                new_gst = _calculate_gst(new_subtotal, product["gst_slab"])
                conn.execute("""
                    UPDATE bill_items
                    SET qty = ?, line_total = ?
                    WHERE id = ?
                """, (new_qty, new_gst["line_total"], existing["id"]))
            else:
                conn.execute("""
                    INSERT INTO bill_items (bill_id, sku_id, qty, unit_price, gst_slab, line_total)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (bill_id.strip(), product["sku_id"], qty, unit_price, product["gst_slab"], gst_info["line_total"]))

            effective_qty = new_qty if existing else qty
            _log_event(conn, "ITEM_ADDED", "bill", bill_id,
                       details={"product_name": product["name"], "sku_id": product["sku_id"],
                                "qty": effective_qty, "unit_price": unit_price})
                
        return {
            "status": "success",
            "message": f"Added {qty} {product['unit']} of {product['name']} to bill {bill_id}.",
            "bill_id": bill_id,
            "product_name": product["name"],
            "qty": qty,
            "unit_price": unit_price,
            "line_total": gst_info["line_total"]
        }
    finally:
        conn.close()

def remove_item_from_bill(bill_id: str, sku_or_name: str) -> Dict[str, Any]:
    """Remove a line item from a draft bill."""
    conn = get_db_connection()
    try:
        cur = conn.execute("SELECT * FROM bills WHERE bill_id = ?", (bill_id.strip(),))
        bill = cur.fetchone()
        if not bill or bill["status"] != "draft":
            return {"status": "error", "message": f"Bill '{bill_id}' not found or not in draft state."}
            
        product = _resolve_sku(conn, sku_or_name)
        if not product:
            return {"status": "error", "message": f"Product matching '{sku_or_name}' not found."}
            
        with immediate_transaction(conn):
            conn.execute("DELETE FROM bill_items WHERE bill_id = ? AND sku_id = ?", (bill_id.strip(), product["sku_id"]))
            _log_event(conn, "ITEM_REMOVED", "bill", bill_id,
                       details={"product_name": product["name"], "sku_id": product["sku_id"]})
            
        return {
            "status": "success",
            "message": f"Removed '{product['name']}' from bill {bill_id}."
        }
    finally:
        conn.close()

def edit_item_qty(bill_id: str, sku_or_name: str, new_qty: float) -> Dict[str, Any]:
    """Edit the quantity of an existing line item in a draft bill."""
    if new_qty <= 0:
        return remove_item_from_bill(bill_id, sku_or_name)
        
    conn = get_db_connection()
    try:
        cur = conn.execute("SELECT * FROM bills WHERE bill_id = ?", (bill_id.strip(),))
        bill = cur.fetchone()
        if not bill or bill["status"] != "draft":
            return {"status": "error", "message": f"Bill '{bill_id}' not found or not in draft state."}
            
        product = _resolve_sku(conn, sku_or_name)
        if not product:
            return {"status": "error", "message": f"Product matching '{sku_or_name}' not found."}
            
        if new_qty > product["quantity"]:
            return {
                "status": "oversell_warning",
                "message": f"Requested quantity {new_qty} exceeds available stock ({product['quantity']}).",
                "available_stock": product["quantity"]
            }
            
        unit_price = product["mrp"]
        new_subtotal = new_qty * unit_price
        gst_info = _calculate_gst(new_subtotal, product["gst_slab"])
        
        with immediate_transaction(conn):
            cur = conn.execute("SELECT qty FROM bill_items WHERE bill_id = ? AND sku_id = ?",
                               (bill_id.strip(), product["sku_id"]))
            existing = cur.fetchone()
            if not existing:
                return {"status": "error", "message": f"Item '{product['name']}' not found in bill {bill_id}."}

            conn.execute("""
                UPDATE bill_items
                SET qty = ?, line_total = ?
                WHERE bill_id = ? AND sku_id = ?
            """, (new_qty, gst_info["line_total"], bill_id.strip(), product["sku_id"]))

            _log_event(conn, "ITEM_QTY_UPDATED", "bill", bill_id,
                       details={"product_name": product["name"], "sku_id": product["sku_id"]},
                       old_value=existing["qty"], new_value=new_qty)
            
        return {
            "status": "success",
            "message": f"Updated quantity of '{product['name']}' to {new_qty} in bill {bill_id}.",
            "new_qty": new_qty,
            "line_total": gst_info["line_total"]
        }
    finally:
        conn.close()

def preview_bill(bill_id: str) -> Dict[str, Any]:
    """Preview bill calculations (subtotal, CGST, SGST, total) without finalizing."""
    conn = get_db_connection()
    try:
        cur = conn.execute("""
            SELECT b.*, c.name as customer_name 
            FROM bills b 
            LEFT JOIN customers c ON b.customer_id = c.customer_id 
            WHERE b.bill_id = ?
        """, (bill_id.strip(),))
        bill = cur.fetchone()
        if not bill:
            return {"status": "error", "message": f"Bill '{bill_id}' not found."}
            
        cur = conn.execute("""
            SELECT bi.*, p.name as product_name, p.hsn_code, p.unit
            FROM bill_items bi
            JOIN products p ON bi.sku_id = p.sku_id
            WHERE bi.bill_id = ?
        """, (bill_id.strip(),))
        items = cur.fetchall()
        
        subtotal = 0.0
        cgst_total = 0.0
        sgst_total = 0.0
        
        item_previews = []
        for item in items:
            line_subtotal = item["qty"] * item["unit_price"]
            gst_info = _calculate_gst(line_subtotal, item["gst_slab"])
            
            subtotal += gst_info["subtotal"]
            cgst_total += gst_info["cgst"]
            sgst_total += gst_info["sgst"]
            
            item_previews.append({
                "sku_id": item["sku_id"],
                "name": item["product_name"],
                "hsn_code": item["hsn_code"],
                "unit": item["unit"],
                "qty": item["qty"],
                "unit_price": item["unit_price"],
                "gst_slab": item["gst_slab"],
                "line_subtotal": gst_info["subtotal"],
                "cgst": gst_info["cgst"],
                "sgst": gst_info["sgst"],
                "line_total": gst_info["line_total"]
            })
            
        grand_total = round(subtotal + cgst_total + sgst_total, 2)
        
        return {
            "status": "success",
            "bill_id": bill_id,
            "bill_status": bill["status"],
            "customer_name": bill["customer_name"] or "Walk-in Customer",
            "items": item_previews,
            "summary": {
                "subtotal": round(subtotal, 2),
                "cgst": round(cgst_total, 2),
                "sgst": round(sgst_total, 2),
                "total_gst": round(cgst_total + sgst_total, 2),
                "grand_total": grand_total
            }
        }
    finally:
        conn.close()

def finalize_bill(
    bill_id: str, 
    payment_mode: str, 
    payment_ref: Optional[str] = None, 
    idempotency_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Finalize a draft bill:
    1. Checks idempotency_log (if key provided).
    2. Enforces oversell guard inside an atomic write transaction (BEGIN IMMEDIATE).
    3. Decrements stock for all line items.
    4. Computes final tax and updates bill status to 'finalized'.
    5. Handles Khata ledger charge if payment_mode is 'khata'.
    """
    payment_mode = payment_mode.lower().strip()
    if payment_mode not in ["cash", "upi", "card", "khata"]:
        return {"status": "error", "message": "Invalid payment mode. Must be cash, upi, card, or khata."}
        
    conn = get_db_connection()
    try:
        # 1. Idempotency Check
        if idempotency_key:
            cur = conn.execute("SELECT * FROM idempotency_log WHERE update_id = ?", (str(idempotency_key),))
            if cur.fetchone():
                # Already processed! Return current bill state without re-executing
                return preview_bill(bill_id)

        with immediate_transaction(conn):
            # Fetch bill
            cur = conn.execute("SELECT * FROM bills WHERE bill_id = ?", (bill_id.strip(),))
            bill = cur.fetchone()
            if not bill:
                return {"status": "error", "message": f"Bill '{bill_id}' not found."}
            if bill["status"] == "finalized":
                return preview_bill(bill_id)
            if bill["status"] == "voided":
                return {"status": "error", "message": f"Bill '{bill_id}' has been voided."}

            # Fetch line items
            cur = conn.execute("SELECT * FROM bill_items WHERE bill_id = ?", (bill_id.strip(),))
            items = cur.fetchall()
            if not items:
                return {"status": "error", "message": "Cannot finalize an empty bill. Add items first."}

            # 2. Oversell Guard inside Atomic Transaction
            subtotal = 0.0
            cgst_total = 0.0
            sgst_total = 0.0
            item_stock_before: Dict[str, Any] = {}

            for item in items:
                cur = conn.execute("SELECT * FROM products WHERE sku_id = ?", (item["sku_id"],))
                product = cur.fetchone()
                if not product:
                    raise ValueError(f"Product SKU {item['sku_id']} missing during finalization.")

                # STRICT OVERSELL GUARD ENFORCEMENT
                if product["quantity"] < item["qty"]:
                    return {
                        "status": "error",
                        "error_type": "OversellGuardError",
                        "message": f"Oversell Guard Triggered: Cannot sell {item['qty']} units of '{product['name']}'. Current stock is only {product['quantity']}."
                    }

                # Stash pre-decrement state for audit trail
                item_stock_before[item["sku_id"]] = {"qty": product["quantity"], "name": product["name"]}

                # Calculate Tax
                line_subtotal = item["qty"] * item["unit_price"]
                gst_info = _calculate_gst(line_subtotal, item["gst_slab"])
                subtotal += gst_info["subtotal"]
                cgst_total += gst_info["cgst"]
                sgst_total += gst_info["sgst"]

            grand_total = round(subtotal + cgst_total + sgst_total, 2)

            # 3. Handle Khata validation if payment mode is Khata
            if payment_mode == "khata":
                if not bill["customer_id"]:
                    return {
                        "status": "error",
                        "error_type": "KhataCustomerRequired",
                        "message": "Cannot finalize bill with payment mode 'khata' without an associated customer."
                    }
                cur = conn.execute("SELECT * FROM customers WHERE customer_id = ?", (bill["customer_id"],))
                cust = cur.fetchone()
                if not cust:
                    return {"status": "error", "message": "Khata customer not found in customer ledger."}

            # 4. Decrement Stock
            for item in items:
                conn.execute("""
                    UPDATE products
                    SET quantity = quantity - ?
                    WHERE sku_id = ?
                """, (item["qty"], item["sku_id"]))

                before = item_stock_before[item["sku_id"]]
                _log_event(conn, "STOCK_DECREMENTED", "product", item["sku_id"],
                           details={"product_name": before["name"], "bill_id": bill_id.strip(),
                                    "qty_sold": item["qty"]},
                           old_value=before["qty"], new_value=before["qty"] - item["qty"])

            # 5. Record Khata Transaction if applicable
            if payment_mode == "khata":
                conn.execute("""
                    INSERT INTO khata_transactions (customer_id, type, amount, bill_id)
                    VALUES (?, 'charge', ?, ?)
                """, (bill["customer_id"], grand_total, bill_id.strip()))

                conn.execute("""
                    UPDATE customers
                    SET khata_balance = khata_balance + ?
                    WHERE customer_id = ?
                """, (grand_total, bill["customer_id"]))

                _log_event(conn, "KHATA_CHARGED", "customer", cust["name"],
                           details={"amount": grand_total, "bill_id": bill_id.strip()},
                           old_value=cust["khata_balance"],
                           new_value=cust["khata_balance"] + grand_total)

            # 6. Update Bill Status to Finalized
            conn.execute("""
                UPDATE bills
                SET status = 'finalized',
                    payment_mode = ?,
                    payment_ref = ?,
                    subtotal = ?,
                    cgst = ?,
                    sgst = ?,
                    total = ?,
                    finalized_at = CURRENT_TIMESTAMP
                WHERE bill_id = ?
            """, (payment_mode, payment_ref, round(subtotal, 2), round(cgst_total, 2), round(sgst_total, 2), grand_total, bill_id.strip()))

            # 7. Log Idempotency
            if idempotency_key:
                conn.execute("""
                    INSERT OR IGNORE INTO idempotency_log (update_id)
                    VALUES (?)
                """, (str(idempotency_key),))

            customer_name = None
            if bill["customer_id"]:
                cur = conn.execute("SELECT name FROM customers WHERE customer_id = ?", (bill["customer_id"],))
                cust_row = cur.fetchone()
                customer_name = cust_row["name"] if cust_row else None
            _log_event(conn, "BILL_FINALIZED", "bill", bill_id,
                       details={"payment_mode": payment_mode, "grand_total": grand_total,
                                "customer_name": customer_name})

        # Return finalized bill summary
        final_preview = preview_bill(bill_id)
        final_preview["message"] = f"Bill {bill_id} finalized successfully! Total: ₹{grand_total} ({payment_mode.upper()})."
        return final_preview

    finally:
        conn.close()

def quick_create_bill(
    items: List[Dict[str, Any]],
    customer_name: Optional[str] = None,
    payment_mode: Optional[str] = None,
    idempotency_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    ⚡ ULTRAFALL/ULTRAFAST Single-Turn Billing Tool:
    Creates draft bill, adds all items (name/sku & qty), and optionally finalizes in 1 single call!
    
    `items` format: [{"name": "sugar", "qty": 2}, {"name": "Maggi", "qty": 4}]
    `payment_mode`: Optional "upi", "cash", "card", or "khata". If omitted, leaves bill as draft.
    """
    # 1. Start bill
    start_res = start_bill(customer_name=customer_name)
    if start_res.get("status") != "success":
        return start_res
        
    bill_id = start_res["bill_id"]
    added_summary = []
    warnings = []
    
    # 2. Add all items
    for item in items:
        name = item.get("name") or item.get("sku_or_name") or item.get("sku")
        qty = float(item.get("qty", 1))
        if not name:
            continue
        res = add_item_to_bill(bill_id=bill_id, sku_or_name=name, qty=qty)
        if res.get("status") == "success":
            added_summary.append(f"{qty} {res.get('product_name')}")
        elif res.get("status") == "oversell_warning":
            warnings.append(res.get("message"))
        else:
            warnings.append(f"Failed to add '{name}': {res.get('message')}")

    # 3. Finalize if payment mode provided
    if payment_mode:
        fin_res = finalize_bill(bill_id=bill_id, payment_mode=payment_mode, idempotency_key=idempotency_key)
        if warnings:
            fin_res["warnings"] = warnings
        return fin_res
    else:
        preview = preview_bill(bill_id=bill_id)
        if warnings:
            preview["warnings"] = warnings
        return preview

