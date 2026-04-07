"""Hallucination detection scorer — decompose output into claims, verify each.

Given a context (retrieved docs, tool results, or known facts) and an LLM
output, this scorer extracts atomic claims from the output and checks each
one against the context for contradictions or fabrications.

Unlike ``assert_faithfulness`` (which returns a single score), this scorer
provides per-claim granularity — showing exactly which statements are
hallucinated and why.

Usage::

    from evalcraft.eval.hallucination import assert_no_hallucination

    run = replay("tests/cassettes/rag_agent.json")
    result = assert_no_hallucination(
        run,
        context="Paris has 2.1 million people. The Eiffel Tower is 330m tall.",
    )
    assert result.passed
    print(f"Hallucination rate: {result.hallucination_rate:.0%}")
    for claim in result.claims:
        if not claim.supported:
            print(f"  HALLUCINATED: {claim.text} — {claim.reason}")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from evalcraft.core.models import AgentRun, AssertionResult, Cassette
from evalcraft.eval._utils import get_cassette, call_llm_judge


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Claim:
    """A single atomic claim extracted from the agent output."""
    text: str
    supported: bool
    reason: str = ""
    category: str = ""  # "supported", "unsupported", "contradicted"

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "supported": self.supported,
            "reason": self.reason,
            "category": self.category,
        }


@dataclass
class HallucinationResult:
    """Detailed result of hallucination detection."""
    passed: bool
    hallucination_rate: float  # 0.0 = no hallucinations, 1.0 = all hallucinated
    total_claims: int
    supported_claims: int
    unsupported_claims: int
    claims: list[Claim] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "hallucination_rate": self.hallucination_rate,
            "total_claims": self.total_claims,
            "supported_claims": self.supported_claims,
            "unsupported_claims": self.unsupported_claims,
            "claims": [c.to_dict() for c in self.claims],
        }

    @property
    def hallucinated_claims(self) -> list[Claim]:
        return [c for c in self.claims if not c.supported]


# ---------------------------------------------------------------------------
# LLM judge call
# ---------------------------------------------------------------------------

_HALLUCINATION_SYSTEM_PROMPT = (
    "You are a hallucination detection system. You extract atomic "
    "factual claims from text and verify each against provided context. "
    "Respond ONLY with a JSON object:\n"
    '{"claims": [{"text": "claim text", "supported": true/false, '
    '"reason": "why", "category": "supported|unsupported|contradicted"}]}'
)


def _call_hallucination_judge(
    prompt: str,
    *,
    provider: str = "openai",
    model: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Call an LLM to extract and verify claims."""
    result = call_llm_judge(
        prompt,
        system_prompt=_HALLUCINATION_SYSTEM_PROMPT,
        provider=provider,
        model=model,
        api_key=api_key,
    )
    result.setdefault("claims", [])
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_hallucinations(
    cassette: Cassette | AgentRun,
    context: str | list[str],
    *,
    threshold: float = 0.5,
    provider: str = "openai",
    model: str | None = None,
    api_key: str | None = None,
) -> HallucinationResult:
    """Detect hallucinated claims in the agent output.

    Extracts atomic claims from the output, then verifies each against
    the provided context. Returns per-claim results with detailed reasons.

    Args:
        cassette: The cassette or agent run to check.
        context: Known-correct context — either a single string or a list
                 of context chunks. The agent output will be checked against
                 this for contradictions and fabrications.
        threshold: Maximum allowed hallucination rate (0.0-1.0). Default 0.5
                   means the check passes if fewer than half the claims are
                   hallucinated.
        provider: LLM provider for the judge.
        model: Override the judge model.
        api_key: Optional API key override.

    Returns:
        HallucinationResult with per-claim breakdown.
    """
    c = get_cassette(cassette)
    output = c.output_text

    if not output:
        return HallucinationResult(
            passed=True,
            hallucination_rate=0.0,
            total_claims=0,
            supported_claims=0,
            unsupported_claims=0,
        )

    # Normalise context to a single string
    if isinstance(context, list):
        context_str = "\n\n---\n\n".join(
            f"Context {i + 1}:\n{ctx}" for i, ctx in enumerate(context)
        )
    else:
        context_str = context

    prompt = (
        f"## Context (ground truth)\n{context_str}\n\n"
        f"## Agent Output\n{output}\n\n"
        "## Task\n"
        "1. Extract every atomic factual claim from the Agent Output.\n"
        "2. For each claim, check if it is supported by the Context.\n"
        "3. Classify each claim as:\n"
        "   - 'supported': the context confirms this claim\n"
        "   - 'unsupported': the context doesn't mention this (fabricated)\n"
        "   - 'contradicted': the context says the opposite\n"
        "4. Provide a brief reason for each classification.\n"
    )

    result = _call_hallucination_judge(
        prompt, provider=provider, model=model, api_key=api_key
    )

    claims: list[Claim] = []
    for raw_claim in result.get("claims", []):
        claims.append(Claim(
            text=raw_claim.get("text", ""),
            supported=bool(raw_claim.get("supported", False)),
            reason=raw_claim.get("reason", ""),
            category=raw_claim.get("category", "unsupported" if not raw_claim.get("supported") else "supported"),
        ))

    total = len(claims)
    supported = sum(1 for c in claims if c.supported)
    unsupported = total - supported
    hallucination_rate = unsupported / total if total > 0 else 0.0
    passed = hallucination_rate <= threshold

    return HallucinationResult(
        passed=passed,
        hallucination_rate=hallucination_rate,
        total_claims=total,
        supported_claims=supported,
        unsupported_claims=unsupported,
        claims=claims,
    )


def assert_no_hallucination(
    cassette: Cassette | AgentRun,
    context: str | list[str],
    *,
    threshold: float = 0.5,
    provider: str = "openai",
    model: str | None = None,
    api_key: str | None = None,
) -> AssertionResult:
    """Assert that the agent output contains no hallucinations.

    Convenience wrapper around ``detect_hallucinations`` that returns
    an ``AssertionResult`` compatible with the ``Evaluator``.

    Args:
        cassette: The cassette or agent run to check.
        context: Known-correct context to verify against.
        threshold: Maximum hallucination rate (default 0.5).
        provider: LLM provider.
        model: Override the judge model.
        api_key: Optional API key override.
    """
    result = detect_hallucinations(
        cassette, context,
        threshold=threshold,
        provider=provider,
        model=model,
        api_key=api_key,
    )

    hallucinated = [c for c in result.claims if not c.supported]
    detail = ""
    if hallucinated:
        detail = "; ".join(f'"{c.text}" ({c.category})' for c in hallucinated[:3])
        if len(hallucinated) > 3:
            detail += f" ... and {len(hallucinated) - 3} more"

    return AssertionResult(
        name="assert_no_hallucination",
        passed=result.passed,
        expected=f"hallucination_rate <= {threshold:.0%}",
        actual=f"{result.hallucination_rate:.0%} ({result.unsupported_claims}/{result.total_claims} claims unsupported)",
        message=detail if not result.passed else "",
    )
