import json
from typing import Dict, Any, Optional
from db.models import get_db_connection

def _log_event(conn, event_type, entity_type, entity_id, details=None,
               old_value=None, new_value=None):
    """Insert an audit row using the CALLER'S open connection/transaction.
    Must be called inside the caller's immediate_transaction block."""
    conn.execute(
        "INSERT INTO audit_log (event_type, entity_type, entity_id, details, old_value, new_value) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (event_type, entity_type, str(entity_id) if entity_id else None,
         json.dumps(details, default=str) if details else None, old_value, new_value))

def get_audit_trail(query: Optional[str] = None, event_type: Optional[str] = None, limit: int = 20) -> Dict[str, Any]:
    """Agent tool: query recent audit events, optionally filtered by entity
    (product name/SKU/bill_id/customer) and/or event_type."""
    limit = max(1, min(100, int(limit)))

    sql = "SELECT * FROM audit_log"
    params: list = []
    conditions = []

    if query:
        conditions.append("(entity_id LIKE ? OR details LIKE ?)")
        like = f"%{query.strip()}%"
        params.extend([like, like])
    if event_type:
        conditions.append("event_type LIKE ?")
        params.append(f"%{event_type.strip()}%")

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
    params.append(limit)

    conn = get_db_connection()
    try:
        cur = conn.execute(sql, params)
        rows = cur.fetchall()

        events = []
        for r in rows:
            try:
                details = json.loads(r["details"]) if r["details"] else None
            except (ValueError, TypeError):
                details = r["details"]
            events.append({
                "id": r["id"],
                "event_type": r["event_type"],
                "entity_type": r["entity_type"],
                "entity_id": r["entity_id"],
                "details": details,
                "old_value": r["old_value"],
                "new_value": r["new_value"],
                "created_at": r["created_at"]
            })

        return {"status": "success", "count": len(events), "events": events}
    finally:
        conn.close()
