"""tests/test_rag_workflow.py — Tests for the LangGraph RAG pipeline.

Verifies node execution order, citation inclusion, hallucination checking,
and performance budgets.

Run:
    pytest tests/ -v
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add the workflow directory to sys.path so we can import workflow.py
# This allows tests to run from any working directory.
_WORKFLOW_DIR = Path(__file__).parent.parent
if str(_WORKFLOW_DIR) not in sys.path:
    sys.path.insert(0, str(_WORKFLOW_DIR))

import pytest
from evalcraft import (
    replay,
    assert_output_contains,
    assert_output_matches,
    assert_cost_under,
    assert_token_count_under,
    assert_latency_under,
)
from evalcraft.core.models import SpanKind

_HERE = Path(__file__).parent

CASSETTES = {
    "remote_work": str(_HERE / "cassettes" / "remote_work_policy.json"),
    "equipment": str(_HERE / "cassettes" / "equipment_stipend.json"),
}


# ---------------------------------------------------------------------------
# Node execution assertions
# ---------------------------------------------------------------------------

class TestNodeExecution:
    """Verify every expected graph node fired during the run."""

    @pytest.mark.parametrize("scenario,cassette", CASSETTES.items())
    def test_rewrite_query_node_executed(self, scenario, cassette):
        run = replay(cassette)
        node_names = [s.name for s in run.cassette.spans if s.kind == SpanKind.AGENT_STEP]
        assert any("rewrite_query" in n for n in node_names), (
            f"[{scenario}] rewrite_query node did not execute. Nodes: {node_names}"
        )

    @pytest.mark.parametrize("scenario,cassette", CASSETTES.items())
    def test_retrieve_docs_node_executed(self, scenario, cassette):
        run = replay(cassette)
        node_names = [s.name for s in run.cassette.spans if s.kind == SpanKind.AGENT_STEP]
        assert any("retrieve_docs" in n for n in node_names), (
            f"[{scenario}] retrieve_docs node did not execute. Nodes: {node_names}"
        )

    @pytest.mark.parametrize("scenario,cassette", CASSETTES.items())
    def test_grade_relevance_node_executed(self, scenario, cassette):
        run = replay(cassette)
        node_names = [s.name for s in run.cassette.spans if s.kind == SpanKind.AGENT_STEP]
        assert any("grade_relevance" in n for n in node_names), (
            f"[{scenario}] grade_relevance node did not execute. Nodes: {node_names}"
        )

    @pytest.mark.parametrize("scenario,cassette", CASSETTES.items())
    def test_generate_answer_node_executed(self, scenario, cassette):
        run = replay(cassette)
        node_names = [s.name for s in run.cassette.spans if s.kind == SpanKind.AGENT_STEP]
        assert any("generate_answer" in n for n in node_names), (
            f"[{scenario}] generate_answer node did not execute. Nodes: {node_names}"
        )

    @pytest.mark.parametrize("scenario,cassette", CASSETTES.items())
    def test_hallucination_check_node_executed(self, scenario, cassette):
        run = replay(cassette)
        node_names = [s.name for s in run.cassette.spans if s.kind == SpanKind.AGENT_STEP]
        assert any("check_hallucination" in n for n in node_names), (
            f"[{scenario}] check_hallucination node did not execute. Nodes: {node_names}"
        )

    @pytest.mark.parametrize("scenario,cassette", CASSETTES.items())
    def test_node_order_rewrite_before_retrieve(self, scenario, cassette):
        """rewrite_query must appear before retrieve_docs in the span list."""
        run = replay(cassette)
        agent_steps = [s.name for s in run.cassette.spans if s.kind == SpanKind.AGENT_STEP]

        rewrite_idx = next((i for i, n in enumerate(agent_steps) if "rewrite_query" in n), None)
        retrieve_idx = next((i for i, n in enumerate(agent_steps) if "retrieve_docs" in n), None)

        assert rewrite_idx is not None, f"[{scenario}] rewrite_query node not found"
        assert retrieve_idx is not None, f"[{scenario}] retrieve_docs node not found"
        assert rewrite_idx < retrieve_idx, (
            f"[{scenario}] rewrite_query ({rewrite_idx}) must precede "
            f"retrieve_docs ({retrieve_idx})"
        )

    @pytest.mark.parametrize("scenario,cassette", CASSETTES.items())
    def test_generate_before_hallucination_check(self, scenario, cassette):
        run = replay(cassette)
        agent_steps = [s.name for s in run.cassette.spans if s.kind == SpanKind.AGENT_STEP]

        gen_idx = next((i for i, n in enumerate(agent_steps) if "generate_answer" in n), None)
        hall_idx = next((i for i, n in enumerate(agent_steps) if "check_hallucination" in n), None)

        assert gen_idx is not None and hall_idx is not None
        assert gen_idx < hall_idx, "generate_answer must precede check_hallucination"


# ---------------------------------------------------------------------------
# Answer quality assertions
# ---------------------------------------------------------------------------

class TestAnswerQuality:

    def test_remote_work_mentions_days(self):
        run = replay(CASSETTES["remote_work"])
        result = assert_output_contains(run, "3 days", case_sensitive=False)
        assert result.passed, result.message

    def test_remote_work_includes_citation(self):
        """Answer must cite the source document."""
        run = replay(CASSETTES["remote_work"])
        result = assert_output_matches(run, r"\[doc-\d+\]")
        assert result.passed, (
            "Answer must include at least one citation like [doc-001].\n"
            f"Got: {run.cassette.output_text[:200]}"
        )

    def test_equipment_mentions_stipend_amount(self):
        run = replay(CASSETTES["equipment"])
        result = assert_output_contains(run, "800", case_sensitive=False)
        assert result.passed, result.message

    def test_equipment_includes_citation(self):
        run = replay(CASSETTES["equipment"])
        result = assert_output_matches(run, r"\[doc-\d+\]")
        assert result.passed, result.message

    def test_equipment_mentions_eligible_items(self):
        run = replay(CASSETTES["equipment"])
        output_lower = run.cassette.output_text.lower()
        eligible_items = ["monitor", "keyboard", "webcam", "ergonomic"]
        assert any(item in output_lower for item in eligible_items), (
            f"Answer should mention eligible equipment items.\nGot: {run.cassette.output_text[:300]}"
        )


# ---------------------------------------------------------------------------
# LLM call structure validation
# ---------------------------------------------------------------------------

class TestLLMCalls:

    @pytest.mark.parametrize("scenario,cassette", CASSETTES.items())
    def test_multiple_llm_calls_per_run(self, scenario, cassette):
        """Pipeline should make at least 3 LLM calls (rewrite, grade, generate, check)."""
        run = replay(cassette)
        assert run.cassette.llm_call_count >= 3, (
            f"[{scenario}] Expected >=3 LLM calls, got {run.cassette.llm_call_count}"
        )

    @pytest.mark.parametrize("scenario,cassette", CASSETTES.items())
    def test_no_tool_calls_in_rag_pipeline(self, scenario, cassette):
        """RAG pipeline uses LLM node calls, not tool calls (tools are in the nodes)."""
        run = replay(cassette)
        # The RAG pipeline embeds tool-like behavior in nodes, not OpenAI function calls
        # This documents and enforces the architectural decision
        assert run.cassette.tool_call_count == 0, (
            f"[{scenario}] Expected 0 tool calls (RAG uses node steps), "
            f"got {run.cassette.tool_call_count}"
        )


# ---------------------------------------------------------------------------
# Budget and performance
# ---------------------------------------------------------------------------

class TestPerformance:

    @pytest.mark.parametrize("scenario,cassette", CASSETTES.items())
    def test_cost_budget(self, scenario, cassette):
        run = replay(cassette)
        result = assert_cost_under(run, max_usd=0.05)
        assert result.passed, f"[{scenario}] {result.message}"

    @pytest.mark.parametrize("scenario,cassette", CASSETTES.items())
    def test_token_budget(self, scenario, cassette):
        run = replay(cassette)
        result = assert_token_count_under(run, max_tokens=5000)
        assert result.passed, f"[{scenario}] {result.message}"


# ---------------------------------------------------------------------------
# Mock-based node-level unit tests
# ---------------------------------------------------------------------------

def test_retrieve_docs_node_direct():
    """Test the retrieval function directly — no LLM, no capture context."""
    from workflow import retrieve_documents

    results = retrieve_documents("remote work days per week", top_k=2)

    assert len(results) >= 1, "Should retrieve at least one document"
    assert any("Remote Work Policy" in d["title"] for d in results), (
        "Should retrieve the Remote Work Policy document"
    )


def test_full_pipeline_with_mocks():
    """End-to-end pipeline test using MockLLM for all LLM calls.

    Uses pattern-based responses so each node type gets the right reply
    regardless of how many documents are retrieved.
    """
    from evalcraft import CaptureContext, MockLLM
    from workflow import retrieve_documents

    llm = MockLLM(model="gpt-4o-mini")

    # Use pattern matching to route each prompt type to the right response.
    # This is more robust than sequential responses when the number of
    # grading calls depends on retrieval results.
    llm.add_pattern_response(
        r"Rewrite:",
        "equipment allowance stipend amount annual limit",
        prompt_tokens=68, completion_tokens=10,
    )
    llm.add_pattern_response(
        r"Is this relevant\?",
        "yes",
        prompt_tokens=140, completion_tokens=1,
    )
    llm.add_pattern_response(
        r"Answer:",
        "According to the Equipment Policy v1.1 [doc-002], the annual stipend is $800.",
        prompt_tokens=350, completion_tokens=25,
    )
    llm.add_pattern_response(
        r"Is this grounded\?",
        "yes",
        prompt_tokens=55, completion_tokens=1,
    )

    with CaptureContext(
        name="mock_rag_pipeline",
        agent_name="rag_pipeline",
        framework="langgraph",
    ) as ctx:
        ctx.record_input("What is the equipment stipend?")

        # Node 1: rewrite_query
        rewrite_response = llm.complete("Rewrite: What is the equipment stipend?")
        rewritten = rewrite_response.content

        # Node 2: retrieve_docs (pure Python — no LLM)
        docs = retrieve_documents(rewritten, top_k=3)

        # Node 3: grade_relevance — one LLM call per retrieved doc
        graded = []
        for doc in docs:
            grade = llm.complete(f"Is this relevant? {doc['content'][:100]}")
            if grade.content.strip().lower().startswith("yes"):
                graded.append(doc)

        # Node 4: generate_answer
        docs_text = "\n".join(f"[{d['id']}] {d['content']}" for d in graded)
        answer_response = llm.complete(f"Answer: What is the equipment stipend?\nDocs: {docs_text}")
        answer = answer_response.content

        # Node 5: check_hallucination
        grounded_response = llm.complete(f"Is this grounded? {answer}")
        is_grounded = grounded_response.content.strip().lower().startswith("yes")

        ctx.record_output(answer)

    # Total calls: 1 (rewrite) + len(docs) (grade) + 1 (generate) + 1 (check)
    expected_calls = 1 + len(docs) + 1 + 1
    llm.assert_called(times=expected_calls)

    # Verify cassette quality
    cassette = ctx.cassette
    assert cassette.llm_call_count >= 3
    assert "800" in cassette.output_text, (
        f"Answer should mention $800 stipend. Got: {cassette.output_text}"
    )
    assert "[doc-" in cassette.output_text, (
        "Answer should include a document citation like [doc-002]."
    )

    result = assert_cost_under(cassette, max_usd=0.10)
    assert result.passed, result.message
