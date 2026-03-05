"""record_cassettes.py — Capture live code-review agent runs into cassettes.

Run once with a real ANTHROPIC_API_KEY to generate cassette files.

Usage:
    ANTHROPIC_API_KEY=sk-ant-... python record_cassettes.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    import anthropic
except ImportError:
    sys.exit("anthropic not installed. Run: pip install -r requirements.txt")

from evalcraft import CaptureContext
from evalcraft.adapters import AnthropicAdapter
from agent import run_code_review_agent


CASSETTES_DIR = Path(__file__).parent / "tests" / "cassettes"
CASSETTES_DIR.mkdir(parents=True, exist_ok=True)


def record_review(
    client: anthropic.Anthropic,
    scenario_name: str,
    repo: str,
    pr_number: int,
) -> None:
    print(f"\n--- Recording: {scenario_name} (PR #{pr_number}) ---")

    cassette_path = CASSETTES_DIR / f"{scenario_name}.json"

    with CaptureContext(
        name=scenario_name,
        agent_name="code_review_agent",
        framework="anthropic",
        save_path=cassette_path,
    ) as ctx:
        ctx.record_input(f"Review PR #{pr_number} in {repo}")

        with AnthropicAdapter():
            review = run_code_review_agent(client, repo, pr_number)

        ctx.record_output(review)

    c = ctx.cassette
    print(f"Review snippet: {review[:150]}...")
    print(f"LLM calls:  {c.llm_call_count}")
    print(f"Tool calls: {c.tool_call_count}")
    print(f"Tokens:     {c.total_tokens}")
    print(f"Cost:       ${c.total_cost_usd:.5f}")
    print(f"Saved:      {cassette_path}")


def main() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("Set ANTHROPIC_API_KEY environment variable before recording.")

    client = anthropic.Anthropic(api_key=api_key)

    scenarios = [
        ("auth_middleware_review", "myorg/backend", 101),
        ("db_pool_refactor_review", "myorg/backend", 102),
    ]

    for name, repo, pr_number in scenarios:
        record_review(client, name, repo, pr_number)

    print(f"\nAll cassettes saved to {CASSETTES_DIR}")
    print("Commit these files — tests replay without any API key.")


if __name__ == "__main__":
    main()
