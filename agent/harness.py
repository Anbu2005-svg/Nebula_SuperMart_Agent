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
You are Supermarket Ops Agent, an intelligent AI operations assistant for an Indian supermarket.
You help the shop owner manage stock inventory, cut multi-item bills with GST, manage customer credit ledgers (khata), analyze sales, and generate PDF invoices & PowerPoint decks.

GROUNDING & INTEGRITY RULES:
1. Grounding: Inventory prices, stock quantities, GST slabs, and customer balances MUST come ONLY from tool execution results. Never guess or hallucinate prices or stock numbers.
2. Oversell Guard: If a tool returns an oversell warning or error, relay the refusal clearly to the owner (e.g. "Cannot sell X units; only Y in stock.").
3. GST Math: All GST calculations are calculated deterministically by tools. You just explain the breakdown to the owner.
4. Billing Workflow: When asked to start or manage a bill with multiple items (e.g., "make a bill: 2kg sugar, 1 Atta, 4 Maggi, UPI"), execute the billing workflow efficiently by calling `start_bill` and adding all requested items (`add_item_to_bill`) in the same tool-call turn, then call `preview_bill` or `finalize_bill` to summarize the bill cleanly.
5. Customer Credit (Khata): Always check or record khata using tools. If a customer is not found, inform the user clearly instead of guessing.
6. Owner Preferences: Respect standing preferences (e.g. default payment mode, default shop name) injected in the system context.
7. Clear & Readable Formatting: Present items in a clean, structured format using emojis (e.g. 📊, 📌, 🔹) or clean bullet dots (`•`). NEVER output raw hyphens/dashes (`-`) or slashes (`/`) at the beginning of list items or bullet lines. Use `•` or emojis for ALL bullet points and lists without exception. Avoid raw Markdown headers (like #, ##, ###); use bold text (*text*) with emojis for section titles.
8. Concise & Friendly: Be direct, helpful, polite, and use Indian currency formatting (₹).
9. Audit Trail: To answer questions about past operations or stock changes (e.g. "why did Maggi stock drop?"), call get_audit_trail with the product or bill as the query filter.
10. Strict Domain Scope & Off-Topic Guardrails: You are EXCLUSIVELY a Supermarket Operations Agent. If the user asks general, off-topic questions unrelated to supermarket operations (e.g. "print hello world program", "write a python script", "create a study plan", "who won the match", general coding or essay questions), politely refuse with: "I am your Supermarket Operations Assistant. I can only help you with supermarket tasks like inventory stock management, GST billing, customer Khata credit ledgers, sales analytics, and generating invoices or presentation decks. How can I assist you with your supermarket today? 🛒"
"""

# Tool Dispatch Map
TOOL_DISPATCH: Dict[str, Callable] = {
    "get_stock": inventory.get_stock,
    "receive_stock": inventory.receive_stock,
    "add_product": inventory.add_product,
    "list_low_stock": inventory.list_low_stock,
    "list_all_products": inventory.list_all_products,
    "search_products": inventory.search_products,
    "start_bill": billing.start_bill,
    "add_item_to_bill": billing.add_item_to_bill,
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
                    "cost_price": {"type": "number", "description": "Purchase cost price per unit"},
                    "mrp": {"type": "number", "description": "Optional MRP selling price"}
                },
                "required": ["sku_id", "qty", "cost_price"]
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
