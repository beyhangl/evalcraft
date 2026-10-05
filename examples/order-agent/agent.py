"""A small support agent: answers order questions by calling lookup_order.

This is the code under test. Break it (stop running the tool, look up the
wrong order, change the prompt) and the offline test in tests/ fails, even
though the recording in tests/cassettes/ is unchanged.
"""

from __future__ import annotations

import json
from typing import Any

MODEL = "gpt-6.1-sol"
SYSTEM_PROMPT = "You are a support agent. Use lookup_order for any order question."

TOOLS = [{
    "type": "function",
    "function": {
        "name": "lookup_order",
        "description": "Look up an order's status and delivery date by its id.",
        "parameters": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
        },
    },
}]

ORDERS = {
    "ORDER-123": {"status": "shipped", "eta": "2026-10-09"},
    "ORDER-456": {"status": "processing", "eta": "2026-10-14"},
}


def lookup_order(order_id: str) -> dict[str, Any]:
    return ORDERS.get(order_id, {"status": "not_found"})


def run_agent(client: Any, question: str) -> str:
    """Answer ``question``, calling tools until the model gives a final answer."""
    messages: list[Any] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    for _ in range(5):
        response = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS)
        message = response.choices[0].message
        if not message.tool_calls:
            return message.content or ""
        messages.append(message)
        for call in message.tool_calls:
            args = json.loads(call.function.arguments)
            result = lookup_order(**args)
            messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)}
            )
    return "Sorry, I couldn't finish that."
