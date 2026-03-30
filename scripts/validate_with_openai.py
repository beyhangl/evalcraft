#!/usr/bin/env python3
"""Validate evalcraft with REAL OpenAI API calls.

Run this script with your API key to prove the entire pipeline works
with a live LLM — not mocks, not hand-crafted cassettes.

Usage:
    export OPENAI_API_KEY=sk-...
    python scripts/validate_with_openai.py

What it does:
    1. Records a real agent run with live gpt-4o-mini calls (tool calling)
    2. Saves the cassette to disk
    3. Replays the cassette (zero API calls)
    4. Runs all assertion types against the replay
    5. Creates a golden set baseline
    6. Checks for regressions
    7. Prints a full validation report
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

# Ensure evalcraft is importable
sys.path.insert(0, str(Path(__file__).parent.parent))


def main():
    # Check for API key
    if not os.environ.get("OPENAI_API_KEY"):
        print("❌ OPENAI_API_KEY not set. Run:")
        print("   export OPENAI_API_KEY=sk-...")
        print("   python scripts/validate_with_openai.py")
        sys.exit(1)

    try:
        import openai
    except ImportError:
        print("❌ openai package not installed. Run: pip install openai")
        sys.exit(1)

    from evalcraft import (
        CaptureContext,
        replay,
        assert_tool_called,
        assert_tool_order,
        assert_output_contains,
        assert_cost_under,
        assert_token_count_under,
    )
    from evalcraft.adapters.openai_adapter import OpenAIAdapter
    from evalcraft.eval.scorers import Evaluator
    from evalcraft.golden.manager import GoldenSet
    from evalcraft.regression.detector import RegressionDetector
    from evalcraft.replay.engine import ReplayDiff

    # Import the example agent
    sys.path.insert(0, str(Path(__file__).parent.parent / "examples" / "openai-agent"))
    from agent import run_support_agent

    tmpdir = Path(tempfile.mkdtemp(prefix="evalcraft-validation-"))
    cassette_path = tmpdir / "order_tracking.json"
    golden_path = tmpdir / "support.golden.json"

    passed = 0
    failed = 0
    total = 0

    def check(name: str, condition: bool, detail: str = ""):
        nonlocal passed, failed, total
        total += 1
        if condition:
            passed += 1
            print(f"  ✅ {name}")
        else:
            failed += 1
            print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))

    print("=" * 60)
    print("  EVALCRAFT LIVE VALIDATION")
    print("=" * 60)
    print()

    # ── Step 1: Record a REAL agent run ──────────────────────────────────
    print("📹 Step 1: Recording real agent run with OpenAI...")
    print("   Using gpt-4.1-mini (recommended) with fallback to gpt-4o-mini")
    client = openai.OpenAI()

    # Detect best available model
    model = "gpt-4.1-mini"
    try:
        client.chat.completions.create(model=model, messages=[{"role": "user", "content": "hi"}], max_tokens=1)
    except Exception:
        model = "gpt-4o-mini"
        print(f"   gpt-4.1-mini not available, falling back to {model}")

    with CaptureContext(
        name="order_tracking",
        agent_name="support_agent",
        framework="openai",
        save_path=str(cassette_path),
    ) as ctx:
        with OpenAIAdapter():
            ctx.record_input("Hi! I placed order ORD-1042 last week. Can you tell me where it is?")
            answer = run_support_agent(client, "Hi! I placed order ORD-1042 last week. Can you tell me where it is?")
            ctx.record_output(answer)

    print(f"   Saved to: {cassette_path}")
    print()

    # ── Step 2: Verify cassette on disk ──────────────────────────────────
    print("💾 Step 2: Verifying cassette file...")
    check("Cassette file exists", cassette_path.exists())
    data = json.loads(cassette_path.read_text())
    check("Valid JSON with evalcraft_version", data.get("evalcraft_version") == "0.1.0")
    check("Has spans", len(data.get("spans", [])) > 0, f"got {len(data.get('spans', []))} spans")
    check("Has fingerprint", bool(data.get("cassette", {}).get("fingerprint")))

    cassette_meta = data.get("cassette", {})
    print(f"   Tokens: {cassette_meta.get('total_tokens', 0)}")
    print(f"   Cost: ${cassette_meta.get('total_cost_usd', 0):.6f}")
    print(f"   LLM calls: {cassette_meta.get('llm_call_count', 0)}")
    print(f"   Tool calls: {cassette_meta.get('tool_call_count', 0)}")
    print(f"   Duration: {cassette_meta.get('total_duration_ms', 0):.0f}ms")
    print()

    # ── Step 3: Replay (zero API calls) ──────────────────────────────────
    print("🔁 Step 3: Replaying cassette (zero API calls)...")
    run = replay(str(cassette_path))
    check("Replay succeeded", run.replayed)
    check("Output preserved", len(run.cassette.output_text) > 0)
    check("Spans preserved", len(run.cassette.spans) > 0)
    print(f"   Output: {run.cassette.output_text[:100]}...")
    print()

    # ── Step 4: Run ALL assertion types ──────────────────────────────────
    print("🧪 Step 4: Running assertions on replayed cassette...")

    # Tool assertions
    r = assert_tool_called(run, "lookup_order")
    check("assert_tool_called(lookup_order)", r.passed, r.message)

    r = assert_tool_called(run, "lookup_order", with_args={"order_id": "ORD-1042"})
    check("assert_tool_called(lookup_order, with_args)", r.passed, r.message)

    r = assert_tool_called(run, "search_knowledge_base")
    if r.passed:
        check("assert_tool_called(search_knowledge_base)", True)
    else:
        # LLM may skip KB search if order lookup is sufficient — this is fine
        print(f"  ⚠️  assert_tool_called(search_knowledge_base) — skipped by LLM (non-deterministic, OK)")

    # Output assertions
    r = assert_output_contains(run, "ORD-1042")
    check("assert_output_contains(ORD-1042)", r.passed, r.message)

    # Cost/performance assertions
    r = assert_cost_under(run, max_usd=0.05)
    check("assert_cost_under($0.05)", r.passed, r.message)

    r = assert_token_count_under(run, max_tokens=5000)
    check("assert_token_count_under(5000)", r.passed, r.message)

    # Composite evaluator
    evaluator = Evaluator()
    evaluator.add(assert_tool_called, run, "lookup_order")
    evaluator.add(assert_output_contains, run, "ORD-1042")
    evaluator.add(assert_cost_under, run, max_usd=0.05)
    eval_result = evaluator.run()
    check("Composite evaluator", eval_result.passed, f"score={eval_result.score:.2f}")
    print()

    # ── Step 5: Golden set ───────────────────────────────────────────────
    print("🏆 Step 5: Creating golden set baseline...")
    gs = GoldenSet(name="support_agent", description="Live validation baseline")
    gs.add_cassette(run.cassette)
    gs.save(golden_path)
    check("Golden set saved", golden_path.exists())

    loaded_gs = GoldenSet.load(golden_path)
    check("Golden set loadable", loaded_gs.name == "support_agent")
    check("Golden set has cassettes", loaded_gs.cassette_count == 1)
    print()

    # ── Step 6: Regression detection ─────────────────────────────────────
    print("🔍 Step 6: Regression detection (same cassette = no regression)...")
    from evalcraft import Cassette
    c_reloaded = Cassette.load(cassette_path)
    detector = RegressionDetector()
    report = detector.compare(run.cassette, c_reloaded)
    check("No critical regressions", not report.has_critical)
    print()

    # ── Step 7: Diff ─────────────────────────────────────────────────────
    print("📊 Step 7: Cassette diff (self-compare)...")
    diff = ReplayDiff.compute(run.cassette, c_reloaded)
    check("No tool sequence change (self-diff)", not diff.tool_sequence_changed)
    check("No output change (self-diff)", not diff.output_changed)
    print()

    # ── Summary ──────────────────────────────────────────────────────────
    print("=" * 60)
    if failed == 0:
        print(f"  ✅ ALL {total} CHECKS PASSED")
        print()
        print("  evalcraft is validated with real OpenAI API calls.")
        print(f"  Cassettes saved to: {tmpdir}")
    else:
        print(f"  ❌ {failed}/{total} CHECKS FAILED")
        print()
        print("  Some validations did not pass. Check the output above.")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
