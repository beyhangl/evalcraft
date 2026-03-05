"""tests/test_support_agent.py — Regression tests for the ShopEasy support agent.

These tests replay pre-recorded cassettes — no API key, no network calls, zero cost.
Run them in CI just like any other pytest suite:

    pytest tests/ -v

To regenerate cassettes from a live agent run:
    OPENAI_API_KEY=sk-... python record_cassettes.py
"""

from __future__ import annotations

from pathlib import Path
import pytest
from evalcraft import (
    replay,
    assert_tool_called,
    assert_tool_order,
    assert_no_tool_called,
    assert_output_contains,
    assert_cost_under,
    assert_token_count_under,
)
from evalcraft.eval.scorers import Evaluator

# Resolve cassette paths relative to this test file so tests can be run
# from any working directory (repo root, the example dir, or CI).
_HERE = Path(__file__).parent

CASSETTES = {
    "order_tracking": str(_HERE / "cassettes" / "order_tracking.json"),
    "return_request": str(_HERE / "cassettes" / "return_request.json"),
    "damaged_item": str(_HERE / "cassettes" / "damaged_item.json"),
}


# ---------------------------------------------------------------------------
# Order tracking scenario
# ---------------------------------------------------------------------------

class TestOrderTracking:
    """Agent should look up the order and consult the knowledge base."""

    def test_lookup_order_called(self):
        run = replay(CASSETTES["order_tracking"])
        result = assert_tool_called(run, "lookup_order")
        assert result.passed, result.message

    def test_lookup_order_correct_id(self):
        run = replay(CASSETTES["order_tracking"])
        result = assert_tool_called(run, "lookup_order", with_args={"order_id": "ORD-1042"})
        assert result.passed, result.message

    def test_knowledge_base_consulted(self):
        run = replay(CASSETTES["order_tracking"])
        result = assert_tool_called(run, "search_knowledge_base")
        assert result.passed, result.message

    def test_tool_order_lookup_before_synthesis(self):
        """Order lookup must happen before the final LLM synthesis."""
        run = replay(CASSETTES["order_tracking"])
        result = assert_tool_order(run, ["lookup_order", "search_knowledge_base"])
        assert result.passed, result.message

    def test_output_mentions_tracking_number(self):
        run = replay(CASSETTES["order_tracking"])
        result = assert_output_contains(run, "UPS")
        assert result.passed, result.message

    def test_output_mentions_order_id(self):
        run = replay(CASSETTES["order_tracking"])
        result = assert_output_contains(run, "ORD-1042")
        assert result.passed, result.message

    def test_cost_budget(self):
        run = replay(CASSETTES["order_tracking"])
        result = assert_cost_under(run, max_usd=0.01)
        assert result.passed, result.message

    def test_token_budget(self):
        run = replay(CASSETTES["order_tracking"])
        result = assert_token_count_under(run, max_tokens=1000)
        assert result.passed, result.message


# ---------------------------------------------------------------------------
# Return request scenario
# ---------------------------------------------------------------------------

class TestReturnRequest:
    """Agent should identify the order and explain the return policy."""

    def test_lookup_order_called(self):
        run = replay(CASSETTES["return_request"])
        result = assert_tool_called(run, "lookup_order", with_args={"order_id": "ORD-9873"})
        assert result.passed, result.message

    def test_return_policy_searched(self):
        run = replay(CASSETTES["return_request"])
        result = assert_tool_called(run, "search_knowledge_base")
        assert result.passed, result.message

    def test_output_mentions_return(self):
        run = replay(CASSETTES["return_request"])
        result = assert_output_contains(run, "Return Item", case_sensitive=False)
        assert result.passed, result.message

    def test_output_mentions_refund_timeline(self):
        run = replay(CASSETTES["return_request"])
        result = assert_output_contains(run, "5-7 business days", case_sensitive=False)
        assert result.passed, result.message

    def test_cost_budget(self):
        run = replay(CASSETTES["return_request"])
        result = assert_cost_under(run, max_usd=0.01)
        assert result.passed, result.message


# ---------------------------------------------------------------------------
# Damaged item scenario
# ---------------------------------------------------------------------------

class TestDamagedItem:
    """Agent should show empathy and offer replacement or refund."""

    def test_order_looked_up(self):
        run = replay(CASSETTES["damaged_item"])
        result = assert_tool_called(run, "lookup_order")
        assert result.passed, result.message

    def test_damage_policy_searched(self):
        run = replay(CASSETTES["damaged_item"])
        result = assert_tool_called(run, "search_knowledge_base")
        assert result.passed, result.message

    def test_output_offers_resolution(self):
        """Agent must offer replacement or refund — non-negotiable brand requirement."""
        run = replay(CASSETTES["damaged_item"])
        output = run.cassette.output_text.lower()
        assert "replacement" in output or "refund" in output, (
            f"Agent output did not offer replacement or refund.\nGot: {run.cassette.output_text}"
        )

    def test_cost_budget(self):
        run = replay(CASSETTES["damaged_item"])
        result = assert_cost_under(run, max_usd=0.01)
        assert result.passed, result.message


# ---------------------------------------------------------------------------
# Composite evaluator example
# ---------------------------------------------------------------------------

def test_order_tracking_composite_eval():
    """Use the Evaluator to bundle multiple assertions into one test."""
    run = replay(CASSETTES["order_tracking"])

    eval_result = (
        Evaluator()
        .add(assert_tool_called, run, "lookup_order")
        .add(assert_tool_called, run, "search_knowledge_base")
        .add(assert_cost_under, run, max_usd=0.01)
        .add(assert_token_count_under, run, max_tokens=1000)
        .run()
    )

    assert eval_result.passed, (
        f"Composite eval failed (score={eval_result.score:.0%}):\n"
        + "\n".join(
            f"  FAIL: {a.name} — {a.message}"
            for a in eval_result.assertions
            if not a.passed
        )
    )


# ---------------------------------------------------------------------------
# Mock-based unit tests (no cassette file needed)
# ---------------------------------------------------------------------------

def test_agent_with_mocks():
    """Unit test using MockLLM and MockTool — fully self-contained, no files."""
    from evalcraft import CaptureContext, MockLLM, MockTool

    kb_tool = MockTool("search_knowledge_base")
    kb_tool.returns([{
        "id": "kb-001",
        "title": "How to track your order",
        "content": "Visit 'My Orders' and enter your order number.",
    }])

    order_tool = MockTool("lookup_order")
    order_tool.returns({
        "id": "ORD-5555",
        "status": "shipped",
        "carrier": "FedEx",
        "tracking": "123456789012",
    })

    llm = MockLLM()
    llm.add_response(
        "*",
        "Your order ORD-5555 is on its way via FedEx. "
        "Track it with number 123456789012. Is there anything else I can help with?",
        prompt_tokens=250,
        completion_tokens=35,
    )

    with CaptureContext(name="mock_support_test") as ctx:
        ctx.record_input("Where is my order ORD-5555?")

        kb_result = kb_tool.call(query="order tracking")
        order_result = order_tool.call(order_id="ORD-5555")

        response = llm.complete(
            f"KB: {kb_result}\nOrder: {order_result}\nAnswer the customer's question."
        )
        ctx.record_output(response.content)

    # Verify mocks were called correctly
    kb_tool.assert_called(times=1)
    order_tool.assert_called(times=1)
    order_tool.assert_called_with(order_id="ORD-5555")
    llm.assert_called(times=1)

    # Verify cassette contents
    cassette = ctx.cassette
    assert cassette.tool_call_count == 2
    assert cassette.llm_call_count == 1
    assert "FedEx" in cassette.output_text

    result = assert_cost_under(cassette, max_usd=0.10)
    assert result.passed, result.message
