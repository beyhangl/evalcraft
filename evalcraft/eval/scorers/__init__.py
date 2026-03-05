"""Eval scorers — assertions and scoring functions for agent runs.

Usage:
    from evalcraft import assert_tool_called, assert_tool_order, assert_cost_under

    # From a cassette
    cassette = Cassette.load("test.json")

    assert_tool_called(cassette, "web_search")
    assert_tool_order(cassette, ["web_search", "summarize", "send_email"])
    assert_cost_under(cassette, max_usd=0.05)
"""

from __future__ import annotations

import re
from typing import Any

from evalcraft.core.models import (
    Cassette,
    Span,
    SpanKind,
    AgentRun,
    EvalResult,
    AssertionResult,
)


# ──────────────────────────────────────────────
# Tool assertions
# ──────────────────────────────────────────────

def assert_tool_called(
    cassette: Cassette | AgentRun,
    tool_name: str,
    times: int | None = None,
    with_args: dict | None = None,
    before: str | None = None,
    after: str | None = None,
) -> AssertionResult:
    """Assert that a tool was called during the agent run.

    Args:
        cassette: The cassette or agent run to check
        tool_name: Name of the tool that should have been called
        times: Optional exact number of times it should have been called
        with_args: Optional args that should have been passed
        before: Tool that should have been called AFTER this tool
        after: Tool that should have been called BEFORE this tool
    """
    c = _get_cassette(cassette)
    tool_calls = [s for s in c.get_tool_calls() if s.tool_name == tool_name]

    if not tool_calls:
        return AssertionResult(
            name=f"assert_tool_called({tool_name})",
            passed=False,
            expected=tool_name,
            actual=c.get_tool_sequence(),
            message=f"Tool '{tool_name}' was never called. Called tools: {c.get_tool_sequence()}",
        )

    if times is not None and len(tool_calls) != times:
        return AssertionResult(
            name=f"assert_tool_called({tool_name}, times={times})",
            passed=False,
            expected=times,
            actual=len(tool_calls),
            message=f"Tool '{tool_name}' was called {len(tool_calls)} times, expected {times}",
        )

    if with_args:
        matched = any(
            all(tc.tool_args and tc.tool_args.get(k) == v for k, v in with_args.items())
            for tc in tool_calls
        )
        if not matched:
            return AssertionResult(
                name=f"assert_tool_called({tool_name}, with_args=...)",
                passed=False,
                expected=with_args,
                actual=[tc.tool_args for tc in tool_calls],
                message=f"Tool '{tool_name}' was never called with args: {with_args}",
            )

    if before:
        seq = c.get_tool_sequence()
        try:
            tool_idx = seq.index(tool_name)
            before_idx = seq.index(before)
            if tool_idx >= before_idx:
                return AssertionResult(
                    name=f"assert_tool_called({tool_name}, before={before})",
                    passed=False,
                    expected=f"{tool_name} before {before}",
                    actual=seq,
                    message=f"Tool '{tool_name}' was not called before '{before}'. Sequence: {seq}",
                )
        except ValueError as e:
            return AssertionResult(
                name=f"assert_tool_called({tool_name}, before={before})",
                passed=False,
                expected=f"{tool_name} and {before} in sequence",
                actual=seq,
                message=f"Tool not found in sequence: {e}",
            )

    if after:
        seq = c.get_tool_sequence()
        try:
            tool_idx = seq.index(tool_name)
            after_idx = seq.index(after)
            if tool_idx <= after_idx:
                return AssertionResult(
                    name=f"assert_tool_called({tool_name}, after={after})",
                    passed=False,
                    expected=f"{tool_name} after {after}",
                    actual=seq,
                    message=f"Tool '{tool_name}' was not called after '{after}'. Sequence: {seq}",
                )
        except ValueError as e:
            return AssertionResult(
                name=f"assert_tool_called({tool_name}, after={after})",
                passed=False,
                expected=f"{tool_name} and {after} in sequence",
                actual=seq,
                message=f"Tool not found in sequence: {e}",
            )

    return AssertionResult(
        name=f"assert_tool_called({tool_name})",
        passed=True,
        expected=tool_name,
        actual=tool_name,
    )


def assert_tool_order(
    cassette: Cassette | AgentRun,
    expected_order: list[str],
    strict: bool = False,
) -> AssertionResult:
    """Assert that tools were called in a specific order.

    Args:
        cassette: The cassette or agent run to check
        expected_order: Expected sequence of tool names
        strict: If True, the sequence must be exact. If False, the tools
                must appear in order but other tools can be in between.
    """
    c = _get_cassette(cassette)
    actual = c.get_tool_sequence()

    if strict:
        if actual != expected_order:
            return AssertionResult(
                name="assert_tool_order(strict)",
                passed=False,
                expected=expected_order,
                actual=actual,
                message=f"Tool sequence mismatch.\nExpected: {expected_order}\nActual: {actual}",
            )
    else:
        # Check subsequence
        actual_iter = iter(actual)
        for tool in expected_order:
            found = False
            for actual_tool in actual_iter:
                if actual_tool == tool:
                    found = True
                    break
            if not found:
                return AssertionResult(
                    name="assert_tool_order",
                    passed=False,
                    expected=expected_order,
                    actual=actual,
                    message=f"Expected tool '{tool}' not found in order. Sequence: {actual}",
                )

    return AssertionResult(
        name="assert_tool_order",
        passed=True,
        expected=expected_order,
        actual=actual,
    )


def assert_no_tool_called(
    cassette: Cassette | AgentRun,
    tool_name: str,
) -> AssertionResult:
    """Assert that a specific tool was NOT called.

    Args:
        cassette: The cassette or agent run to check
        tool_name: Name of the tool that should NOT have been called
    """
    c = _get_cassette(cassette)
    tool_calls = [s for s in c.get_tool_calls() if s.tool_name == tool_name]

    if tool_calls:
        return AssertionResult(
            name=f"assert_no_tool_called({tool_name})",
            passed=False,
            expected=f"{tool_name} not called",
            actual=f"Called {len(tool_calls)} times",
            message=f"Tool '{tool_name}' was called {len(tool_calls)} times, expected 0",
        )

    return AssertionResult(
        name=f"assert_no_tool_called({tool_name})",
        passed=True,
    )


# ──────────────────────────────────────────────
# Output assertions
# ──────────────────────────────────────────────

def assert_output_contains(
    cassette: Cassette | AgentRun,
    substring: str,
    case_sensitive: bool = True,
) -> AssertionResult:
    """Assert the agent output contains a substring."""
    c = _get_cassette(cassette)
    output = c.output_text

    if case_sensitive:
        passed = substring in output
    else:
        passed = substring.lower() in output.lower()

    return AssertionResult(
        name=f"assert_output_contains({substring!r})",
        passed=passed,
        expected=substring,
        actual=output[:200] if not passed else substring,
        message="" if passed else f"Output does not contain '{substring}'",
    )


def assert_output_matches(
    cassette: Cassette | AgentRun,
    pattern: str,
) -> AssertionResult:
    """Assert the agent output matches a regex pattern."""
    c = _get_cassette(cassette)
    output = c.output_text
    match = re.search(pattern, output)

    return AssertionResult(
        name=f"assert_output_matches({pattern!r})",
        passed=match is not None,
        expected=pattern,
        actual=output[:200] if not match else match.group(),
        message="" if match else f"Output does not match pattern '{pattern}'",
    )


# ──────────────────────────────────────────────
# Cost and performance assertions
# ──────────────────────────────────────────────

def assert_cost_under(
    cassette: Cassette | AgentRun,
    max_usd: float,
) -> AssertionResult:
    """Assert the total cost of the run is under a threshold."""
    c = _get_cassette(cassette)
    c.compute_metrics()

    return AssertionResult(
        name=f"assert_cost_under(${max_usd})",
        passed=c.total_cost_usd <= max_usd,
        expected=max_usd,
        actual=c.total_cost_usd,
        message="" if c.total_cost_usd <= max_usd
        else f"Cost ${c.total_cost_usd:.4f} exceeds limit ${max_usd:.4f}",
    )


def assert_latency_under(
    cassette: Cassette | AgentRun,
    max_ms: float,
) -> AssertionResult:
    """Assert the total latency of the run is under a threshold."""
    c = _get_cassette(cassette)
    c.compute_metrics()

    return AssertionResult(
        name=f"assert_latency_under({max_ms}ms)",
        passed=c.total_duration_ms <= max_ms,
        expected=max_ms,
        actual=c.total_duration_ms,
        message="" if c.total_duration_ms <= max_ms
        else f"Latency {c.total_duration_ms:.1f}ms exceeds limit {max_ms:.1f}ms",
    )


def assert_token_count_under(
    cassette: Cassette | AgentRun,
    max_tokens: int,
) -> AssertionResult:
    """Assert the total token count is under a threshold."""
    c = _get_cassette(cassette)
    c.compute_metrics()

    return AssertionResult(
        name=f"assert_token_count_under({max_tokens})",
        passed=c.total_tokens <= max_tokens,
        expected=max_tokens,
        actual=c.total_tokens,
        message="" if c.total_tokens <= max_tokens
        else f"Token count {c.total_tokens} exceeds limit {max_tokens}",
    )


# ──────────────────────────────────────────────
# Composite evaluator
# ──────────────────────────────────────────────

class Evaluator:
    """Compose multiple assertions into a single evaluation.

    Usage:
        evaluator = Evaluator()
        evaluator.add(assert_tool_called, cassette, "search")
        evaluator.add(assert_cost_under, cassette, max_usd=0.05)
        result = evaluator.run()
        assert result.passed
    """

    def __init__(self):
        self._checks: list[tuple] = []

    def add(self, assertion_fn, *args, **kwargs) -> Evaluator:
        """Add an assertion to the evaluator."""
        self._checks.append((assertion_fn, args, kwargs))
        return self

    def run(self) -> EvalResult:
        """Run all assertions and return the combined result."""
        results = []
        for fn, args, kwargs in self._checks:
            result = fn(*args, **kwargs)
            results.append(result)

        all_passed = all(r.passed for r in results)
        score = sum(1 for r in results if r.passed) / len(results) if results else 1.0

        return EvalResult(
            passed=all_passed,
            score=score,
            assertions=results,
        )


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _get_cassette(obj: Cassette | AgentRun) -> Cassette:
    """Extract cassette from either a Cassette or AgentRun."""
    if isinstance(obj, AgentRun):
        return obj.cassette
    return obj
