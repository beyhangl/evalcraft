"""Record the example cassette without an API key.

The committed recording in tests/cassettes/ was made by running the real agent
and the real OpenAI SDK against this scripted stand-in for the model, so
anyone can regenerate it for free. To record against the real model instead,
set OPENAI_API_KEY and run ``pytest --evalcraft-record=all``.

    python scripted_model.py
"""

from __future__ import annotations

from pathlib import Path

import httpx
import openai

from agent import run_agent
from evalcraft import CaptureContext
from evalcraft.adapters import OpenAIAdapter

REPLIES = [
    {"id": "chatcmpl-1", "object": "chat.completion", "created": 1759600000, "model": "gpt-6.1-sol",
     "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
         "role": "assistant", "content": None,
         "tool_calls": [{"id": "call_1", "type": "function", "function": {
             "name": "lookup_order", "arguments": "{\"order_id\": \"ORDER-123\"}"}}]}}],
     "usage": {"prompt_tokens": 96, "completion_tokens": 18, "total_tokens": 114}},
    {"id": "chatcmpl-2", "object": "chat.completion", "created": 1759600001, "model": "gpt-6.1-sol",
     "choices": [{"index": 0, "finish_reason": "stop", "message": {
         "role": "assistant",
         "content": "ORDER-123 has shipped and should arrive on 2026-10-09."}}],
     "usage": {"prompt_tokens": 139, "completion_tokens": 16, "total_tokens": 155}},
]


def main() -> None:
    replies = iter(REPLIES)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=next(replies)))
    client = openai.OpenAI(api_key="scripted", http_client=httpx.Client(transport=transport))
    out = Path(__file__).parent / "tests" / "cassettes" / "order_status.json"
    with CaptureContext(name="order_status", save_path=out), OpenAIAdapter():
        print(run_agent(client, "Where is ORDER-123?"))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
