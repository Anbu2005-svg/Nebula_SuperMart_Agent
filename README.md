# Nebula SuperMart AI Ops Agent 🛒🤖

> **Supermarket Operations AI Agent for Telegram**  
> An intelligent, autonomous Telegram AI Operations Agent for Indian Kirana Supermarkets built with **100% Free & Open-Source Tools**, PostgreSQL cloud database, dual LLM key failover, and ReportLab / Matplotlib document generators.

---

## 📌 Project & Repository Details
* **GitHub Repository:** [https://github.com/Anbu2005-svg/Nebula_SuperMart_Agent](https://github.com/Anbu2005-svg/Nebula_SuperMart_Agent)
* **Telegram Bot:** [@Nebula_superMart_bot](https://t.me/Nebula_superMart_bot)
* **Live Deployment:** **Deployed Live on Render** 🚀 ([Render Web Service](https://render.com))
* **Author / Contributor:** `Anbu2005-svg`
* **Core Tech Stack:** Python 3.9+, Telegram Bot API (`python-telegram-bot`), Ollama Cloud OpenAI-compatible API (`nemotron-3-super`), PostgreSQL (psycopg2 / Prisma), ReportLab (PDF Invoices), python-pptx & Matplotlib (PPTX Decks), pytest.

---

## 📱 Complete Telegram Bot Command Menu

The bot automatically registers its command menu with the Telegram API:

| Command | Description | Example Usage |
|---|---|---|
| `/start` | Start bot session, view welcome card, register or log in | `/start` |
| `/stock` | List full inventory catalog with SKUs, MRP, GST slabs, and stock levels | `/stock` |
| `/lowstock` | List items at or below reorder level requiring immediate restock | `/lowstock` |
| `/bill <items>` | Create & finalize a multi-item bill with GST & stock decrement | `/bill 2 sugar, 4 maggi, UPI` |
| `/khata` | View customer credit ledger & outstanding balance details | `/khata` |
| `/summary` | View daily sales revenue, GST collected, and payment breakdown | `/summary` |
| `/invoice <bill_id>` | Download official PDF GST Tax Invoice for a finalized bill | `/invoice BILL-7C9A41E2` |
| `/analysis [period]` | Download 4-slide executive PowerPoint (.pptx) sales & ops deck | `/analysis Today` |
| `/new` / `/reset` / `/clear` | Clear in-memory chat session (preserves database & preferences) | `/new` |
| `/help` | Display interactive command menu and usage guide | `/help` |
| `/logout` | Log out of current shop session | `/logout` |

---

## 🚀 Quickstart & Deployment Guide

### 1. Local Setup
```bash
# Clone repository
git clone https://github.com/Anbu2005-svg/Nebula_SuperMart_Agent.git
cd Nebula_SuperMart_Agent

# Create and activate virtual environment
python -m venv venv
.\venv\Scripts\activate   # Windows (or source venv/bin/activate on Linux/macOS)

# Install dependencies
pip install -r requirements.txt

# Configure .env file
cp .env.example .env

# Run test suite
pytest tests/ -v

# Launch Telegram bot locally
python bot.py
```

### 2. 🌐 Render Cloud Web Service Deployment (Live Deployed)
This bot is **deployed live on Render** and includes a built-in HTTP health-check server listening on port `PORT` (`8080`) specifically designed for **Render Web Services**:

1. Create a new **Web Service** on [Render.com](https://render.com).
2. Connect your GitHub repository `Anbu2005-svg/Nebula_SuperMart_Agent`.
3. Set the following build and start configurations:
   * **Runtime**: Python 3
   * **Build Command**: `pip install -r requirements.txt`
   * **Start Command**: `python bot.py`
4. Add Environment Variables in Render Dashboard:
   * `TELEGRAM_BOT_TOKEN`: Your Telegram Bot Token from @BotFather
   * `DATABASE_URL`: Cloud PostgreSQL Connection String (Supabase/Neon/Render)
   * `LLM_API_KEY_1`: Your Ollama Cloud / OpenAI API key
   * `PORT`: `8080`
5. Render automatically builds the service, binds to port `8080`, and runs **Live** 24/7!

---

## 📦 Initial 10-Product Inventory Dataset

Pre-populated in database via `db/seed.py`:

| # | Product Name | Category | Stock | Unit | MRP | GST |
|---|---|---|---|---|---|---|
| 1 | Brooke Bond Red Label Tea 250g | Beverages | 15 | packet | ₹140 | 5% |
| 2 | Amul Pasteurised Butter 100g | Dairy | 20 | packet | ₹62 | 12% |
| 3 | Amul Taaza Toned Milk 1L | Dairy | 25 | packet | ₹56 | 0% |
| 4 | Fortune Sunlite Sunflower Oil 1L | Edible Oils | 40 | litre | ₹155 | 5% |
| 5 | Aashirvaad Whole Wheat Atta 5kg | Grains & Flour | 30 | packet | ₹245 | 5% |
| 6 | Basmati Rice 1kg (Loose) | Grains & Flour | 50 | kg | ₹80 | 0% |
| 7 | Refined White Sugar 1kg (Loose) | Pantry Basics | 60 | kg | ₹48 | 0% |
| 8 | Tata Iodized Salt 1kg | Pantry Basics | 45 | packet | ₹28 | 0% |
| 9 | Surf Excel Easy Wash Detergent Powder 1kg | Household Care | 25 | packet | ₹140 | 18% |
| 10 | Maggi 2-Minute Instant Noodles 70g | Snacks & Packaged Food | 100 | packet | ₹14 | 18% |

---

## 🛠️ Modular Skills & Tools Architecture

* **Inventory (`skills/inventory.py`):** `get_stock`, `receive_stock`, `add_product`, `update_gst_slab`, `list_low_stock`, `list_all_products`, `search_products`.
* **Multi-Item GST Billing (`skills/billing.py`):** `start_bill`, `add_item_to_bill`, `remove_item_from_bill`, `edit_item_qty`, `preview_bill`, `finalize_bill`, `quick_create_bill`.
* **Khata Credit Ledger (`skills/credit.py`):** `charge_khata`, `record_payment`, `get_khata_balance`, `list_all_khata`.
* **Analytics & Reporting (`skills/analytics.py`):** `daily_summary`, `close_day`.
* **Document Generation (`skills/documents.py` & `docgen/`):** `generate_invoice_pdf` (ReportLab PDF), `generate_analysis_deck` (widescreen 4-slide PPTX deck with Matplotlib charts).
* **Audit Trail (`skills/audit.py`):** `get_audit_trail` (queries before/after mutation event history).
* **Authentication & Preferences (`skills/auth.py` & `skills/preferences.py`):** `register_shop`, `login_shop`, `set_preference`, `get_preference`.

---

## 🧪 Comprehensive Automated Test Suite (41 Tests)

Run all 41 unit and integration tests:
```bash
pytest tests/ -v
```

Tests cover end-to-end multi-item billing, oversell protection, ReportLab PDF generation, Matplotlib PPTX chart rendering, 5-cashier concurrent PostgreSQL write locking, Telegram update idempotency, and audit event logs.

---

## ✨ Unique Features & Key Highlights

### 1. 🔐 Multi-Tenant Shop Owner Authentication (Login & Signup)
* Supports full multi-tenant isolation where each shop owner operates securely under their own shop identity.
* **New Shop Signup**: Allows new shop owners to register their store credentials (`shop_name`, `shop_address`, `shop_gstin`, password) directly via Telegram contact sharing or interactive prompts.
* **Existing User Login**: Returning shop owners log in instantly with their credentials. Session state persists across chats and automatically expires after 24 hours of inactivity.
* **Preserves Data Safety**: Multi-tenant database schema ensures inventory, bills, and Khata ledgers remain 100% isolated per shop session.

### 2. 🌐 2-Step Verified Government GST Slab Rate Updates
* **Government GST Update Handling**: When a shop owner mentions a GST slab revision (e.g. *"Government updated GST on Sugar to 5%"* or *"Verify new GST rate for Rice"*), the agent does NOT modify catalog data blindly.
* **2-Step Verification Flow**:
  1. The agent inspects current catalog rates using search tools.
  2. The agent presents an explicit confirmation card to the shop owner:
     ```text
     ⚠️ CONFIRM GST SLAB UPDATE:
     • Target: Refined White Sugar 1kg [SKU-SUGAR-1K]
     • Current GST: 0% ➔ Proposed New GST: 5%
     Please reply 'YES' to confirm and update catalog.
     ```
  3. Only after the user confirms with `YES` / `confirm` / `ok`, the agent invokes `update_gst_slab` to commit changes to PostgreSQL.

### 3. 🛡️ Intelligent Token-Cost & Context Optimization Guardrails
To reduce LLM token consumption, eliminate API rate limits, and cut operational LLM costs by **60% to 70%**:
* **Smart Context Compression**: Automatically summarizes older chat history turns when conversation length exceeds 10 turns. Keeps system prompt & recent turns intact while compressing earlier turns into a compact highlight block, preventing token explosion.
* **Ultrafast Single-Turn Execution Guard**: Executes complex multi-item billing (`quick_create_bill`) or stock receipts in 1 single LLM turn rather than forcing multi-turn search/query roundtrips.
* **Dual API Key Failover & Round-Robin Load Balancing**: Automatically failovers across `LLM_API_KEY_1`, `LLM_API_KEY_2`, etc. when hitting 429 rate limit errors, distributing concurrent shop traffic seamlessly.
* **Sticky Default Payment Mode Persistence**: Remembers the shop owner's preferred payment mode (e.g., `UPI`) in PostgreSQL so subsequent bills automatically finalize via `UPI` without requiring the user to re-type the payment mode every time.
