"""silent_tool_failure.py — catch the agent that quietly stopped calling its tool.

The failure this example reproduces is the one agent teams report most often:
after a model swap the agent still answers politely and the run returns
successfully, but it no longer calls the tool that did the real work. It
answers from memory instead, and because the new model re-sends a longer
prompt every turn, the run also costs three times as much.

An eval that scores only the final text passes both runs. The evalcraft
assertions below read what the agent actually did, so they pass the good run
and fail the regressed one with a message saying why. No API key or network is
needed; the two runs are recorded by hand to keep the example self-contained.

Run:
    python examples/silent_tool_failure.py
"""

from __future__ import annotations

from evalcraft import (
    CaptureContext,
    assert_cost_under,
    assert_output_contains,
    assert_tool_args_match_schema,
    assert_tool_called,
)

ORDER_ARGS_SCHEMA = {
    "type": "object",
    "required": ["order_id"],
    "properties": {"order_id": {"type": "string", "pattern": "^[0-9]+$"}},
}


def record_good_run() -> CaptureContext:
    """Baseline: the agent looks the order up, then answers."""
    with CaptureContext(name="order_status_good", agent_name="support_bot") as ctx:
        ctx.record_input("Where is order 4521?")
        ctx.record_tool_call(
            "lookup_order",
            args={"order_id": "4521"},
            result={"status": "shipped", "eta": "2026-09-26"},
        )
        ctx.record_llm_call(
            model="gpt-5.4-mini", input="Order 4521 lookup: shipped, eta 09-26",
            output="Order 4521 has shipped and should arrive on Sept 26.",
            prompt_tokens=900, completion_tokens=40, cost_usd=0.0012,
        )
        ctx.record_output("Order 4521 has shipped and should arrive on Sept 26.")
    return ctx


def record_regressed_run() -> CaptureContext:
    """After a model swap: same polite answer, no tool call, 3x the cost."""
    with CaptureContext(name="order_status_regressed", agent_name="support_bot") as ctx:
        ctx.record_input("Where is order 4521?")
        # No lookup_order call. The model answers from memory.
        ctx.record_llm_call(
            model="gpt-5.5", input="Where is order 4521?",
            output="Order 4521 has shipped and should arrive on Sept 26.",
            prompt_tokens=2700, completion_tokens=40, cost_usd=0.0036,
        )
        ctx.record_output("Order 4521 has shipped and should arrive on Sept 26.")
    return ctx


def check(label: str, ctx: CaptureContext) -> int:
    run = ctx.cassette
    checks = [
        # What an output-only eval would check. It passes for BOTH runs.
        assert_output_contains(run, "shipped"),
        # What actually matters.
        assert_tool_called(run, "lookup_order"),
        assert_tool_args_match_schema(run, "lookup_order", ORDER_ARGS_SCHEMA),
        assert_cost_under(run, max_usd=0.002),
    ]
    print(f"\n{label}")
    failed = 0
    for result in checks:
        status = "PASS" if result.passed else "FAIL"
        failed += not result.passed
        detail = f"  -> {result.message}" if result.message else ""
        print(f"  [{status}] {result.name}{detail}")
    return failed


if __name__ == "__main__":
    good_failures = check("Baseline run", record_good_run())
    bad_failures = check("After the model swap", record_regressed_run())

    print(
        "\nThe output check passed both times. The tool-call and cost checks "
        f"caught the regression ({bad_failures} failures) and passed the baseline "
        f"({good_failures} failures), with no model call and no API key."
    )
    # Exit 0 only when the demo behaves as described, so CI can run it.
    raise SystemExit(0 if good_failures == 0 and bad_failures == 3 else 1)
