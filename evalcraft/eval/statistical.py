"""Statistical evaluation — run scorers N times for confidence intervals.

LLM outputs are non-deterministic. Running an eval once is meaningless.
This module runs a scorer multiple times and reports pass rate, mean score,
and confidence intervals.

Usage::

    from evalcraft.eval.statistical import eval_n

    result = eval_n(
        cassette,
        scorer=assert_output_semantic,
        n=5,
        criteria="Mentions temperature and city name",
    )
    assert result.pass_rate >= 0.8
    print(f"Pass rate: {result.pass_rate:.0%} ({result.passes}/{result.n})")
    print(f"Mean score: {result.mean_score:.2f} +/- {result.std_score:.2f}")
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable

from evalcraft.core.models import AgentRun, AssertionResult, Cassette


@dataclass
class StatisticalResult:
    """Result of running a scorer N times."""
    n: int = 0
    passes: int = 0
    failures: int = 0
    pass_rate: float = 0.0
    mean_score: float = 0.0
    std_score: float = 0.0
    ci_lower: float = 0.0  # 95% confidence interval lower bound
    ci_upper: float = 0.0  # 95% confidence interval upper bound
    results: list[AssertionResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """True if pass rate meets the threshold (default: majority)."""
        return self.pass_rate >= 0.5

    def to_dict(self) -> dict:
        return {
            "n": self.n,
            "passes": self.passes,
            "failures": self.failures,
            "pass_rate": self.pass_rate,
            "mean_score": self.mean_score,
            "std_score": self.std_score,
            "ci_lower": self.ci_lower,
            "ci_upper": self.ci_upper,
            "results": [r.to_dict() for r in self.results],
        }


def eval_n(
    cassette: Cassette | AgentRun,
    scorer: Callable[..., AssertionResult],
    n: int = 5,
    **scorer_kwargs: Any,
) -> StatisticalResult:
    """Run a scorer N times and compute statistical aggregates.

    This is useful for LLM-as-Judge scorers that may produce different
    results on each call due to judge non-determinism.

    Args:
        cassette: The cassette or agent run to evaluate.
        scorer: The scorer function to call (e.g. ``assert_output_semantic``).
        n: Number of times to run the scorer (default 5).
        **scorer_kwargs: Additional keyword arguments passed to the scorer.

    Returns:
        StatisticalResult with pass rate, mean score, and confidence intervals.

    Example::

        result = eval_n(
            run,
            assert_output_semantic,
            n=5,
            criteria="Mentions the city name",
        )
        assert result.pass_rate >= 0.8
    """
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")

    results: list[AssertionResult] = []
    for _ in range(n):
        result = scorer(cassette, **scorer_kwargs)
        results.append(result)

    passes = sum(1 for r in results if r.passed)
    failures = n - passes
    pass_rate = passes / n

    # Compute confidence interval for pass rate using Wilson score interval
    ci_lower, ci_upper = _wilson_ci(passes, n)

    # If results have numeric actuals, compute mean/std of those
    scores = _extract_scores(results)
    if scores:
        mean_score = sum(scores) / len(scores)
        if len(scores) > 1:
            variance = sum((s - mean_score) ** 2 for s in scores) / (len(scores) - 1)
            std_score = math.sqrt(variance)
        else:
            std_score = 0.0
    else:
        mean_score = pass_rate
        std_score = 0.0

    return StatisticalResult(
        n=n,
        passes=passes,
        failures=failures,
        pass_rate=pass_rate,
        mean_score=mean_score,
        std_score=std_score,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        results=results,
    )


def _wilson_ci(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score confidence interval for a binomial proportion.

    More accurate than the normal approximation for small sample sizes.
    Default z=1.96 gives a 95% confidence interval.
    """
    if total == 0:
        return (0.0, 0.0)

    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    spread = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denominator

    lower = max(0.0, center - spread)
    upper = min(1.0, center + spread)
    return (lower, upper)


def _extract_scores(results: list[AssertionResult]) -> list[float]:
    """Try to extract numeric scores from assertion results."""
    scores: list[float] = []
    for r in results:
        actual = r.actual
        if isinstance(actual, (int, float)):
            scores.append(float(actual))
        elif isinstance(actual, str):
            # Try to parse "0.85" or "0.85 (2/3 claims supported)"
            try:
                scores.append(float(actual.split()[0]))
            except (ValueError, IndexError):
                pass
    return scores
