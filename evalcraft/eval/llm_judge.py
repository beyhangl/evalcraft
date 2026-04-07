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

By default the judge uses ``gpt-4.1-nano`` via the OpenAI SDK.  You can
switch to any OpenAI-compatible endpoint or the Anthropic SDK by passing
``provider="anthropic"`` and ``model="claude-haiku-4-5-20251001"``.
"""

from __future__ import annotations

from typing import Any

from evalcraft.core.models import AssertionResult, AgentRun, Cassette
from evalcraft.eval._utils import get_cassette, call_llm_judge, normalize_pass_key


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
        model: Override the judge model (default ``gpt-4.1-nano`` / ``claude-haiku-4-5-20251001``).
        api_key: Optional API key override.

    Returns:
        AssertionResult with ``passed=True`` if the judge says the criteria are met.
    """
    c = get_cassette(cassette)
    output = c.output_text

    if not output:
        return AssertionResult(
            name=f"assert_output_semantic({criteria!r})",
            passed=False,
            expected=criteria,
            actual="<empty output>",
            message="Agent produced no output to evaluate.",
        )

    prompt = (
        f"## Agent output\n{output}\n\n"
        f"## Criteria\n{criteria}\n\n"
        "Does the agent output satisfy ALL of the above criteria?"
    )

    result = _call_judge(prompt, provider=provider, model=model, api_key=api_key)

    return AssertionResult(
        name=f"assert_output_semantic({criteria!r})",
        passed=bool(result["pass"]),
        expected=criteria,
        actual=output[:200],
        message=result.get("reason", "") if not result["pass"] else "",
    )


def assert_factual_consistency(
    cassette: Cassette | AgentRun,
    ground_truth: str,
    *,
    provider: str = "openai",
    model: str | None = None,
    api_key: str | None = None,
) -> AssertionResult:
    """Assert that the agent output is factually consistent with *ground_truth*."""
    c = get_cassette(cassette)
    output = c.output_text

    if not output:
        return AssertionResult(
            name="assert_factual_consistency",
            passed=False,
            expected=ground_truth[:100],
            actual="<empty output>",
            message="Agent produced no output to evaluate.",
        )

    prompt = (
        f"## Agent output\n{output}\n\n"
        f"## Ground truth\n{ground_truth}\n\n"
        "Is the agent output factually consistent with the ground truth? "
        "Minor rephrasings are acceptable.  Contradictions, fabricated details, "
        "or missing critical facts should cause a failure."
    )

    result = _call_judge(prompt, provider=provider, model=model, api_key=api_key)

    return AssertionResult(
        name="assert_factual_consistency",
        passed=bool(result["pass"]),
        expected=ground_truth[:200],
        actual=output[:200],
        message=result.get("reason", "") if not result["pass"] else "",
    )


def assert_tone(
    cassette: Cassette | AgentRun,
    expected: str,
    *,
    provider: str = "openai",
    model: str | None = None,
    api_key: str | None = None,
) -> AssertionResult:
    """Assert that the agent output has the *expected* tone."""
    c = get_cassette(cassette)
    output = c.output_text

    if not output:
        return AssertionResult(
            name=f"assert_tone({expected!r})",
            passed=False,
            expected=expected,
            actual="<empty output>",
            message="Agent produced no output to evaluate.",
        )

    prompt = (
        f"## Agent output\n{output}\n\n"
        f"## Expected tone\n{expected}\n\n"
        "Does the agent output match the expected tone?"
    )

    result = _call_judge(prompt, provider=provider, model=model, api_key=api_key)

    return AssertionResult(
        name=f"assert_tone({expected!r})",
        passed=bool(result["pass"]),
        expected=expected,
        actual=output[:200],
        message=result.get("reason", "") if not result["pass"] else "",
    )


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
    c = get_cassette(cassette)
    output = c.output_text

    if not output:
        return AssertionResult(
            name="assert_custom_criteria",
            passed=False,
            expected=criteria,
            actual="<empty output>",
            message="Agent produced no output to evaluate.",
        )

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

    return AssertionResult(
        name="assert_custom_criteria",
        passed=bool(result["pass"]),
        expected=criteria,
        actual=output[:200],
        message=result.get("reason", "") if not result["pass"] else "",
    )
