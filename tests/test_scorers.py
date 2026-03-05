"""Tests for evalcraft.eval.scorers."""

import pytest
from evalcraft.core.models import (
    Cassette, Span, SpanKind, TokenUsage, AgentRun, EvalResult
)
from evalcraft.eval.scorers import (
    assert_tool_called,
    assert_tool_order,
    assert_no_tool_called,
    assert_output_contains,
    assert_output_matches,
    assert_cost_under,
    assert_latency_under,
    assert_token_count_under,
    Evaluator,
    _get_cassette,
)


# ──────────────────────────────────────────────
# _get_cassette helper
# ──────────────────────────────────────────────

class TestGetCassette:
    def test_returns_cassette_unchanged(self, simple_cassette):
        assert _get_cassette(simple_cassette) is simple_cassette

    def test_extracts_cassette_from_agent_run(self, simple_cassette):
        run = AgentRun(cassette=simple_cassette)
        assert _get_cassette(run) is simple_cassette


# ──────────────────────────────────────────────
# assert_tool_called
# ──────────────────────────────────────────────

class TestAssertToolCalled:
    def test_tool_was_called(self, simple_cassette):
        result = assert_tool_called(simple_cassette, "get_weather")
        assert result.passed

    def test_tool_was_not_called(self, simple_cassette):
        result = assert_tool_called(simple_cassette, "nonexistent_tool")
        assert not result.passed
        assert "nonexistent_tool" in result.message

    def test_exact_times_passes(self, simple_cassette):
        result = assert_tool_called(simple_cassette, "get_weather", times=1)
        assert result.passed

    def test_exact_times_fails(self, simple_cassette):
        result = assert_tool_called(simple_cassette, "get_weather", times=3)
        assert not result.passed

    def test_with_args_passes(self, simple_cassette):
        result = assert_tool_called(simple_cassette, "get_weather", with_args={"city": "NYC"})
        assert result.passed

    def test_with_args_fails(self, simple_cassette):
        result = assert_tool_called(simple_cassette, "get_weather", with_args={"city": "London"})
        assert not result.passed

    def test_before_constraint_passes(self, multi_tool_cassette):
        # web_search is before send_email
        result = assert_tool_called(multi_tool_cassette, "web_search", before="send_email")
        assert result.passed

    def test_before_constraint_fails(self, multi_tool_cassette):
        # send_email is NOT before web_search
        result = assert_tool_called(multi_tool_cassette, "send_email", before="web_search")
        assert not result.passed

    def test_before_tool_not_in_sequence(self, simple_cassette):
        result = assert_tool_called(simple_cassette, "get_weather", before="missing_tool")
        assert not result.passed

    def test_after_constraint_passes(self, multi_tool_cassette):
        # send_email is after web_search
        result = assert_tool_called(multi_tool_cassette, "send_email", after="web_search")
        assert result.passed

    def test_after_constraint_fails(self, multi_tool_cassette):
        # web_search is NOT after send_email
        result = assert_tool_called(multi_tool_cassette, "web_search", after="send_email")
        assert not result.passed

    def test_after_tool_not_in_sequence(self, simple_cassette):
        result = assert_tool_called(simple_cassette, "get_weather", after="missing_tool")
        assert not result.passed

    def test_accepts_agent_run(self, simple_cassette):
        run = AgentRun(cassette=simple_cassette)
        result = assert_tool_called(run, "get_weather")
        assert result.passed

    def test_assertion_name_contains_tool(self, simple_cassette):
        result = assert_tool_called(simple_cassette, "get_weather")
        assert "get_weather" in result.name


# ──────────────────────────────────────────────
# assert_tool_order
# ──────────────────────────────────────────────

class TestAssertToolOrder:
    def test_exact_order_passes(self, multi_tool_cassette):
        result = assert_tool_order(
            multi_tool_cassette,
            ["web_search", "summarize", "send_email"],
            strict=True,
        )
        assert result.passed

    def test_exact_order_fails(self, multi_tool_cassette):
        result = assert_tool_order(
            multi_tool_cassette,
            ["send_email", "web_search", "summarize"],
            strict=True,
        )
        assert not result.passed

    def test_subsequence_passes(self, multi_tool_cassette):
        result = assert_tool_order(
            multi_tool_cassette,
            ["web_search", "send_email"],  # skipping summarize
            strict=False,
        )
        assert result.passed

    def test_subsequence_fails_wrong_order(self, multi_tool_cassette):
        result = assert_tool_order(
            multi_tool_cassette,
            ["send_email", "web_search"],  # wrong order
            strict=False,
        )
        assert not result.passed

    def test_subsequence_missing_tool(self, multi_tool_cassette):
        result = assert_tool_order(
            multi_tool_cassette,
            ["web_search", "nonexistent"],
            strict=False,
        )
        assert not result.passed

    def test_empty_expected_passes(self, multi_tool_cassette):
        result = assert_tool_order(multi_tool_cassette, [], strict=False)
        assert result.passed

    def test_accepts_agent_run(self, multi_tool_cassette):
        run = AgentRun(cassette=multi_tool_cassette)
        result = assert_tool_order(run, ["web_search", "summarize", "send_email"], strict=True)
        assert result.passed


# ──────────────────────────────────────────────
# assert_no_tool_called
# ──────────────────────────────────────────────

class TestAssertNoToolCalled:
    def test_tool_not_called_passes(self, simple_cassette):
        result = assert_no_tool_called(simple_cassette, "send_email")
        assert result.passed

    def test_tool_was_called_fails(self, simple_cassette):
        result = assert_no_tool_called(simple_cassette, "get_weather")
        assert not result.passed
        assert "get_weather" in result.message

    def test_accepts_agent_run(self, simple_cassette):
        run = AgentRun(cassette=simple_cassette)
        result = assert_no_tool_called(run, "nonexistent")
        assert result.passed


# ──────────────────────────────────────────────
# assert_output_contains
# ──────────────────────────────────────────────

class TestAssertOutputContains:
    def test_contains_passes(self, simple_cassette):
        result = assert_output_contains(simple_cassette, "sunny")
        assert result.passed

    def test_not_contains_fails(self, simple_cassette):
        result = assert_output_contains(simple_cassette, "rainy")
        assert not result.passed
        assert "rainy" in result.message

    def test_case_sensitive_fails(self, simple_cassette):
        result = assert_output_contains(simple_cassette, "SUNNY", case_sensitive=True)
        assert not result.passed

    def test_case_insensitive_passes(self, simple_cassette):
        result = assert_output_contains(simple_cassette, "SUNNY", case_sensitive=False)
        assert result.passed

    def test_accepts_agent_run(self, simple_cassette):
        run = AgentRun(cassette=simple_cassette)
        result = assert_output_contains(run, "sunny")
        assert result.passed

    def test_empty_output_fails(self):
        c = Cassette()
        c.output_text = ""
        result = assert_output_contains(c, "anything")
        assert not result.passed


# ──────────────────────────────────────────────
# assert_output_matches
# ──────────────────────────────────────────────

class TestAssertOutputMatches:
    def test_pattern_matches(self, simple_cassette):
        result = assert_output_matches(simple_cassette, r"\d+°F")
        assert result.passed

    def test_pattern_no_match_fails(self, simple_cassette):
        result = assert_output_matches(simple_cassette, r"\d{4}-\d{2}-\d{2}")
        assert not result.passed

    def test_accepts_agent_run(self, simple_cassette):
        run = AgentRun(cassette=simple_cassette)
        result = assert_output_matches(run, r"sunny")
        assert result.passed

    def test_assertion_name_contains_pattern(self, simple_cassette):
        result = assert_output_matches(simple_cassette, r"sunny")
        assert "sunny" in result.name


# ──────────────────────────────────────────────
# assert_cost_under
# ──────────────────────────────────────────────

class TestAssertCostUnder:
    def test_cost_under_limit_passes(self, simple_cassette):
        result = assert_cost_under(simple_cassette, max_usd=1.0)
        assert result.passed

    def test_cost_over_limit_fails(self, simple_cassette):
        result = assert_cost_under(simple_cassette, max_usd=0.0001)
        assert not result.passed
        assert "exceeds" in result.message

    def test_cost_exactly_at_limit_passes(self, simple_cassette):
        simple_cassette.compute_metrics()
        cost = simple_cassette.total_cost_usd
        result = assert_cost_under(simple_cassette, max_usd=cost)
        assert result.passed

    def test_accepts_agent_run(self, simple_cassette):
        run = AgentRun(cassette=simple_cassette)
        result = assert_cost_under(run, max_usd=10.0)
        assert result.passed


# ──────────────────────────────────────────────
# assert_latency_under
# ──────────────────────────────────────────────

class TestAssertLatencyUnder:
    def test_latency_under_limit_passes(self, multi_tool_cassette):
        multi_tool_cassette.compute_metrics()
        result = assert_latency_under(multi_tool_cassette, max_ms=10000.0)
        assert result.passed

    def test_latency_over_limit_fails(self, multi_tool_cassette):
        multi_tool_cassette.total_duration_ms = 999999.0
        result = assert_latency_under(multi_tool_cassette, max_ms=1.0)
        assert not result.passed
        assert "exceeds" in result.message

    def test_accepts_agent_run(self, multi_tool_cassette):
        run = AgentRun(cassette=multi_tool_cassette)
        result = assert_latency_under(run, max_ms=9999999.0)
        assert result.passed


# ──────────────────────────────────────────────
# assert_token_count_under
# ──────────────────────────────────────────────

class TestAssertTokenCountUnder:
    def test_tokens_under_limit_passes(self, simple_cassette):
        result = assert_token_count_under(simple_cassette, max_tokens=1000)
        assert result.passed

    def test_tokens_over_limit_fails(self, simple_cassette):
        result = assert_token_count_under(simple_cassette, max_tokens=1)
        assert not result.passed
        assert "exceeds" in result.message

    def test_tokens_exactly_at_limit_passes(self, simple_cassette):
        simple_cassette.compute_metrics()
        tokens = simple_cassette.total_tokens
        result = assert_token_count_under(simple_cassette, max_tokens=tokens)
        assert result.passed

    def test_accepts_agent_run(self, simple_cassette):
        run = AgentRun(cassette=simple_cassette)
        result = assert_token_count_under(run, max_tokens=9999)
        assert result.passed


# ──────────────────────────────────────────────
# Evaluator
# ──────────────────────────────────────────────

class TestEvaluator:
    def test_empty_evaluator_passes(self):
        evaluator = Evaluator()
        result = evaluator.run()
        assert result.passed
        assert result.score == 1.0

    def test_all_passing_assertions(self, simple_cassette):
        evaluator = Evaluator()
        evaluator.add(assert_tool_called, simple_cassette, "get_weather")
        evaluator.add(assert_output_contains, simple_cassette, "sunny")
        result = evaluator.run()
        assert result.passed
        assert result.score == 1.0

    def test_some_failing_assertions(self, simple_cassette):
        evaluator = Evaluator()
        evaluator.add(assert_tool_called, simple_cassette, "get_weather")  # passes
        evaluator.add(assert_tool_called, simple_cassette, "nonexistent")  # fails
        result = evaluator.run()
        assert not result.passed
        assert result.score == 0.5
        assert len(result.failed_assertions) == 1

    def test_all_failing(self, simple_cassette):
        evaluator = Evaluator()
        evaluator.add(assert_tool_called, simple_cassette, "tool_a")
        evaluator.add(assert_tool_called, simple_cassette, "tool_b")
        result = evaluator.run()
        assert not result.passed
        assert result.score == 0.0

    def test_chaining_add(self, simple_cassette):
        evaluator = (
            Evaluator()
            .add(assert_tool_called, simple_cassette, "get_weather")
            .add(assert_output_contains, simple_cassette, "sunny")
        )
        result = evaluator.run()
        assert result.passed

    def test_result_contains_all_assertions(self, simple_cassette):
        evaluator = Evaluator()
        evaluator.add(assert_tool_called, simple_cassette, "get_weather")
        evaluator.add(assert_cost_under, simple_cassette, max_usd=1.0)
        result = evaluator.run()
        assert len(result.assertions) == 2

    def test_with_kwargs(self, simple_cassette):
        evaluator = Evaluator()
        evaluator.add(assert_tool_called, simple_cassette, "get_weather", times=1)
        result = evaluator.run()
        assert result.passed
