-- Supermarket Operations SQLite Database Schema

CREATE TABLE IF NOT EXISTS products (
    sku_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    unit TEXT NOT NULL,             -- kg, g, litre, ml, packet, dozen, piece
    is_loose BOOLEAN DEFAULT 0,
    cost_price REAL NOT NULL,
    mrp REAL NOT NULL,
    gst_slab REAL NOT NULL DEFAULT 0,          -- 0, 5, 12, 18
    hsn_code TEXT,
    quantity REAL NOT NULL DEFAULT 0,
    reorder_level REAL NOT NULL DEFAULT 10
);

CREATE TABLE IF NOT EXISTS customers (
    customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    khata_balance REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS bills (
    bill_id TEXT PRIMARY KEY,   -- UUID
    status TEXT NOT NULL DEFAULT 'draft',                -- 'draft' | 'finalized' | 'voided'
    customer_id INTEGER NULL,
    payment_mode TEXT,          -- cash, upi, card, khata
    payment_ref TEXT,
    subtotal REAL DEFAULT 0,
    cgst REAL DEFAULT 0,
    sgst REAL DEFAULT 0,
    total REAL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finalized_at TIMESTAMP NULL,
    FOREIGN KEY(customer_id) REFERENCES customers(customer_id)
);

CREATE TABLE IF NOT EXISTS bill_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_id TEXT NOT NULL,
    sku_id TEXT NOT NULL,
    qty REAL NOT NULL,
    unit_price REAL NOT NULL,
    gst_slab REAL NOT NULL DEFAULT 0,
    line_total REAL NOT NULL,
    FOREIGN KEY(bill_id) REFERENCES bills(bill_id),
    FOREIGN KEY(sku_id) REFERENCES products(sku_id)
);

CREATE TABLE IF NOT EXISTS khata_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    type TEXT NOT NULL,          -- 'charge' | 'payment'
    amount REAL NOT NULL,
    bill_id TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(customer_id) REFERENCES customers(customer_id),
    FOREIGN KEY(bill_id) REFERENCES bills(bill_id)
);

CREATE TABLE IF NOT EXISTS preferences (
    owner_id TEXT NOT NULL,       -- Telegram user id
    key TEXT NOT NULL,            -- e.g., 'default_payment_mode', 'default_atta_sku', 'shop_name'
    value TEXT NOT NULL,
    PRIMARY KEY (owner_id, key)
);

CREATE TABLE IF NOT EXISTS idempotency_log (
    update_id TEXT PRIMARY KEY,   -- Telegram update_id
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS shops (
    shop_id INTEGER PRIMARY KEY AUTOINCREMENT,
    shop_name TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    shop_address TEXT NULL,
    shop_gstin TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_sessions (
    telegram_id TEXT PRIMARY KEY,
    shop_id INTEGER NOT NULL,
    authenticated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(shop_id) REFERENCES shops(shop_id)
);

CREATE TABLE IF NOT EXISTS authenticated_users (
    telegram_id TEXT PRIMARY KEY,
    phone_number TEXT NULL,
    authenticated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

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
