from typing import Dict, Any, List, Optional
from db.models import get_db_connection, immediate_transaction
from skills.audit import _log_event

def _get_customer_by_name(conn, name: str) -> Optional[Any]:
    cur = conn.execute("SELECT * FROM customers WHERE name LIKE ?", (f"%{name.strip()}%",))
    return cur.fetchone()

def charge_khata(customer_name: str, amount: float, bill_id: Optional[str] = None) -> Dict[str, Any]:
    """Add a credit charge to a customer's khata ledger."""
    if amount <= 0:
        return {"status": "error", "message": "Charge amount must be positive."}
        
    conn = get_db_connection()
    try:
        customer = _get_customer_by_name(conn, customer_name)
        if not customer:
            return {
                "status": "error",
                "error_type": "CustomerNotFound",
                "message": f"Customer '{customer_name}' not found in credit ledger. Create customer record first or check spelling."
            }
            
        cid = customer["customer_id"]
        with immediate_transaction(conn):
            conn.execute("""
                INSERT INTO khata_transactions (customer_id, type, amount, bill_id)
                VALUES (?, 'charge', ?, ?)
            """, (cid, amount, bill_id))
            
            conn.execute("""
                UPDATE customers
                SET khata_balance = khata_balance + ?
                WHERE customer_id = ?
            """, (amount, cid))
            
            cur = conn.execute("SELECT khata_balance FROM customers WHERE customer_id = ?", (cid,))
            new_balance = cur.fetchone()["khata_balance"]

            _log_event(conn, "KHATA_CHARGED", "customer", customer["name"],
                       details={"amount": amount, "bill_id": bill_id},
                       old_value=customer["khata_balance"], new_value=new_balance)

        return {
            "status": "success",
            "message": f"Charged ₹{amount:.2f} to {customer['name']}'s khata. New balance: ₹{new_balance:.2f}",
            "customer_name": customer["name"],
            "charged_amount": amount,
            "new_balance": new_balance
        }
    finally:
        conn.close()

def record_payment(customer_name: str, amount: float) -> Dict[str, Any]:
    """Record a credit repayment from a customer to reduce their khata balance."""
    if amount <= 0:
        return {"status": "error", "message": "Payment amount must be positive."}
        
    conn = get_db_connection()
    try:
        customer = _get_customer_by_name(conn, customer_name)
        if not customer:
            return {
                "status": "error",
                "error_type": "CustomerNotFound",
                "message": f"Customer '{customer_name}' not found in credit ledger. Cannot record payment for non-existent customer."
            }
            
        cid = customer["customer_id"]
        with immediate_transaction(conn):
            conn.execute("""
                INSERT INTO khata_transactions (customer_id, type, amount)
                VALUES (?, 'payment', ?)
            """, (cid, amount))
            
            conn.execute("""
                UPDATE customers
                SET khata_balance = khata_balance - ?
                WHERE customer_id = ?
            """, (amount, cid))
            
            cur = conn.execute("SELECT khata_balance FROM customers WHERE customer_id = ?", (cid,))
            new_balance = cur.fetchone()["khata_balance"]

            _log_event(conn, "KHATA_PAYMENT_RECORDED", "customer", customer["name"],
                       details={"amount": amount},
                       old_value=customer["khata_balance"], new_value=new_balance)

        return {
            "status": "success",
            "message": f"Recorded payment of ₹{amount:.2f} from {customer['name']}. Remaining khata balance: ₹{new_balance:.2f}",
            "customer_name": customer["name"],
            "payment_amount": amount,
            "new_balance": new_balance
        }
    finally:
        conn.close()

def get_khata_balance(customer_name: str) -> Dict[str, Any]:
    """Get current credit (khata) balance and transaction history for a customer."""
    conn = get_db_connection()
    try:
        customer = _get_customer_by_name(conn, customer_name)
        if not customer:
            return {
                "status": "error",
                "error_type": "CustomerNotFound",
                "message": f"Customer '{customer_name}' not found in credit ledger."
            }
            
        cid = customer["customer_id"]
        cur = conn.execute("""
            SELECT * FROM khata_transactions 
            WHERE customer_id = ? 
            ORDER BY created_at DESC 
            LIMIT 10
        """, (cid,))
        txs = cur.fetchall()
        
        history = [{
            "id": tx["id"],
            "type": tx["type"],
            "amount": tx["amount"],
            "bill_id": tx["bill_id"],
            "created_at": tx["created_at"]
        } for tx in txs]
        
        return {
            "status": "success",
            "customer_name": customer["name"],
            "khata_balance": customer["khata_balance"],
            "recent_transactions": history
        }
    finally:
        conn.close()

def list_all_khata() -> Dict[str, Any]:
    """List all customers with non-zero khata balance."""
    conn = get_db_connection()
    try:
        cur = conn.execute("SELECT * FROM customers WHERE khata_balance != 0 ORDER BY khata_balance DESC")
        customers = cur.fetchall()
        
        items = [{
            "customer_id": c["customer_id"],
            "name": c["name"],
            "khata_balance": c["khata_balance"]
        } for c in customers]
        
        return {
            "status": "success",
            "count": len(items),
            "khata_ledger": items
        }
    finally:
        conn.close()
