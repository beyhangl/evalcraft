"""Multi-judge consensus scoring — run multiple LLM judges and aggregate.

Single-judge evaluation suffers from self-preference bias, position bias,
and verbosity bias. Running multiple judges and aggregating via majority
vote substantially improves reliability.

Usage::

    from evalcraft.eval.jury import JuryScorer

    jury = JuryScorer(
        judges=[
            {"provider": "openai", "model": "gpt-4.1-nano"},
            {"provider": "openai", "model": "gpt-4.1-mini"},
            {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
        ],
    )

    result = jury.evaluate(cassette, criteria="Is the answer helpful and accurate?")
    assert result.passed
    print(f"Verdict: {result.verdict} ({result.votes_for}/{result.total_judges})")
    print(f"Agreement: {result.agreement:.0%}")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from evalcraft.core.models import AgentRun, AssertionResult, Cassette
from evalcraft.eval.llm_judge import _call_judge


def _get_cassette(obj: Cassette | AgentRun) -> Cassette:
    if isinstance(obj, AgentRun):
        return obj.cassette
    return obj


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class JudgeVote:
    """A single judge's vote."""
    provider: str
    model: str
    passed: bool
    score: float
    reason: str

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "passed": self.passed,
            "score": self.score,
            "reason": self.reason,
        }


@dataclass
class JuryResult:
    """Aggregated result from multiple judges."""
    verdict: str  # "pass", "fail", or "split"
    passed: bool
    votes_for: int = 0
    votes_against: int = 0
    total_judges: int = 0
    agreement: float = 0.0  # fraction of judges that agree with the verdict
    mean_score: float = 0.0
    votes: list[JudgeVote] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "passed": self.passed,
            "votes_for": self.votes_for,
            "votes_against": self.votes_against,
            "total_judges": self.total_judges,
            "agreement": self.agreement,
            "mean_score": self.mean_score,
            "votes": [v.to_dict() for v in self.votes],
        }


# ---------------------------------------------------------------------------
# JuryScorer
# ---------------------------------------------------------------------------

class JuryScorer:
    """Run multiple LLM judges and aggregate via majority vote.

    Args:
        judges: List of judge configurations. Each is a dict with optional
                keys ``provider`` (default "openai"), ``model``, and ``api_key``.
                If not provided, defaults to 3 diverse judges.
        threshold: Fraction of judges that must pass for the overall verdict
                   to be "pass" (default 0.5 = majority).
    """

    def __init__(
        self,
        judges: list[dict[str, str]] | None = None,
        threshold: float = 0.5,
    ) -> None:
        if judges is None:
            judges = [
                {"provider": "openai", "model": "gpt-4.1-nano"},
                {"provider": "openai", "model": "gpt-4.1-mini"},
                {"provider": "openai", "model": "gpt-4.1"},
            ]
        if not judges:
            raise ValueError("At least one judge is required")
        self.judges = judges
        self.threshold = threshold

    def evaluate(
        self,
        cassette: Cassette | AgentRun,
        criteria: str,
    ) -> JuryResult:
        """Evaluate the cassette output with all judges.

        Args:
            cassette: The cassette or agent run to evaluate.
            criteria: Natural-language criteria for the judges.

        Returns:
            JuryResult with aggregated verdict, votes, and agreement score.
        """
        c = _get_cassette(cassette)
        output = c.output_text

        if not output:
            return JuryResult(
                verdict="fail",
                passed=False,
                total_judges=len(self.judges),
                votes=[],
            )

        prompt = (
            f"## Agent output\n{output}\n\n"
            f"## Criteria\n{criteria}\n\n"
            "Does the agent output satisfy the criteria?"
        )

        votes: list[JudgeVote] = []
        for judge_cfg in self.judges:
            provider = judge_cfg.get("provider", "openai")
            model = judge_cfg.get("model")
            api_key = judge_cfg.get("api_key")

            result = _call_judge(
                prompt,
                provider=provider,
                model=model,
                api_key=api_key,
            )

            votes.append(JudgeVote(
                provider=provider,
                model=model or "(default)",
                passed=bool(result["pass"]),
                score=float(result.get("score", 1.0 if result["pass"] else 0.0)),
                reason=result.get("reason", ""),
            ))

        votes_for = sum(1 for v in votes if v.passed)
        votes_against = len(votes) - votes_for
        total = len(votes)
        pass_rate = votes_for / total if total > 0 else 0.0
        passed = pass_rate >= self.threshold

        if passed:
            verdict = "pass"
        elif votes_for == 0:
            verdict = "fail"
        else:
            verdict = "split"

        majority_count = max(votes_for, votes_against)
        agreement = majority_count / total if total > 0 else 0.0

        scores = [v.score for v in votes]
        mean_score = sum(scores) / len(scores) if scores else 0.0

        return JuryResult(
            verdict=verdict,
            passed=passed,
            votes_for=votes_for,
            votes_against=votes_against,
            total_judges=total,
            agreement=agreement,
            mean_score=mean_score,
            votes=votes,
        )

    def assert_consensus(
        self,
        cassette: Cassette | AgentRun,
        criteria: str,
    ) -> AssertionResult:
        """Evaluate and return an AssertionResult for use with existing scorers.

        Convenience method that wraps ``evaluate()`` into the standard
        ``AssertionResult`` format, compatible with ``Evaluator.add()``.
        """
        jury_result = self.evaluate(cassette, criteria)

        return AssertionResult(
            name=f"jury_consensus({len(self.judges)} judges)",
            passed=jury_result.passed,
            expected=f">= {self.threshold:.0%} agreement",
            actual=f"{jury_result.votes_for}/{jury_result.total_judges} passed "
                   f"(agreement: {jury_result.agreement:.0%})",
            message="" if jury_result.passed else
                   f"Jury verdict: {jury_result.verdict} — "
                   f"{jury_result.votes_for}/{jury_result.total_judges} judges passed, "
                   f"needed {self.threshold:.0%}",
        )
