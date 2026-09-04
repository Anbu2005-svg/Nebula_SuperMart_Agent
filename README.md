# Nebula SuperMart AI Ops Agent 🛒🤖

> **Supermarket Operations AI Agent**  
> An intelligent, autonomous Telegram AI Operations Agent for Indian Supermarkets built with **100% Free & Open-Source Tools**.

---

## 📌 Project Overview & GitHub Details
* **GitHub Repository:** [https://github.com/Anbu2005-svg/Nebula_SuperMart_Agent](https://github.com/Anbu2005-svg/Nebula_SuperMart_Agent)
* **Contributor / Author:** `Anbu2005-svg` (`anbanand44@gmail.com`)
* **Core Stack:** Python 3.9+, Telegram Bot API (`python-telegram-bot`), Groq LLM API (`qwen/qwen3.8-27b`), SQLite3 (WAL Mode), ReportLab (PDF), python-pptx (PPTX), pytest.

---

## 🚀 Quickstart & Setup Guide

### 1. Clone & Set Up Virtual Environment
```bash
# Clone repository
git clone https://github.com/Anbu2005-svg/Nebula_SuperMart_Agent.git
cd Nebula_SuperMart_Agent

# Create and activate virtual environment
python -m venv venv
.\venv\Scripts\activate   # Windows (or source venv/bin/activate on Linux/macOS)

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env` and fill in your API tokens:
```bash
cp .env.example .env
```
Ensure your `.env` contains:
```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=qwen/qwen3.8-27b
DB_PATH=supermarket.db
SHOP_NAME=Nebula SuperMart
SHOP_ADDRESS=123 Main Street, Chennai, TN - 600001
SHOP_GSTIN=33AABCU9603R1ZM
REQUIRE_AUTH=false
```

### 3. Initialize Database & Run Tests
```bash
# Seed SQLite database with the 10 initial supermarket products & sample customers
python -m db.seed

# Run the complete 24-test automated test suite
pytest tests/ -v
```

### 4. Launch Telegram Bot
```bash
python bot.py
```

---

## 📱 Telegram Bot Commands & Interactive Menu

The bot automatically registers an interactive command menu with Telegram using `set_my_commands`:

| Command | Description |
|---|---|
| `/start` | Start bot session & verify mobile contact |
| `/new` | Reset conversation context (standing preferences persist) |
| `/invoice <bill_id>` | Download official PDF GST Tax Invoice for a bill |
| `/analysis <period>` | Download PowerPoint (.pptx) operations & sales analysis deck |
| `/help` | Display interactive command menu and usage guide |
| `/logout` | De-authenticate current user session |

---

## 📦 Initial 10-Product Inventory Dataset

The database seed script (`db/seed.py`) pre-populates the catalog with the exact initial dataset specified in the project problem statement:

| # | Product Name | Category | Stock | Unit | MRP | GST |
|---|---|---|---|---|---|---|
| 1 | Brooke Bond Red Label Tea 250g | Beverages | 15 | packet | ₹140 | 5% |
| 2 | Amul Pasteurised Butter 500g | Dairy | 20 | packet | ₹275 | 12% |
| 3 | Amul Taaza Toned Milk 1L | Dairy | 25 | packet | ₹56 | 0% |
| 4 | Fortune Sunlite Sunflower Oil 1L | Edible Oils | 40 | litre | ₹155 | 5% |
| 5 | Aashirvaad Whole Wheat Atta 10kg | Grains & Flour | 30 | packet | ₹440 | 5% |
| 6 | India Gate Basmati Rice Feast Rozzana 5kg | Grains & Flour | 12 | packet | ₹475 | 5% |
| 7 | Refined White Sugar 1kg | Pantry Basics | 60 | kg | ₹48 | 5% |
| 8 | Tata Iodized Salt 1kg | Pantry Basics | 50 | packet | ₹28 | 0% |
| 9 | Dettol Original Bathing Soap 125g | Personal Care | 40 | piece | ₹48 | 18% |
| 10 | Maggi 2-Minute Instant Noodles 70g | Snacks & Packaged Food | 100 | packet | ₹14 | 18% |

> 💡 **Clean Inventory Formatting:** When asked for stock, the agent presents items in structured, category-grouped cards with emojis, prices, and stock badges instead of raw database tables.

---

## 🏗️ Technical Architecture & Tech Stack

```
Telegram User Input (update_id)
        │
        ▼
 Check Idempotency Log (Skip if update_id already processed)
        │
        ▼
 Load Owner Standing Preferences → Inject into Agent System Context
        │
        ▼
 Groq Agent Multi-Tool Control Loop (qwen/qwen3.8-27b)
 ┌─────────────────────────────────────────────────────────────┐
 │ 1. Send conversation history + tool schemas to Groq LLM      │
 │ 2. Model decides tool execution (e.g. add_item_to_bill)    │
 │ 3. Python code executes tool function against SQLite DB     │
 │ 4. Append tool result JSON back to LLM context             │
 │ 5. Repeat until model completes response text               │
 └─────────────────────────────────────────────────────────────┘
        │
        ▼
 Deliver Response Text & PDF / PPTX Files to Telegram User
```

---

## 🛠️ Modular Skills & Tools Structure

Tools are organized cleanly inside `/skills`:

* **Inventory (`skills/inventory.py`):**
  * `get_stock(query)` — Stock level, MRP, unit, GST slab lookup.
  * `receive_stock(sku_id, qty, cost_price, mrp)` — Receive wholesale stock shipments.
  * `add_product(name, category, unit, is_loose, cost_price, mrp, gst_slab, hsn_code, quantity, reorder_level)` — Add new SKUs to catalog.
  * `list_low_stock()` — Low inventory alert list.
  * `list_all_products(category)` — Catalog listing grouped by category.
  * `search_products(query)` — Fuzzy product search.

* **Multi-Item GST Billing (`skills/billing.py`):**
  * `start_bill(customer_name)` — Create draft `bill_id`.
  * `add_item_to_bill(bill_id, sku_or_name, qty)` — Add line item with stock check.
  * `remove_item_from_bill(bill_id, sku_or_name)` — Remove line item.
  * `edit_item_qty(bill_id, sku_or_name, new_qty)` — Update item quantity.
  * `preview_bill(bill_id)` — Preview tax breakdown, subtotal, CGST, SGST, grand total.
  * `finalize_bill(bill_id, payment_mode, payment_ref)` — Atomic stock decrement, payment recording & sale completion.

* **Khata Credit Ledger (`skills/credit.py`):**
  * `charge_khata(customer_name, amount, bill_id)` — Charge credit balance.
  * `record_payment(customer_name, amount)` — Record credit repayment.
  * `get_khata_balance(customer_name)` — Balance & credit transaction history.
  * `list_all_khata()` — List all customers with non-zero credit balance.

* **Analytics (`skills/analytics.py`):**
  * `daily_summary(date_str)` — Total revenue, GST breakdown, payment mode split, top items.
  * `close_day(date_str)` — Day closeout report.

* **Document Generation (`skills/documents.py` & `docgen/`):**
  * `generate_invoice_pdf(bill_id)` — Generates PDF GST Tax Invoice using ReportLab (`docgen/invoice_template.py`).
  * `generate_analysis_deck(period)` — Generates PowerPoint presentation with embedded Matplotlib charts (`docgen/deck_builder.py`).

* **Preferences (`skills/preferences.py`):**
  * `set_preference(key, value)` / `get_preference(key)` — Store and retrieve owner standing preferences.

---

## 💡 Resolution of the 9 Hard Requirements

1. **Grounding & Zero Hallucinations:** Prices, stock levels, and customer balances come strictly from SQLite tool outputs.
2. **Oversell Guard:** Enforced atomically in Python code; requests exceeding available stock trigger refusal messages.
3. **Deterministic GST Math:** Pure function `_calculate_gst()` calculates intra-state CGST (50%) and SGST (50%) per line item.
4. **Multi-Turn Bills:** Draft bills persist across turns until finalized.
5. **Idempotency:** Unique `update_id` logging prevents duplicate billing on network retries.
6. **Concurrency Safety:** `BEGIN IMMEDIATE` write locks serialize database writes cleanly under parallel load.
7. **Code Guardrails:** Validation rules (e.g. `cost_price <= mrp`, GST slab in `[0, 5, 12, 18]`) enforced in tool code.
8. **Real Document Artifacts:** Real PDF tax invoices and PPTX slides generated locally and delivered via Telegram.
9. **Session Persistence:** Owner preferences persist in SQLite even across `/new` context resets.

---

## 🧪 Comprehensive 29-Suite Automated Testing

Run the full automated test suite:
```bash
pytest tests/ -v
```

Our test suite includes **29 automated unit and integration tests**:
* `tests/test_agent_flow.py` — End-to-end billing, PDF generation, Khata lifecycle, PPTX deck creation, preferences.
* `tests/test_docgen_and_harness.py` — PDF invoice non-empty content validation, PowerPoint slide layout verification, tool schema completeness, Khata repayment lifecycle, search fallback.
* `tests/test_inventory_edge_cases.py` — Cost price vs MRP guards, invalid GST slabs, negative stock receipts, catalog search, low-stock threshold alerts.
* `tests/test_billing_edge_cases.py` — Quantity editing, line item removal, invalid payment mode handling, non-existent bill errors.
* `tests/test_analytics_and_concurrency.py` — Sales summary calculations, day closeout, and multi-threaded 5-cashier concurrent write locks.
* `tests/test_gst_calc.py` — Tax calculation accuracy for 0%, 5%, 12%, and 18% slabs.
* `tests/test_oversell.py` — Oversell guard refusal and stock quantity decrementing.
* `tests/test_idempotency.py` — Telegram `update_id` idempotency protection.
* `tests/test_auth.py` — Telegram mobile contact verification authentication lifecycle.
