"""Tests for deterministic loop / repetition detection scorers.

All offline, deterministic, $0 — they inspect only the recorded spans and never
call a model.
"""

import json

import pytest

from evalcraft import (
    assert_no_loops,
    assert_no_repeated_tool_calls,
    detect_loops,
)
from evalcraft.core.models import AgentRun, Cassette, Span, SpanKind


def _tool(name: str, args: dict) -> Span:
    return Span(kind=SpanKind.TOOL_CALL, name=f"tool:{name}", tool_name=name, tool_args=args)


def _llm(output: str) -> Span:
    return Span(kind=SpanKind.LLM_RESPONSE, name="llm", model="m", output=output)


def _step(name: str, output: str) -> Span:
    return Span(kind=SpanKind.AGENT_STEP, name=name, output=output)


def _cassette(spans: list[Span]) -> Cassette:
    c = Cassette(name="t", agent_name="a")
    for s in spans:
        c.add_span(s)
    c.output_text = "done"
    return c


# ── repeated tool calls ──────────────────────────────────────────────────────

class TestRepeatedToolCalls:
    def test_identical_calls_over_threshold_flagged(self):
        c = _cassette([_tool("search", {"q": "x"}) for _ in range(3)])
        r = assert_no_repeated_tool_calls(c)  # default max_repeats=2
        assert r.passed is False
        assert "search" in r.message

    def test_at_threshold_passes(self):
        c = _cassette([_tool("search", {"q": "x"}) for _ in range(2)])
        assert assert_no_repeated_tool_calls(c, max_repeats=2).passed

    def test_distinct_args_not_a_loop(self):
        c = _cassette([_tool("search", {"q": f"q{i}"}) for i in range(5)])
        assert assert_no_repeated_tool_calls(c).passed

    def test_args_order_insensitive(self):
        # same args in different dict order must count as the same call
        c = _cassette([
            _tool("f", {"a": 1, "b": 2}),
            _tool("f", {"b": 2, "a": 1}),
            _tool("f", {"a": 1, "b": 2}),
        ])
        r = assert_no_repeated_tool_calls(c, max_repeats=2)
        assert r.passed is False and r.actual[0]["count"] == 3

    def test_max_repeats_param(self):
        c = _cassette([_tool("search", {"q": "x"}) for _ in range(4)])
        assert assert_no_repeated_tool_calls(c, max_repeats=4).passed
        assert assert_no_repeated_tool_calls(c, max_repeats=3).passed is False


# ── repeated outputs ─────────────────────────────────────────────────────────

class TestRepeatedOutputs:
    def test_exact_repeat_flagged(self):
        c = _cassette([_llm("I am thinking.") for _ in range(3)])
        r = assert_no_loops(c)
        assert r.passed is False
        assert any(f["kind"] == "repeated_output" for f in r.actual)

    def test_whitespace_normalised(self):
        c = _cassette([_llm("the  answer"), _llm("the answer"), _llm("the   answer")])
        assert assert_no_loops(c).passed is False  # all normalise to "the answer"

    def test_distinct_outputs_pass(self):
        c = _cassette([_llm(f"step {i} reasoning") for i in range(5)])
        assert assert_no_loops(c).passed

    def test_near_duplicate_only_with_similarity(self):
        c = _cassette([
            _llm("The answer is 42 today"),
            _llm("The answer is 42 now"),
            _llm("The answer is 42 here"),
        ])
        assert assert_no_loops(c).passed  # exact-only: all distinct
        assert assert_no_loops(c, similarity=0.6).passed is False  # near-dup loop

    def test_similarity_out_of_range_raises(self):
        c = _cassette([_llm("a")])
        with pytest.raises(ValueError, match="similarity"):
            detect_loops(c, similarity=0.0)
        with pytest.raises(ValueError, match="similarity"):
            detect_loops(c, similarity=1.5)


class TestNearDuplicateCorrectness:
    """Regression tests for the adversarial-review findings."""

    DRIFT = [
        "alpha beta gamma delta",
        "beta gamma delta epsilon",   # ~0.67 to prev, ~0.33 to first
        "gamma delta epsilon zeta",
        "delta epsilon zeta eta",     # ~0.14 to first
    ]

    def test_gradual_drift_chain_is_caught(self):
        # Each step is near its neighbour but not the first — single-linkage must
        # connect the whole chain (greedy first-member clustering would miss it).
        c = _cassette([_llm(s) for s in self.DRIFT])
        r = assert_no_loops(c, similarity=0.6)
        assert r.passed is False
        assert r.actual[0]["count"] == 4

    def test_drift_detection_is_order_independent(self):
        a = detect_loops(_cassette([_llm(s) for s in self.DRIFT]), similarity=0.6)
        b = detect_loops(_cassette([_llm(s) for s in reversed(self.DRIFT)]), similarity=0.6)
        assert a.has_loops and b.has_loops
        assert a.findings[0].count == b.findings[0].count == 4

    def test_symbol_only_outputs_not_falsely_merged(self):
        # distinct punctuation-only outputs tokenize to empty sets — must NOT merge
        c = _cassette([_llm("!!!"), _llm("???"), _llm("***")])
        assert assert_no_loops(c, similarity=0.6).passed

    def test_identical_symbol_only_outputs_still_caught(self):
        c = _cassette([_llm("!!!"), _llm("!!!"), _llm("!!!")])
        assert assert_no_loops(c, similarity=0.6).passed is False


class TestCrossKindEcho:
    """A single answer echoed under differently-named lifecycle spans is not a loop."""

    def test_differently_named_echo_not_a_loop(self):
        # mirrors the CrewAI adapter: one final answer recorded under 3 names
        c = _cassette([
            _step("agent:finish", "Final answer is 42."),
            _step("task:solve", "Final answer is 42."),
            _step("crew:kickoff", "Final answer is 42."),
        ])
        assert assert_no_loops(c).passed                      # exact
        assert assert_no_loops(c, similarity=0.6).passed      # near-dup

    def test_same_named_repeat_is_a_loop(self):
        # the same step name repeating identical output IS a loop
        c = _cassette([_step("agent:finish", "thinking…") for _ in range(3)])
        assert assert_no_loops(c).passed is False

    def test_case_consistent_across_modes(self):
        # "Done"/"done"/"DONE" is the same loop in both exact and near-dup modes
        c = _cassette([_llm("Done"), _llm("done"), _llm("DONE")])
        assert assert_no_loops(c).passed is False              # exact (case-insensitive)
        assert assert_no_loops(c, similarity=0.6).passed is False  # near-dup


# ── detect_loops / report ────────────────────────────────────────────────────

class TestDetectLoops:
    def test_report_aggregates_both_signals(self):
        spans = [_tool("search", {"q": "x"}) for _ in range(3)] + [_llm("same") for _ in range(3)]
        report = detect_loops(_cassette(spans))
        kinds = sorted({f.kind for f in report.findings})
        assert report.has_loops
        assert kinds == ["repeated_output", "repeated_tool_call"]

    def test_clean_report_has_no_loops(self):
        report = detect_loops(_cassette([_tool("a", {"i": 1}), _tool("b", {"i": 2})]))
        assert report.has_loops is False and report.findings == []

    def test_report_to_dict(self):
        report = detect_loops(_cassette([_tool("s", {"q": "x"}) for _ in range(3)]))
        d = report.to_dict()
        assert d["has_loops"] is True
        assert d["findings"][0]["kind"] == "repeated_tool_call"
        assert set(d["findings"][0]) == {"kind", "signature", "count", "max_allowed"}

    def test_thresholds_independent(self):
        # 3 identical tool calls + 3 identical outputs; relax only the tool side
        spans = [_tool("s", {"q": "x"}) for _ in range(3)] + [_llm("same") for _ in range(3)]
        r = detect_loops(_cassette(spans), max_tool_repeats=5, max_step_repeats=2)
        assert [f.kind for f in r.findings] == ["repeated_output"]


# ── guarantees ───────────────────────────────────────────────────────────────

class TestGuarantees:
    def test_empty_cassette_passes(self):
        assert assert_no_loops(Cassette(name="empty")).passed
        assert assert_no_repeated_tool_calls(Cassette(name="empty")).passed

    def test_accepts_agentrun(self):
        c = _cassette([_tool("s", {"q": "x"}) for _ in range(3)])
        run = AgentRun(cassette=c)
        assert assert_no_loops(run).passed is False
        assert assert_no_repeated_tool_calls(run).passed is False

    def test_deterministic_byte_identical(self):
        c = _cassette([_tool("s", {"q": "x"}) for _ in range(3)] + [_llm("same")] * 3)
        a = assert_no_loops(c).to_dict()
        b = assert_no_loops(c).to_dict()
        assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)

    def test_passing_result_has_no_message(self):
        r = assert_no_loops(_cassette([_tool("a", {"i": 1})]))
        assert r.passed and r.message == ""
