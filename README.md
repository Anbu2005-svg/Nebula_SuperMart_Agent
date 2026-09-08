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

## 🏗️ Agent Design, Harness & Technical Architecture

### 1. 🧠 The Agent Harness Picked & Why
We selected the **OpenAI-Compatible Function-Calling Harness** (`agent/harness.py`) backed by **Ollama Cloud** (`nemotron-3-super`):
* **Why Function Calling?** Traditional text/regex parsing of LLM outputs is fragile and prone to syntax failures. Standardized JSON tool schemas guarantee strict type enforcement, deterministic parameter extraction, and reliable tool execution for critical financial and inventory operations (GST, billing, stock receipts).
* **Dual API Key Failover Pool:** Supports multiple API key environment variables (`LLM_API_KEY_1`, `LLM_API_KEY_2`) with round-robin load distribution. If a 429 rate limit error occurs, the harness automatically fails over to the next key without failing user requests.

---

### 2. 🔄 How the Agent Control Loop Works (`agent/control_loop.py`)
```
Telegram User Message (update_id)
       │
       ▼
 1. Check Idempotency Log ──(If already processed)──► Return Cached Preview
       │
       ▼
 2. Load Active Shop Session & Standing Preferences from PostgreSQL
       │
       ▼
 3. Build Dynamic System Prompt (System Instructions + Shop Meta + Standing Preferences)
       │
       ▼
 4. Multi-Step LLM Tool Execution Loop:
    ├── Call LLM API (with round-robin key rotation & failover)
    ├── If Tool Call Requested:
    │     ├── Inject owner_id / update_id into tool arguments
    │     ├── Execute target Python Skill in /skills
    │     ├── Auto-update default_payment_mode if payment mode supplied
    │     └── Pass tool result JSON back to LLM context
    └── Repeat until LLM returns final natural language response
       │
       ▼
 5. Smart Context Compression (If history > 10 messages, summarize older turns)
       │
       ▼
 Deliver Response & Generated Files (PDF / PPTX) to Telegram User
```

---

### 3. 🛠️ Skill & Tool Architecture (`/skills`)
Business logic is decoupled into domain-specific modules under `/skills`:
* **Inventory (`skills/inventory.py`):** Transactional stock lookup, receipt, catalog management, 2-step GST updates, low stock intimations.
* **Multi-Item GST Billing (`skills/billing.py`):** Draft bill state management, stock reservation, oversell checking, `quick_create_bill` 1-turn generation.
* **Khata Credit Ledger (`skills/credit.py`):** Customer balance tracking, credit charging, repayment recording.
* **Analytics (`skills/analytics.py`):** Daily sales aggregation, payment mode splits, day closeout reports.
* **Document Generation (`skills/documents.py` & `docgen/`):** ReportLab PDF invoice builder & 4-slide widescreen PowerPoint Matplotlib deck builder.
* **Audit Trail (`skills/audit.py`):** Immutably logs before/after values for all business mutations.
* **Auth & Preferences (`skills/auth.py` & `skills/preferences.py`):** Multi-tenant shop authentication and persistent standing preferences.

---

### 4. 💡 How Each Hard Part Was Solved

| Hard Requirement | Technical Solution |
|---|---|
| **Zero Hallucinations & Grounding** | All product prices, stock quantities, GST slabs, and customer balances MUST originate from database tool outputs. System prompt explicitly forbids model guessing. |
| **Oversell Protection & Concurrency** | Enforced atomically inside PostgreSQL transactions (`immediate_transaction`). Quantity is checked at row level before decrementing stock. If requested quantity > available stock, transaction rolls back and returns an `OversellGuardError`. |
| **Deterministic GST Math** | Handled by a pure Python function `_calculate_gst()`. Calculates intra-state CGST (50%) and SGST (50%) deterministically per line item, avoiding LLM floating point rounding errors. |
| **Multi-Turn Bills** | Draft bills persist in PostgreSQL across chat turns with status `'draft'` until the shop owner explicitly finalizes them. |
| **Telegram Network Retries & Idempotency** | Every Telegram update carries a unique `update_id`. Checked against `idempotency_log` table before execution; duplicate requests return cached results without double-billing or double-decrementing stock. |
| **Multi-Tenant Shop Auth & Isolation** | Session tokens expire after 24h of inactivity. All database queries enforce owner scoping (`owner_id`), isolating inventory and financial ledgers per shop. |
| **2-Step Verified Government GST Updates** | When users request a GST rate change, the agent checks current catalog rates, displays an explicit confirmation card (`⚠️ CONFIRM GST SLAB UPDATE`), and executes `update_gst_slab` ONLY after explicit `YES` confirmation. |
| **Token Cost & Context Optimization** | Smart Context Compression summarizes earlier turns when chat history exceeds 10 messages, cutting LLM token costs by ~60–70%. `quick_create_bill` executes multi-item billing in 1 single turn. |
| **Real Document Artifact Generation** | ReportLab PDF invoices and 4-slide Matplotlib PPTX decks query 100% live database figures (zero hardcoded fallback numbers) and deliver files directly via Telegram. |

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
