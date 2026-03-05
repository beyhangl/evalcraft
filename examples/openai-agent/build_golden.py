"""build_golden.py — Create the golden set from recorded cassettes.

Run this after record_cassettes.py to promote the cassettes to a golden set.
The golden set becomes the regression baseline: future runs are compared
against it and fail if they deviate significantly.

Usage:
    python build_golden.py
"""

from __future__ import annotations

from pathlib import Path

from evalcraft import GoldenSet
from evalcraft.golden.manager import Thresholds
from evalcraft.core.models import Cassette


CASSETTES_DIR = Path(__file__).parent / "tests" / "cassettes"
GOLDEN_DIR = Path(__file__).parent / "golden"
GOLDEN_DIR.mkdir(parents=True, exist_ok=True)


def main() -> None:
    golden = GoldenSet(
        name="support_agent_v1",
        description=(
            "Golden set for the ShopEasy customer support agent. "
            "Validates tool-call sequence and cost budgets."
        ),
        thresholds=Thresholds(
            tool_sequence_must_match=True,
            output_must_match=False,         # LLM wording varies — do NOT lock text
            max_token_increase_ratio=1.5,    # allow up to 50% more tokens
            max_cost_increase_ratio=2.0,     # allow up to 2x cost
            max_latency_increase_ratio=None, # skip latency (CI machines vary)
            max_cost_usd=0.02,               # hard cap per run
        ),
    )

    cassette_files = sorted(CASSETTES_DIR.glob("*.json"))
    if not cassette_files:
        print(f"No cassettes found in {CASSETTES_DIR}.")
        print("Run record_cassettes.py first to capture live runs.")
        return

    for path in cassette_files:
        cassette = Cassette.load(path)
        golden.add_cassette(cassette)
        print(f"  Added cassette: {cassette.name}  ({cassette.total_tokens} tokens)")

    out_path = GOLDEN_DIR / "support_agent.golden.json"
    golden.save(out_path)
    print(f"\nGolden set saved: {out_path}")
    print(f"  Cassettes: {golden.cassette_count}")
    print(f"  Version:   {golden.version}")
    print("\nCommit golden/ to git — tests compare against this baseline.")


if __name__ == "__main__":
    main()
