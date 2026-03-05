"""record_cassettes.py — Capture live agent runs into cassettes.

Run this script ONCE (with a real OPENAI_API_KEY) to produce the cassette
files that your test suite replays for free.

Usage:
    OPENAI_API_KEY=sk-... python record_cassettes.py

Cassettes are saved to tests/cassettes/ and should be committed to git.
After that, tests/ never need a real API key again.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Imports — guard against missing openai
# ---------------------------------------------------------------------------
try:
    import openai
except ImportError:
    sys.exit("openai not installed. Run: pip install -r requirements.txt")

from evalcraft import CaptureContext
from evalcraft.adapters import OpenAIAdapter
from agent import run_support_agent


CASSETTES_DIR = Path(__file__).parent / "tests" / "cassettes"
CASSETTES_DIR.mkdir(parents=True, exist_ok=True)


def record_scenario(
    client: openai.OpenAI,
    scenario_name: str,
    user_message: str,
) -> None:
    """Record one support scenario into a cassette file."""
    cassette_path = CASSETTES_DIR / f"{scenario_name}.json"

    print(f"\n--- Recording: {scenario_name} ---")
    print(f"Customer: {user_message}")

    with CaptureContext(
        name=scenario_name,
        agent_name="support_agent",
        framework="openai",
        save_path=cassette_path,
    ) as ctx:
        ctx.record_input(user_message)

        with OpenAIAdapter():
            answer = run_support_agent(client, user_message)

        ctx.record_output(answer)

    c = ctx.cassette
    print(f"Agent:    {answer[:120]}...")
    print(f"Spans:    {len(c.spans)}")
    print(f"Tokens:   {c.total_tokens}")
    print(f"Cost:     ${c.total_cost_usd:.5f}")
    print(f"Saved:    {cassette_path}")


def main() -> None:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        sys.exit("Set OPENAI_API_KEY environment variable before recording.")

    client = openai.OpenAI(api_key=api_key)

    scenarios = [
        (
            "order_tracking",
            "Hi! I placed order ORD-1042 last week. Can you tell me where it is?",
        ),
        (
            "return_request",
            "I need to return a USB-C Hub from order ORD-9873. What's the process?",
        ),
        (
            "damaged_item",
            "My package arrived and the wireless headphones are broken. Order ORD-1042.",
        ),
    ]

    for name, message in scenarios:
        record_scenario(client, name, message)

    print(f"\nAll cassettes saved to {CASSETTES_DIR}")
    print("Commit these files to git — tests will replay without any API key.")


if __name__ == "__main__":
    main()
