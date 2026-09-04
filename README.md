# Supermarket Ops Agent 🛒🤖

> **Nebula KnowLab Hiring Task**  
> An intelligent, autonomous Telegram AI Operations Agent for Indian Supermarkets built with **100% Free & Open-Source Tools**.

---

## 📌 Telegram Bot Handle & Demo Quickstart
- **Telegram Bot Handle:** `@YourBotHandle` (Run locally or deploy via polling)
- **Repo Structure:** Clean modular python app (`skills/`, `agent/`, `db/`, `docgen/`, `tests/`)

### Setup & Running Locally
```bash
# 1. Clone repository & enter workspace
cd "SuperMarket ops Agent"

# 2. Activate virtual environment
.\venv\Scripts\activate   # Windows

# 3. Copy .env.example and configure keys
cp .env.example .env
# Set TELEGRAM_BOT_TOKEN and GROQ_API_KEY in .env

# 4. Seed database with Indian supermarket catalog
python -m db.seed

# 5. Run tests
pytest tests/ -v

# 6. Launch Telegram Bot
python bot.py
```

---

## 🏗️ Technical Architecture & Tech Stack

| Layer | Technology Choice | Rationale |
|---|---|---|
| **LLM & Agent Engine** | **Groq API** (`llama-3.3-70b-versatile`) | **100% Free** (No credit card required), ultra-low latency inference, standard OpenAI-compatible function calling. |
| **Bot Interface** | **python-telegram-bot** (v21+, Async) | Mature Python Telegram framework supporting polling & webhooks. |
| **Database & Concurrency** | **SQLite** (`sqlite3` with WAL mode) | Zero external dependencies, single file durability, `BEGIN IMMEDIATE` write-lock transactions for concurrency safety. |
| **PDF Tax Invoices** | **ReportLab** | Pure Python PDF layout engine, generating branded PDF invoices with GST breakdowns. |
| **PowerPoint Analytics** | **python-pptx** + **matplotlib** | Generates real PowerPoint `.pptx` decks with embedded charts. |

---

## ⚙️ Control Loop Architecture

```
Telegram Message Arrives (update_id)
        │
        ▼
 Check idempotency_log (Skip if update_id already processed)
        │
        ▼
 Load Owner Preferences from DB → Inject into System Prompt
        │
        ▼
 Groq Agent Multi-Step Tool Call Loop
 ┌─────────────────────────────────────────────────────────────┐
 │ 1. Send conversation history + tool definitions to Groq      │
 │ 2. Model decides to call Tool A (e.g. get_stock)            │
 │ 3. Code executes tool function locally                       │
 │ 4. Append tool result JSON to messages context              │
 │ 5. Repeat until model outputs final text response            │
 └─────────────────────────────────────────────────────────────┘
        │
        ▼
 Deliver Final Response & Attach PDF/PPTX Artifacts to Telegram
        │
        ▼
 Record update_id in idempotency_log
```

---

## 🛠️ Skills & Tools Organization

Tools are modularized cleanly inside `/skills`:

- **Inventory (`skills/inventory.py`):**
  - `get_stock(query)` — Stock level, MRP, GST slab.
  - `receive_stock(sku_id, qty, cost_price, mrp)` — Stock replenishment.
  - `add_product(...)` — New product catalog creation.
  - `list_low_stock()` — Low inventory alerts.
- **Billing (`skills/billing.py`):**
  - `start_bill(customer_name)` — Create draft `bill_id`.
  - `add_item_to_bill(bill_id, sku_or_name, qty)` — Soft stock check & add item.
  - `remove_item_from_bill(bill_id, sku_or_name)` — Remove line item.
  - `edit_item_qty(bill_id, sku_or_name, new_qty)` — Edit draft quantity.
  - `preview_bill(bill_id)` — Preview tax & total.
  - `finalize_bill(bill_id, payment_mode)` — Atomic stock decrement & sale commit.
- **Credit / Khata (`skills/credit.py`):**
  - `charge_khata(customer_name, amount, bill_id)` — Charge customer credit.
  - `record_payment(customer_name, amount)` — Record credit repayment.
  - `get_khata_balance(customer_name)` — Balance & history lookup.
- **Analytics (`skills/analytics.py`):**
  - `daily_summary(date_str)` — Sales, GST, payment mode breakdown.
  - `close_day(date_str)` — Day-close summary.
- **Document Generation (`skills/documents.py`):**
  - `generate_invoice_pdf(bill_id)` — PDF tax invoice builder.
  - `generate_analysis_deck(period)` — PowerPoint presentation builder.
- **Preferences (`skills/preferences.py`):**
  - `set_preference(key, value)` — Persist owner settings.
  - `get_preference(key)` — Fetch standing owner settings.

---

## 💡 How the 9 "Hard Parts" Were Solved

### 1. Grounding & Zero Hallucination
Tools are the **sole source of truth** for pricing, stock quantities, and customer balances. The system prompt instructs the agent never to guess prices or inventory levels; all queries route through `get_stock` or `preview_bill`.

### 2. Oversell Guard Enforcement
Enforced in Python code (`skills/billing.py`) inside `finalize_bill()` within an atomic transaction. If requested `qty > current_stock`, the tool raises an `OversellGuardError`. The LLM receives this error and relays a refusal message to the user.

### 3. GST Calculation Correctness
Deterministic pure function `_calculate_gst()`:
$$\text{GST Amount} = \text{Subtotal} \times \frac{\text{GST Slab}}{100}$$
$$\text{CGST} = \text{SGST} = \frac{\text{GST Amount}}{2}$$
Rounded per line to 2 decimal places. Verified in `tests/test_gst_calc.py`.

### 4. Multi-turn Bills
Bills are maintained in a `bills` table with `status='draft'`. Line items can be added, updated, or removed across multiple turns before the user calls `finalize_bill`.

### 5. Idempotency & Retried Updates
Every Telegram update carries a unique `update_id`. Before processing, `control_loop.py` checks `idempotency_log`. Retried updates return the previous result without double-billing or double-decrementing stock.

### 6. Concurrency Safety
SQLite write transactions wrap stock mutations using `BEGIN IMMEDIATE`. This acquires an immediate write lock on the database, serializing concurrent requests and preventing race conditions.

### 7. Guardrails in Code
Business rules (e.g. no selling below cost price, refusing credit repayments for non-existent customers) are enforced in tool code. Typed errors are returned as JSON to the LLM.

### 8. Real PDF & PPTX Artifacts
- **PDF Invoice:** Built via `reportlab` (`docgen/invoice_template.py`), featuring shop headers, itemized HSN/GST tables, and totals.
- **PPTX Deck:** Built via `python-pptx` and `matplotlib` (`docgen/deck_builder.py`), creating visual slide decks with sales and category pie/bar charts.

### 9. Persistent Memory Across Sessions
Owner preferences (e.g. `default_payment_mode=UPI`, `shop_name=Anbu SuperMart`) are saved in the `preferences` table. They are injected into the agent's system context on every turn and persist even when `/new` clears session memory.

---

## 🧪 Testing Suite

Run full automated tests:
```bash
pytest tests/ -v
```

Tests include:
- `tests/test_gst_calc.py` — GST slab math & rounding.
- `tests/test_oversell.py` — Stock oversell guard & decrementing.
- `tests/test_idempotency.py` — Duplicate Telegram update handling.
- `tests/test_agent_flow.py` — End-to-end billing, PDF generation, Khata lifecycle, and PPTX decks.
