import os
import json
import logging
from typing import Dict, Any, List, Callable
from openai import OpenAI

from skills import inventory, billing, credit, analytics, documents, preferences, audit

logger = logging.getLogger(__name__)

# ── LLM Provider Configuration ──────────────────────────────────────
# Uses Ollama Cloud's OpenAI-compatible API.
# Two API keys are supported for automatic failover on rate limit (429) errors.
def normalize_openai_base_url(base_url: str) -> str:
    """Return an OpenAI-compatible base URL for the configured provider.

    Ollama's native API lives at ``/api`` while its OpenAI-compatible API lives
    at ``/v1``. The OpenAI SDK appends ``/chat/completions``, so passing an
    Ollama native URL would otherwise request the invalid ``/api/chat/completions``.
    """
    normalized = base_url.strip().rstrip("/")
    if normalized.endswith("/api"):
        return f"{normalized[:-4]}/v1"
    return normalized


API_BASE_URL = normalize_openai_base_url(
    os.getenv("LLM_BASE_URL", "https://ollama.com/v1")
)
MODEL_NAME = os.getenv("LLM_MODEL", "nemotron-3-super")

# Dual API key pool for rate-limit failover
def _load_api_keys() -> List[str]:
    """Load API keys from environment. Called lazily to support test environments."""
    keys: List[str] = []
    for key_env in ["LLM_API_KEY_1", "LLM_API_KEY_2"]:
        val = os.getenv(key_env, "").strip()
        if val:
            keys.append(val)
    # Accept Ollama's provider-native environment variable as a fallback.
    if not keys:
        ollama_key = os.getenv("OLLAMA_API_KEY", "").strip()
        if ollama_key:
            keys.append(ollama_key)
    return keys

_API_KEYS: List[str] = _load_api_keys()

if not _API_KEYS:
    logger.warning("⚠️ No LLM API keys found at import time. Set LLM_API_KEY_1 in .env before running the bot.")

# Track which key is currently active (index into _API_KEYS)
_active_key_index = 0

def _build_client(api_key: str) -> OpenAI:
    """Build an OpenAI-compatible client pointing at the configured base URL."""
    return OpenAI(api_key=api_key, base_url=API_BASE_URL)

def get_llm_client() -> OpenAI:
    """Get the currently active LLM client. Raises if no keys configured."""
    global _API_KEYS
    # Reload keys lazily in case dotenv was loaded after initial import
    if not _API_KEYS:
        _API_KEYS = _load_api_keys()
    if not _API_KEYS:
        raise ValueError("No LLM API keys configured! Set LLM_API_KEY_1 (and optionally LLM_API_KEY_2) in .env")
    return _build_client(_API_KEYS[_active_key_index])

def failover_to_next_key() -> bool:
    """Switch to the next API key. Returns True if a new key is available, False if exhausted."""
    global _active_key_index
    next_idx = _active_key_index + 1
    if next_idx < len(_API_KEYS):
        _active_key_index = next_idx
        logger.warning(f"⚡ Rate limit hit — failing over to API key #{next_idx + 1}")
        return True
    else:
        # Wrap around back to key 1 (it may have recovered by now)
        _active_key_index = 0
        logger.warning("⚠️ All API keys exhausted — wrapping back to key #1")
        return False

def reset_key_rotation():
    """Reset back to the first API key (call at start of each request cycle)."""
    global _active_key_index
    _active_key_index = 0

# System Prompt grounding instructions
SYSTEM_PROMPT = """
You are Supermarket Ops Agent, an intelligent, proactive AI operations assistant for an Indian supermarket.
You help the shop owner manage stock inventory, cut multi-item bills with GST, manage customer credit ledgers (khata), analyze sales, and generate PDF invoices & PowerPoint decks.

GROUNDING & INTEGRITY RULES:
1. Grounding: Inventory prices, stock quantities, GST slabs, and customer balances MUST come ONLY from tool execution results. Never guess or hallucinate prices or stock numbers.
2. Direct Tool Execution: When requested to perform a supermarket task, ALWAYS execute the appropriate tool immediately in your FIRST response turn:
   • For viewing full inventory/stock ("Show stock", "/stock", "List products") → call `list_all_products`.
   • For low stock reorder items ("Low stock", "/lowstock") → call `list_low_stock`.
   • For creating/cutting a bill ("make a bill", "/bill 2 sugar, 4 Maggi") → call `quick_create_bill` or `start_bill`.
   • For customer credit balances ("Khata query", "/khata") → call `list_all_khata` or `get_khata_balance`.
   • For sales & revenue breakdown ("sales summary", "/summary") → call `daily_summary`.
   • For populating problem statement stock items ("load default stocks", "/seed") → call `populate_default_inventory`.
3. Oversell Guard: If a tool returns an oversell warning or error, relay the refusal clearly to the owner (e.g. "Cannot sell X units; only Y in stock.").
4. GST Math: All GST calculations are calculated deterministically by tools. Explain the itemized breakdown clearly to the owner.
5. Billing Speed & Workflow: When asked to make or start a bill (e.g. "make a bill: 2kg sugar, 4 Maggi, UPI"), if a payment mode is specified in the prompt, pass `payment_mode` to `quick_create_bill` to finalize immediately. If NO payment mode is mentioned, create as a DRAFT so the user can edit or confirm payment.
6. Customer Credit (Khata): Always check or record khata using tools. If a customer is not found, inform the user clearly.
7. Clear & Readable Formatting: Present items in a clean, structured format using emojis (e.g. 📊, 📌, 🔹, 🛒, 📦) or clean bullet dots (`•`). NEVER output raw hyphens/dashes (`-`) or slashes (`/`) at the beginning of list items or bullet lines. Use `•` or emojis for ALL bullet points and lists without exception. Avoid raw Markdown headers (like #, ##, ###); use bold text (*text*) with emojis for section titles.
8. Concise, Helpful & Friendly: Be direct, helpful, polite, and use Indian currency formatting (₹). Mention the active shop name in responses.
9. Audit Trail: To answer questions about past operations or stock changes (e.g. "why did Maggi stock drop?"), call `get_audit_trail`.
10. Strict Domain Scope & Off-Topic Guardrails: You are EXCLUSIVELY a Supermarket Operations Agent. If the user asks general, off-topic questions unrelated to supermarket operations, politely refuse.
11. Ultrafast Single-Turn Execution Guard: NEVER call search or stock check tools before calling update actions like `receive_stock`, `quick_create_bill`, or `charge_khata`. Execute the target tool directly in Turn 1!
"""

# Tool Dispatch Map
TOOL_DISPATCH: Dict[str, Callable] = {
    "get_stock": inventory.get_stock,
    "receive_stock": inventory.receive_stock,
    "add_product": inventory.add_product,
    "populate_default_inventory": inventory.populate_default_inventory,
    "list_low_stock": inventory.list_low_stock,
    "list_all_products": inventory.list_all_products,
    "search_products": inventory.search_products,
    "start_bill": billing.start_bill,
    "add_item_to_bill": billing.add_item_to_bill,
    "quick_create_bill": billing.quick_create_bill,
    "remove_item_from_bill": billing.remove_item_from_bill,
    "edit_item_qty": billing.edit_item_qty,
    "preview_bill": billing.preview_bill,
    "finalize_bill": billing.finalize_bill,
    "charge_khata": credit.charge_khata,
    "record_payment": credit.record_payment,
    "get_khata_balance": credit.get_khata_balance,
    "list_all_khata": credit.list_all_khata,
    "daily_summary": analytics.daily_summary,
    "close_day": analytics.close_day,
    "generate_invoice_pdf": documents.generate_invoice_pdf,
    "generate_analysis_deck": documents.generate_analysis_deck,
    "set_preference": preferences.set_preference,
    "get_preference": preferences.get_preference,
    "get_audit_trail": audit.get_audit_trail
}

# OpenAI-compatible tool schemas
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "get_stock",
            "description": "Check current stock level, MRP, unit, and GST slab for a product by SKU ID or product name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "SKU ID or product name (e.g. 'Aashirvaad Atta' or 'SKU-SALT-01')"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "receive_stock",
            "description": "Receive new stock inventory for a product SKU (increments stock quantity).",
            "parameters": {
                "type": "object",
                "properties": {
                    "sku_id": {"type": "string", "description": "SKU ID or product name"},
                    "qty": {"type": "number", "description": "Quantity received (e.g. 50)"},
                    "cost_price": {"type": "number", "description": "Optional purchase cost price per unit"},
                    "mrp": {"type": "number", "description": "Optional MRP selling price"}
                },
                "required": ["sku_id", "qty"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_product",
            "description": "Add a new product SKU to the supermarket catalog.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Product name"},
                    "category": {"type": "string", "description": "Category (e.g., Grains, Dairy, Beverages)"},
                    "unit": {"type": "string", "description": "Unit of measure: kg, g, litre, ml, packet, piece, dozen"},
                    "is_loose": {"type": "boolean", "description": "True if loose items sold by weight/volume"},
                    "cost_price": {"type": "number", "description": "Cost price"},
                    "mrp": {"type": "number", "description": "MRP / selling price"},
                    "gst_slab": {"type": "number", "description": "GST slab rate: 0, 5, 12, or 18"},
                    "hsn_code": {"type": "string", "description": "HSN tax code"},
                    "quantity": {"type": "number", "description": "Initial stock quantity (default 0)"},
                    "reorder_level": {"type": "number", "description": "Low stock reorder threshold (default 10)"}
                },
                "required": ["name", "category", "unit", "is_loose", "cost_price", "mrp", "gst_slab", "hsn_code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_low_stock",
            "description": "List all products where stock quantity is at or below the reorder level.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "populate_default_inventory",
            "description": "Auto-populate an empty shop inventory with the 10 standard problem statement sample stock items (Maggi, Wheat Atta, Sugar, Sunflower Oil, Milk, Basmati Rice, Salt, Soap, Butter, Tea) and sample customers.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_all_products",
            "description": "List all available products in inventory with stock levels, MRPs, units, and categories.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Optional category filter (e.g. 'Dairy', 'Grains & Flour')"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "Search product catalog by name, category, or SKU.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search keyword"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "quick_create_bill",
            "description": "ULTRAFAST single-turn bill generator. Pass all items, customer name, and payment mode to start, add items, and finalize a bill in 1 single call!",
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "description": "List of objects with 'name' and 'qty', e.g. [{'name': 'sugar', 'qty': 2}, {'name': 'Maggi', 'qty': 4}]",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "Product SKU or name"},
                                "qty": {"type": "number", "description": "Quantity"}
                            },
                            "required": ["name", "qty"]
                        }
                    },
                    "customer_name": {"type": "string", "description": "Optional customer name"},
                    "payment_mode": {"type": "string", "description": "Optional payment mode: 'upi', 'cash', 'card', 'khata'"}
                },
                "required": ["items"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "start_bill",
            "description": "Create a new draft bill for a customer (or walk-in). Returns new draft bill_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string", "description": "Optional customer name"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_item_to_bill",
            "description": "Add an item and quantity to a draft bill.",
            "parameters": {
                "type": "object",
                "properties": {
                    "bill_id": {"type": "string", "description": "Draft bill ID (e.g. 'BILL-12345678')"},
                    "sku_or_name": {"type": "string", "description": "SKU ID or product name"},
                    "qty": {"type": "number", "description": "Quantity to add"}
                },
                "required": ["bill_id", "sku_or_name", "qty"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "remove_item_from_bill",
            "description": "Remove an item line from a draft bill.",
            "parameters": {
                "type": "object",
                "properties": {
                    "bill_id": {"type": "string"},
                    "sku_or_name": {"type": "string"}
                },
                "required": ["bill_id", "sku_or_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_item_qty",
            "description": "Edit the quantity of an item in a draft bill.",
            "parameters": {
                "type": "object",
                "properties": {
                    "bill_id": {"type": "string"},
                    "sku_or_name": {"type": "string"},
                    "new_qty": {"type": "number"}
                },
                "required": ["bill_id", "sku_or_name", "new_qty"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "preview_bill",
            "description": "Preview a bill showing subtotal, CGST, SGST, total GST, and grand total without committing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "bill_id": {"type": "string"}
                },
                "required": ["bill_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "finalize_bill",
            "description": "Finalize a draft bill atomically: checks stock, decrements inventory, applies payment, and logs transaction.",
            "parameters": {
                "type": "object",
                "properties": {
                    "bill_id": {"type": "string"},
                    "payment_mode": {"type": "string", "description": "Payment mode: 'cash', 'upi', 'card', or 'khata'"},
                    "payment_ref": {"type": "string", "description": "Optional transaction reference / UPI ID"}
                },
                "required": ["bill_id", "payment_mode"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "charge_khata",
            "description": "Add a credit charge to a customer's khata ledger balance.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string"},
                    "amount": {"type": "number"},
                    "bill_id": {"type": "string"}
                },
                "required": ["customer_name", "amount"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "record_payment",
            "description": "Record a credit repayment from a customer to lower their khata ledger balance.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string"},
                    "amount": {"type": "number"}
                },
                "required": ["customer_name", "amount"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_khata_balance",
            "description": "Get current khata balance and recent credit transaction history for a customer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string"}
                },
                "required": ["customer_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_all_khata",
            "description": "List all customers with non-zero credit balance.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "daily_summary",
            "description": "Get daily sales revenue, GST collected, payment mode breakdown, and top items.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_str": {"type": "string", "description": "Optional date formatted as YYYY-MM-DD"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "close_day",
            "description": "Close out day operations and generate closed daily summary report.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_str": {"type": "string", "description": "Optional date formatted as YYYY-MM-DD"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_invoice_pdf",
            "description": "Generate a PDF tax invoice file for a bill.",
            "parameters": {
                "type": "object",
                "properties": {
                    "bill_id": {"type": "string"}
                },
                "required": ["bill_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_analysis_deck",
            "description": "Generate a PowerPoint (.pptx) presentation with charts for sales and inventory analysis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {"type": "string", "description": "Period description e.g. 'Today', 'Weekly', 'August 2026'"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_preference",
            "description": "Save or update a persistent preference setting for the owner.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Setting key (e.g. 'default_payment_mode', 'shop_name')"},
                    "value": {"type": "string", "description": "Setting value"}
                },
                "required": ["key", "value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_preference",
            "description": "Get a persistent preference setting for the owner.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"}
                },
                "required": ["key"]
            }
        }
    },
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
]
