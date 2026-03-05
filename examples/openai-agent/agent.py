"""Support agent — a realistic customer support agent powered by OpenAI.

The agent handles customer queries by:
1. Searching a knowledge base for relevant articles
2. Looking up the customer's order history
3. Drafting a helpful reply using GPT-4o-mini

This file contains the agent logic *only*. No evalcraft imports.
evalcraft instrumentation lives in the test files so that
production code stays clean.
"""

from __future__ import annotations

import json
from typing import Any


# ---------------------------------------------------------------------------
# Fake tools (replace with real implementations in production)
# ---------------------------------------------------------------------------

def search_knowledge_base(query: str, max_results: int = 3) -> list[dict]:
    """Search internal knowledge base articles."""
    # Simulated KB — in production this would call a vector DB / Elasticsearch
    articles = [
        {
            "id": "kb-001",
            "title": "How to track your order",
            "content": (
                "To track your order, visit our website and click 'My Orders'. "
                "Enter your order number (found in the confirmation email) and zip code. "
                "You will see real-time tracking information."
            ),
        },
        {
            "id": "kb-002",
            "title": "Return and refund policy",
            "content": (
                "We offer 30-day returns on all items. To initiate a return, "
                "log into your account, go to 'Order History', and click 'Return Item'. "
                "Refunds are processed within 5-7 business days to the original payment method."
            ),
        },
        {
            "id": "kb-003",
            "title": "Damaged or missing items",
            "content": (
                "If your order arrived damaged or an item is missing, please contact us "
                "within 48 hours of delivery. We will ship a replacement at no charge "
                "or issue a full refund, whichever you prefer."
            ),
        },
    ]
    hits = [a for a in articles if any(w in a["title"].lower() or w in a["content"].lower()
                                        for w in query.lower().split())]
    return hits[:max_results] if hits else articles[:max_results]


def lookup_order(order_id: str) -> dict:
    """Look up order details by order ID."""
    orders = {
        "ORD-1042": {
            "id": "ORD-1042",
            "status": "shipped",
            "items": [{"name": "Wireless Headphones", "qty": 1, "price": 89.99}],
            "shipped_date": "2026-02-28",
            "estimated_delivery": "2026-03-06",
            "carrier": "UPS",
            "tracking": "1Z999AA10123456784",
        },
        "ORD-9873": {
            "id": "ORD-9873",
            "status": "delivered",
            "items": [{"name": "USB-C Hub", "qty": 2, "price": 34.99}],
            "delivered_date": "2026-02-20",
        },
    }
    return orders.get(order_id, {"error": f"Order {order_id!r} not found"})


# ---------------------------------------------------------------------------
# OpenAI tool schemas
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": "Search the customer support knowledge base for relevant articles.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "max_results": {
                        "type": "integer",
                        "description": "Max articles to return (1-5)",
                        "default": 3,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_order",
            "description": "Look up the status and details of a customer order by order ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "Order ID (e.g. ORD-1042)",
                    }
                },
                "required": ["order_id"],
            },
        },
    },
]

TOOL_MAP: dict[str, Any] = {
    "search_knowledge_base": search_knowledge_base,
    "lookup_order": lookup_order,
}

SYSTEM_PROMPT = """You are a friendly and efficient customer support agent for ShopEasy, \
an online retail store. Your job is to help customers resolve their issues quickly and \
professionally.

When answering:
- Always search the knowledge base first for relevant articles
- If the customer mentions an order number, look it up
- Be concise but empathetic
- End your reply with a brief offer to help further
"""


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------

def run_support_agent(client: Any, user_message: str) -> str:
    """Run the support agent for a customer message.

    Args:
        client: An openai.OpenAI() client instance.
        user_message: The customer's support message.

    Returns:
        The agent's final reply as a string.
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    # Agentic loop — keep calling until no more tool calls
    for _iteration in range(5):  # safety cap
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )
        msg = response.choices[0].message

        if not msg.tool_calls:
            # Final answer — no more tools to call
            return msg.content or ""

        # Execute tool calls and append results
        messages.append(msg)
        for tc in msg.tool_calls:
            fn_name = tc.function.name
            fn_args = json.loads(tc.function.arguments)
            fn = TOOL_MAP.get(fn_name)
            result = fn(**fn_args) if fn else {"error": f"Unknown tool: {fn_name}"}

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result),
            })

    # Fallback — return whatever the last message was
    return messages[-1].get("content", "I'm sorry, I couldn't process your request.")
