from datetime import date
from typing import Dict, Any, Optional
from db.models import get_db_connection


def daily_summary(date_str: Optional[str] = None) -> Dict[str, Any]:
    """
    Generate daily sales summary report for a given date (YYYY-MM-DD).
    Defaults to current date if omitted.
    """
    if date_str:
        try:
            from datetime import datetime
            parsed_date = datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
            target_date = parsed_date.isoformat()
        except ValueError:
            return {"status": "error", "message": f"Invalid date format '{date_str}'. Expected format is YYYY-MM-DD (e.g. 2026-09-12)."}
    else:
        target_date = date.today().isoformat()

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        # Finalized bills on date (PostgreSQL DATE() equivalent)
        cur.execute("""
            SELECT * FROM bills
            WHERE status = 'finalized' AND finalized_at::date = %s::date
        """, (target_date,))
        bills = cur.fetchall()

        total_bills = len(bills)
        total_sales = sum(b["total"] for b in bills)
        subtotal_sales = sum(b["subtotal"] for b in bills)
        cgst_collected = sum(b["cgst"] for b in bills)
        sgst_collected = sum(b["sgst"] for b in bills)
        total_tax_collected = cgst_collected + sgst_collected

        # Payment Mode Breakdown
        payment_breakdown = {"cash": 0.0, "upi": 0.0, "card": 0.0, "khata": 0.0}
        for b in bills:
            pm = b["payment_mode"] or "other"
            if pm in payment_breakdown:
                payment_breakdown[pm] += b["total"]

        # Top 5 items sold
        cur.execute("""
            SELECT p.name, SUM(bi.qty) as total_qty, p.unit, SUM(bi.line_total) as item_revenue
            FROM bill_items bi
            JOIN bills b ON bi.bill_id = b.bill_id
            JOIN products p ON bi.sku_id = p.sku_id
            WHERE b.status = 'finalized' AND b.finalized_at::date = %s::date
            GROUP BY bi.sku_id, p.name, p.unit
            ORDER BY total_qty DESC
            LIMIT 5
        """, (target_date,))
        top_items = cur.fetchall()
        cur.close()

        items_summary = [{
            "name": row["name"],
            "total_qty": row["total_qty"],
            "unit": row["unit"],
            "revenue": row["item_revenue"]
        } for row in top_items]

        return {
            "status": "success",
            "date": target_date,
            "total_bills": total_bills,
            "total_sales": round(total_sales, 2),
            "subtotal": round(subtotal_sales, 2),
            "total_tax_collected": round(total_tax_collected, 2),
            "cgst_collected": round(cgst_collected, 2),
            "sgst_collected": round(sgst_collected, 2),
            "payment_breakdown": {k: round(v, 2) for k, v in payment_breakdown.items()},
            "top_selling_items": items_summary
        }
    finally:
        conn.close()


def close_day(date_str: Optional[str] = None) -> Dict[str, Any]:
    """Close out supermarket operations for the day and return closed daily report."""
    summary = daily_summary(date_str)
    summary["message"] = f"Day {summary['date']} operations closed successfully. Total Revenue: \u20b9{summary['total_sales']:.2f}"
    summary["is_closed"] = True
    return summary
