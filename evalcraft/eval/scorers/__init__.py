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
from collections import Counter

from evalcraft.core.models import (
    AgentRun,
    AssertionResult,
    Cassette,
    EvalResult,
    SpanKind,
)
from evalcraft.eval._utils import get_cassette as _get_cassette

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


_TRAJECTORY_MODES = ("strict", "unordered", "subset", "superset")


def assert_tool_trajectory(
    cassette: Cassette | AgentRun,
    expected_tools: list[str],
    *,
    mode: str = "strict",
) -> AssertionResult:
    """Assert the tool-call trajectory matches a reference under one of four modes.

    Complements ``assert_tool_order`` (strict / ordered-subsequence) with the
    set/multiset comparisons agent trajectories are usually judged by:

    - ``"strict"``    — exact same tools in exact same order (list equality).
    - ``"unordered"`` — same tools with the same counts, any order (multiset equality).
    - ``"subset"``    — every tool called is in the reference (no unexpected tools;
      the agent may skip some). Set-based: ``set(actual) <= set(expected)``.
    - ``"superset"``  — every reference tool was called (all required present; the
      agent may add more). Set-based: ``set(expected) <= set(actual)``.

    Args:
        cassette: The cassette or agent run to check.
        expected_tools: Reference sequence/set of tool names.
        mode: One of ``strict`` / ``unordered`` / ``subset`` / ``superset``.
    """
    if mode not in _TRAJECTORY_MODES:
        raise ValueError(f"mode must be one of {_TRAJECTORY_MODES}, got {mode!r}")

    c = _get_cassette(cassette)
    actual = c.get_tool_sequence()
    expected = list(expected_tools)
    name = f"assert_tool_trajectory({mode})"

    detail = ""
    if mode == "strict":
        passed = actual == expected
        if not passed:
            detail = "sequence differs"
    elif mode == "unordered":
        passed = Counter(actual) == Counter(expected)
        if not passed:
            over = sorted((Counter(actual) - Counter(expected)).elements())
            under = sorted((Counter(expected) - Counter(actual)).elements())
            detail = f"extra={over}, missing={under}"
    elif mode == "subset":
        extra = sorted(set(actual) - set(expected))
        passed = not extra
        if not passed:
            detail = f"unexpected tool(s)={extra}"
    else:  # superset
        missing = sorted(set(expected) - set(actual))
        passed = not missing
        if not passed:
            detail = f"missing required tool(s)={missing}"

    return AssertionResult(
        name=name,
        passed=passed,
        expected=expected,
        actual=actual,
        message="" if passed
        else f"Tool trajectory ({mode}) mismatch — {detail}. Expected {expected}, got {actual}",
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

def _priced_total(c: Cassette) -> tuple[float, dict[str, int]]:
    """Total cost, pricing calls recorded without a cost from today's tables.

    Returns the total and, per model, the number of calls to a paid model that
    used tokens but still has no price.
    """
    from evalcraft.core.pricing import looks_paid, price_for

    total = 0.0
    unpriced: dict[str, int] = {}
    for span in c.spans:
        if span.cost_usd:
            total += span.cost_usd
            continue
        if span.cost_usd is not None or span.kind not in (
            SpanKind.LLM_REQUEST, SpanKind.LLM_RESPONSE
        ):
            continue
        usage = span.token_usage
        if usage is None:
            continue
        tokens = (usage.prompt_tokens + usage.completion_tokens
                  + usage.cache_read_tokens + usage.cache_write_tokens)
        if tokens <= 0:
            continue
        price = price_for(span.model)
        if price is not None:
            total += price.cost(
                usage.prompt_tokens, usage.completion_tokens,
                usage.cache_read_tokens, usage.cache_write_tokens,
            )
        elif looks_paid(span.model):
            unpriced[span.model or ""] = unpriced.get(span.model or "", 0) + 1
    return total, unpriced


def assert_cost_under(
    cassette: Cassette | AgentRun,
    max_usd: float,
    *,
    on_unknown_price: str = "fail",
) -> AssertionResult:
    """Assert the total cost of the run is under a threshold.

    Calls recorded without a cost are priced from evalcraft's current tables,
    so a cassette recorded before a model was added still counts. A call to a
    paid model that evalcraft can't price fails the assertion rather than
    counting as $0, since a budget that silently ignores calls proves nothing.
    Register the price with :func:`evalcraft.register_price` or
    ``[tool.evalcraft.prices]``, or pass ``on_unknown_price="ignore"``.
    """
    if on_unknown_price not in ("fail", "ignore"):
        raise ValueError("on_unknown_price must be 'fail' or 'ignore'")
    c = _get_cassette(cassette)
    c.compute_metrics()
    total, unpriced = _priced_total(c)
    name = f"assert_cost_under(${max_usd})"

    if unpriced and on_unknown_price == "fail":
        calls = sum(unpriced.values())
        return AssertionResult(
            name=name,
            passed=False,
            expected=max_usd,
            actual=total,
            message=(
                f"Cost unknown for {calls} call(s) to {sorted(unpriced)}: evalcraft has "
                "no price for these models, so the budget can't be checked. Add one "
                "with evalcraft.register_price(...) or [tool.evalcraft.prices], or "
                "pass on_unknown_price='ignore'."
            ),
        )

    return AssertionResult(
        name=name,
        passed=total <= max_usd,
        expected=max_usd,
        actual=total,
        message="" if total <= max_usd
        else f"Cost ${total:.4f} exceeds limit ${max_usd:.4f}",
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


def assert_same_tool_calls(
    cassette: Cassette | AgentRun,
    baseline: Cassette | AgentRun | str,
    *,
    ignore_fields: list[str] | tuple[str, ...] = (),
    compare_results: bool = False,
) -> AssertionResult:
    """Assert the run called the same tools, in order, with the same arguments.

    Compares against a baseline recording field by field, so a run that looks
    identical in aggregate but looked up ``ORDER-999`` instead of ``ORDER-123``
    fails with exactly that field. ``ignore_fields`` takes glob patterns on
    ``<tool>.<field>`` or ``<field>`` (``"*.arguments.request_id"``). Results
    are not compared unless ``compare_results`` is set, since they come from
    the tool, not the agent.
    """
    from evalcraft.replay.tool_diff import CONTRACT, diff_tool_calls

    c = _get_cassette(cassette)
    base = Cassette.load(baseline) if isinstance(baseline, str) else _get_cassette(baseline)
    old_seq, new_seq = base.get_tool_sequence(), c.get_tool_sequence()
    changes = diff_tool_calls(base, c, ignore=ignore_fields, compare_results=compare_results)
    relevant = [ch for ch in changes if ch.severity == CONTRACT or compare_results]
    problems: list[str] = []
    if old_seq != new_seq:
        problems.append(f"tool sequence {old_seq} → {new_seq}")
    problems += [f"{ch.tool} (call {ch.call}) {ch.describe()}" for ch in relevant]
    return AssertionResult(
        name="assert_same_tool_calls",
        passed=not problems,
        expected=old_seq,
        actual=new_seq,
        message="" if not problems
        else "Tool calls differ from the baseline: " + "; ".join(problems),
    )


def cache_hit_rate(cassette: Cassette | AgentRun) -> float | None:
    """Share of input tokens served from the prompt cache, or ``None`` if no input.

    ``cache_read / (fresh input + cache_read + cache_write)`` over every LLM call.
    """
    c = _get_cassette(cassette)
    read = total = 0
    for span in c.get_llm_calls():
        usage = span.token_usage
        if usage is None:
            continue
        read += usage.cache_read_tokens
        total += usage.prompt_tokens + usage.cache_read_tokens + usage.cache_write_tokens
    return read / total if total else None


def assert_cache_hit_rate_at_least(
    cassette: Cassette | AgentRun,
    min_rate: float,
) -> AssertionResult:
    """Assert that at least ``min_rate`` of input tokens were cache reads.

    In a long agent loop most of the prompt is re-sent every turn, so a falling
    hit rate usually means something changed the cached prefix (a timestamp in
    the system prompt, a reordered tool list) and the run now pays full price
    for it. The first call of a run always misses, so leave room for it.
    """
    if not 0.0 <= min_rate <= 1.0:
        raise ValueError("min_rate must be between 0 and 1")
    rate = cache_hit_rate(cassette)
    name = f"assert_cache_hit_rate_at_least({min_rate:.0%})"
    if rate is None:
        return AssertionResult(
            name=name, passed=False, expected=min_rate, actual=None,
            message="No input tokens were recorded, so the cache hit rate is unknown.",
        )
    return AssertionResult(
        name=name,
        passed=rate >= min_rate,
        expected=min_rate,
        actual=rate,
        message="" if rate >= min_rate
        else f"Cache hit rate {rate:.1%} is below {min_rate:.0%}",
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

