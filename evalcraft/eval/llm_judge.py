"""LLM-as-Judge scorers — semantic evaluation of agent outputs using an LLM.

Unlike regex/exact-match scorers, these functions call an LLM to evaluate
the quality, correctness, and tone of agent outputs.  They are intended for
CI pipelines where you want deeper quality gates than string matching.

Usage::

    from evalcraft.eval.llm_judge import (
        assert_output_semantic,
        assert_factual_consistency,
        assert_tone,
        assert_custom_criteria,
    )

    run = replay("tests/cassettes/weather.json")
    result = assert_output_semantic(run, criteria="Mentions temperature and city name")
    assert result.passed

By default the judge uses ``gpt-5.4-nano`` via the OpenAI SDK.  You can
switch to any OpenAI-compatible endpoint or the Anthropic SDK by passing
``provider="anthropic"`` and ``model="claude-haiku-4-5-20251001"``.
"""

from __future__ import annotations

from typing import Any

from evalcraft.core.models import AgentRun, AssertionResult, Cassette
from evalcraft.eval._utils import call_llm_judge, normalize_pass_key, output_or_fail

_JUDGE_SYSTEM_PROMPT = (
    "You are an evaluation judge.  You receive an agent output and "
    "a set of criteria.  Respond ONLY with a JSON object: "
    '{"pass": true/false, "reason": "brief explanation", "score": 0.0-1.0}'
)


def _call_judge(
    prompt: str,
    *,
    provider: str = "openai",
    model: str | None = None,
    api_key: str | None = None,
    temperature: float = 0.0,
) -> dict[str, Any]:
    """Call an LLM judge and parse the structured JSON response.

    Thin wrapper around :func:`evalcraft.eval._utils.call_llm_judge`
    kept for backward compatibility (tests mock this function).
    """
    result = call_llm_judge(
        prompt,
        system_prompt=_JUDGE_SYSTEM_PROMPT,
        provider=provider,
        model=model,
        api_key=api_key,
        temperature=temperature,
    )
    return normalize_pass_key(result)


def _pass_reason_result(
    name: str, result: dict[str, Any], expected: Any, output: str
) -> AssertionResult:
    """Build the standard AssertionResult from a ``{pass, reason}`` judge result."""
    passed = bool(result["pass"])
    return AssertionResult(
        name=name, passed=passed, expected=expected,
        actual=output[:200], message="" if passed else result.get("reason", ""),
    )


# ---------------------------------------------------------------------------
# Public scorers
# ---------------------------------------------------------------------------

def assert_output_semantic(
    cassette: Cassette | AgentRun,
    criteria: str,
    *,
    provider: str = "openai",
    model: str | None = None,
    api_key: str | None = None,
) -> AssertionResult:
    """Assert that the agent output satisfies semantic *criteria* judged by an LLM.

    Args:
        cassette: The cassette or agent run to evaluate.
        criteria: Natural-language description of what the output should contain
                  or how it should behave (e.g. "Mentions temperature and city name").
        provider: LLM provider — ``"openai"`` (default) or ``"anthropic"``.
        model: Override the judge model (default ``gpt-5.4-nano`` / ``claude-haiku-4-5-20251001``).
        api_key: Optional API key override.

    Returns:
        AssertionResult with ``passed=True`` if the judge says the criteria are met.
    """
    name = f"assert_output_semantic({criteria!r})"
    output, fail = output_or_fail(cassette, name, criteria)
    if fail:
        return fail

    prompt = (
        f"## Agent output\n{output}\n\n"
        f"## Criteria\n{criteria}\n\n"
        "Does the agent output satisfy ALL of the above criteria?"
    )

    result = _call_judge(prompt, provider=provider, model=model, api_key=api_key)
    return _pass_reason_result(name, result, criteria, output)


def assert_factual_consistency(
    cassette: Cassette | AgentRun,
    ground_truth: str,
    *,
    provider: str = "openai",
    model: str | None = None,
    api_key: str | None = None,
) -> AssertionResult:
    """Assert that the agent output is factually consistent with *ground_truth*."""
    expected = ground_truth[:200]
    output, fail = output_or_fail(cassette, "assert_factual_consistency", expected)
    if fail:
        return fail

    prompt = (
        f"## Agent output\n{output}\n\n"
        f"## Ground truth\n{ground_truth}\n\n"
        "Is the agent output factually consistent with the ground truth? "
        "Minor rephrasings are acceptable.  Contradictions, fabricated details, "
        "or missing critical facts should cause a failure."
    )

    result = _call_judge(prompt, provider=provider, model=model, api_key=api_key)
    return _pass_reason_result("assert_factual_consistency", result, expected, output)


def assert_tone(
    cassette: Cassette | AgentRun,
    expected: str,
    *,
    provider: str = "openai",
    model: str | None = None,
    api_key: str | None = None,
) -> AssertionResult:
    """Assert that the agent output has the *expected* tone."""
    name = f"assert_tone({expected!r})"
    output, fail = output_or_fail(cassette, name, expected)
    if fail:
        return fail

    prompt = (
        f"## Agent output\n{output}\n\n"
        f"## Expected tone\n{expected}\n\n"
        "Does the agent output match the expected tone?"
    )

    result = _call_judge(prompt, provider=provider, model=model, api_key=api_key)
    return _pass_reason_result(name, result, expected, output)


def assert_custom_criteria(
    cassette: Cassette | AgentRun,
    criteria: list[str],
    *,
    require_all: bool = True,
    provider: str = "openai",
    model: str | None = None,
    api_key: str | None = None,
) -> AssertionResult:
    """Assert that the agent output meets a list of custom evaluation criteria."""
    output, fail = output_or_fail(cassette, "assert_custom_criteria", criteria)
    if fail:
        return fail

    criteria_block = "\n".join(f"  {i + 1}. {crit}" for i, crit in enumerate(criteria))
    mode_instruction = (
        "ALL criteria must be satisfied for a pass."
        if require_all
        else "At least ONE criterion must be satisfied for a pass."
    )

    prompt = (
        f"## Agent output\n{output}\n\n"
        f"## Criteria\n{criteria_block}\n\n"
        f"{mode_instruction}\n\n"
        "Evaluate each criterion and determine an overall pass/fail."
    )

    result = _call_judge(prompt, provider=provider, model=model, api_key=api_key)
    return _pass_reason_result("assert_custom_criteria", result, criteria, output)
