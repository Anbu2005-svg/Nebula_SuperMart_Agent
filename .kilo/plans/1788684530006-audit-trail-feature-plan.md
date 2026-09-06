# Plan: Add Full Audit Trail (Event Log + Query Tool)

## Goal

Add a production-grade audit trail to the Supermarket Ops Agent: a new `audit_log` SQLite table recording every important business operation with before/after values, written atomically inside each mutating tool's existing transaction, plus a new 23rd agent tool `get_audit_trail` so the agent can answer questions like "Why did today's Maggi stock decrease?" from real records.

**No behavior changes to existing tools** — only additive INSERT statements inside existing transactions, one new module, one new tool registration.

## Context (verified in code)

- `db/schema.sql` uses `CREATE TABLE IF NOT EXISTS`; `bot.py` calls `seed_database()` on startup which re-runs `init_db()` → the new table will be auto-created on the existing `supermarket.db` with zero migration.
- Every mutating tool already wraps its writes in `with immediate_transaction(conn)` (`skills/billing.py`, `skills/inventory.py`, `skills/credit.py`, `skills/preferences.py`). Logging inside these blocks inherits atomicity: if the transaction rolls back (exception), the log entry rolls back too.
- Guard-path early `return`s inside `with immediate_transaction(...)` blocks commit an empty transaction — safe: no mutation happened, so no log should be written on those paths.
- `agent/harness.py` holds `TOOL_DISPATCH` (22 entries) + `TOOLS_SCHEMA` (22 schemas). `tests/test_docgen_and_harness.py::test_groq_tool_dispatch_completeness` asserts `len(schema_names) == 22` and must be bumped to 23.
- README states "22 AI tools" (line ~49) and "29 automated tests" (two places) — counts must be updated.

## Design Decisions (resolved)

1. **Scope:** Full — log table + event writes in all 10 mutating tools + `get_audit_trail` as the 23rd agent tool. No new Telegram slash command (agent tool only; strategy says don't invest in UI).
2. **Atomicity:** `_log_event()` receives the caller's open connection and is called inside the caller's `immediate_transaction` block, so audit rows commit or roll back with the business operation.
3. **No logs for:** read-only tools, guard rejections (oversell warning, invalid payment mode, CustomerNotFound, cost>MRP) — only successful mutations.
4. **Queryability:** `entity_id` (SKU / bill_id / customer name) and a JSON `details` string are both matched via LIKE in the query tool, so the agent can filter by either "SKU-MAGGI-70", "Maggi", or "BILL-12345678".

## Event Catalog

| event_type | Trigger (file) | entity_type / entity_id | old_value → new_value | details JSON keys |
|---|---|---|---|---|
| `BILL_CREATED` | `billing.start_bill` | bill / bill_id | — | customer_name |
| `ITEM_ADDED` | `billing.add_item_to_bill` (success path only) | bill / bill_id | — | product_name, sku_id, qty, unit_price |
| `ITEM_REMOVED` | `billing.remove_item_from_bill` | bill / bill_id | — | product_name, sku_id |
| `ITEM_QTY_UPDATED` | `billing.edit_item_qty` | bill / bill_id | old_qty → new_qty | product_name, sku_id |
| `STOCK_DECREMENTED` | `billing.finalize_bill` (per item, after UPDATE products) | product / sku_id | qty_before → qty_after | product_name, bill_id, qty_sold |
| `BILL_FINALIZED` | `billing.finalize_bill` (after bills UPDATE) | bill / bill_id | — | payment_mode, grand_total, customer_name |
| `STOCK_RECEIVED` | `inventory.receive_stock` | product / sku_id | qty_before → qty_after | product_name, qty_received, cost_price, mrp |
| `PRODUCT_ADDED` | `inventory.add_product` | product / sku_id | 0 → quantity | name, category, mrp, gst_slab |
| `KHATA_CHARGED` | `credit.charge_khata` AND `billing.finalize_bill` khata path | customer / customer name | balance_before → balance_after | amount, bill_id (nullable) |
| `KHATA_PAYMENT_RECORDED` | `credit.record_payment` | customer / customer name | balance_before → balance_after | amount |
| `PREFERENCE_SET` | `preferences.set_preference` | owner / owner_id | — | key, value |

## Task List (ordered)

### 1. `db/schema.sql` — add table

```sql
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    details TEXT,                    -- JSON string
    old_value REAL,
    new_value REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_event ON audit_log(event_type);
```

### 2. New file `skills/audit.py`

```python
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
    # SELECT ... WHERE (entity_id LIKE ? OR details LIKE ?) AND event_type LIKE ?
    # ORDER BY created_at DESC, id DESC LIMIT ?
    # Return {"status": "success", "count": n, "events": [...]} with details parsed back to dict.
```

- Clamp `limit` to [1, 100].
- No circular imports: `audit` imports only `db.models`; the skill modules import `_log_event` from `skills.audit` (one-way).

### 3. `skills/billing.py` — instrument 5 functions

Insert `_log_event(...)` calls inside each existing `with immediate_transaction(conn)` block, **only on success paths** (after the INSERT/UPDATE, before the block ends):

- `start_bill`: `BILL_CREATED` (details: customer_name) after the bills INSERT.
- `add_item_to_bill`: `ITEM_ADDED` (details: product_name, sku_id, qty, unit_price) after both the existing-item UPDATE branch and the new-item INSERT branch (single call after the if/else, using `new_qty`/`qty` appropriately — keep it simple: log after the if/else using the effective quantity).
- `remove_item_from_bill`: `ITEM_REMOVED` after the DELETE.
- `edit_item_qty`: `ITEM_QTY_UPDATED` with `old_value=existing qty` (must SELECT the current row first), `new_value=new_qty`.
- `finalize_bill`: during the validation loop, capture each product's pre-decrement `quantity` (it is already fetched there — stash `old_qty` per sku). Then inside the same transaction, after the stock UPDATE loop: one `STOCK_DECREMENTED` per item (old_value→old_qty − item qty). After the khata inserts (if mode == khata): `KHATA_CHARGED` (old_value=cust["khata_balance"] captured earlier, new_value=old+grand_total). After the bills UPDATE: `BILL_FINALIZED` (details: payment_mode, grand_total, customer_name).
- **Do not** log on oversell-guard, invalid-payment, empty-bill, voided, or already-finalized early returns.

### 4. `skills/inventory.py` — instrument 2 functions

- `receive_stock`: `STOCK_RECEIVED` with old_value=product["quantity"] (fetched earlier), new_value=new_qty (details: product_name, qty_received, cost_price, mrp).
- `add_product`: `PRODUCT_ADDED` (old_value=0, new_value=quantity).

### 5. `skills/credit.py` — instrument 2 functions

- `charge_khata`: `KHATA_CHARGED`, old_value=customer["khata_balance"] (from initial fetch), new_value=new_balance (read after UPDATE).
- `record_payment`: `KHATA_PAYMENT_RECORDED`, same pattern (new_value=new_balance).

### 6. `skills/preferences.py` — instrument 1 function

- `set_preference`: `PREFERENCE_SET` (entity_type "owner", entity_id owner_id, details: key, value) inside the existing transaction.

### 7. `agent/harness.py` — register the 23rd tool

- Add `"get_audit_trail": audit.get_audit_trail` to `TOOL_DISPATCH` and import `audit` in the skills import line.
- Add the matching entry to `TOOLS_SCHEMA`:

```python
{
  "type": "function",
  "function": {
    "name": "get_audit_trail",
    "description": "Query the audit trail of past store operations (stock changes, bills, khata, preferences) to answer questions like 'why did Maggi stock decrease today?'. Optionally filter by entity (product/SKU/bill/customer) and/or event type.",
    "parameters": {
      "type": "object",
      "properties": {
        "query": {"type": "string", "description": "Optional filter: product name, SKU, bill ID, or customer name"},
        "event_type": {"type": "string", "description": "Optional event type filter, e.g. STOCK_DECREMENTED"},
        "limit": {"type": "number", "description": "Max events to return (default 20)"}
      }
    }
  }
}
```

- Append one line to `SYSTEM_PROMPT`: `9. Audit Trail: To answer questions about past operations or stock changes (e.g. "why did Maggi stock drop?"), call get_audit_trail with the product or bill as the query filter.` (renumber if needed).

### 8. New file `tests/test_audit_trail.py` (5 tests)

Follow the existing fixture pattern (per-file TEST_DB, monkeypatch `db.models.DEFAULT_DB_PATH`, seed, cleanup):

1. `test_audit_logs_bill_lifecycle` — start_bill → add 2 items → edit qty → remove item → finalize cash. Assert ordered event sequence contains BILL_CREATED, ITEM_ADDED ×2, ITEM_QTY_UPDATED, ITEM_REMOVED, STOCK_DECREMENTED (with correct old→new values), BILL_FINALIZED; assert no events reference the removed item's decrement.
2. `test_audit_no_log_on_oversell_rejection` — attempt `add_item_to_bill` with qty > stock and a finalize on a drained SKU; assert zero STOCK_DECREMENTED / ITEM_ADDED events exist for that bill.
3. `test_audit_logs_stock_receipt_and_product` — `receive_stock` (assert STOCK_RECEIVED old→new) and `add_product` (assert PRODUCT_ADDED).
4. `test_audit_logs_khata_events` — charge → payment; assert KHATA_CHARGED and KHATA_PAYMENT_RECORDED with correct balance transitions. Include one `finalize_bill(payment_mode="khata")` to assert the finalize-path KHATA_CHARGED event.
5. `test_get_audit_trail_filtering` — call `get_audit_trail(query="Maggi", event_type="STOCK_DECREMENTED")` after a Maggi sale; assert only Maggi decrement events return; also test empty-result shape and `limit` clamping.

### 9. Update existing count assertions and docs

- `tests/test_docgen_and_harness.py::test_groq_tool_dispatch_completeness`: `assert len(schema_names) == 22` → `23`.
- `README.md`: update "22 AI tools" → 23; "29 automated tests" → 34 (two places: section header + intro bullet); add an **Audit Trail (`skills/audit.py`)** bullet under the tools section listing `get_audit_trail(query, event_type, limit)`; optionally add a short "Audit Trail" line to the hard-requirements section noting every mutation is logged with before/after values inside the same DB transaction.

## Validation

1. `python -m pytest tests/ -v` — expect **34 passed** (29 existing + 5 new), 0 failures.
2. Manual smoke (optional, read-only spirit): after running tests against a scratch DB, confirm `audit_log` table populates in `supermarket.db` on next `python bot.py` start (schema auto-applies) and a chat message like "why did Maggi stock decrease?" triggers `get_audit_trail` via the agent loop.
3. Confirm no existing test broke — especially the tool-dispatch completeness test and the idempotency test (finalize now writes audit rows inside the same transaction; the duplicate-finalize path returns `preview_bill` before the transaction, so no double audit rows).

## Risks / Edge Cases

- **Early-return-inside-transaction commits are empty** — verified safe; no orphan logs.
- **`details` JSON with non-serializable values** — use `json.dumps(..., default=str)` (already the pattern in `control_loop.py`).
- **Old-value capture**: `edit_item_qty`, `finalize_bill`, `charge_khata`, `record_payment` must SELECT/capture the pre-mutation value before the UPDATE — insertion points documented in task 3–5.
- **Audit rows inside finalize's transaction** strengthen the atomicity demo (stock decrement + payment + audit all commit together) — highlight this in the demo recording.
- **No perf concern**: single-row INSERTs on an indexed table, same transaction already held.

## Out of Scope

- Telegram `/audit` slash command (agent tool suffices).
- Audit-trail retention/purge policies.
- Logging read-only operations (get_stock, preview_bill, analytics) — would pollute the trail.
- Any changes to oversell/ concurrency / idempotency logic itself.
