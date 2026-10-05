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
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

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


# ──────────────────────────────────────────────
# Consistency across repeated runs (pass^k)
# ──────────────────────────────────────────────

RunLike = Cassette | AgentRun
Check = Callable[[RunLike], AssertionResult]


@dataclass
class ConsistencyResult:
    """How reliably an agent repeats a success across k runs of the same task.

    - ``mean_at_k``: share of all runs that passed (the usual "pass rate").
    - ``pass_at_k``: share of tasks where at least one of the k runs passed.
    - ``pass_hat_k``: share of tasks where every one of the k runs passed.
    - ``consistency_gap``: ``mean_at_k - pass_hat_k``. A large gap means the
      agent can do the task but doesn't do it reliably.
    """

    k: int = 0
    tasks: int = 0
    mean_at_k: float = 0.0
    pass_at_k: float = 0.0
    pass_hat_k: float = 0.0
    consistency_gap: float = 0.0
    per_task: dict[str, list[bool]] = field(default_factory=dict)
    failures: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "k": self.k,
            "tasks": self.tasks,
            "mean_at_k": self.mean_at_k,
            "pass_at_k": self.pass_at_k,
            "pass_hat_k": self.pass_hat_k,
            "consistency_gap": self.consistency_gap,
            "per_task": {t: list(v) for t, v in self.per_task.items()},
            "failures": {t: list(v) for t, v in self.failures.items()},
        }


def consistency(
    runs: Mapping[str, Sequence[RunLike]] | Sequence[RunLike],
    *checks: Check,
) -> ConsistencyResult:
    """Score k recorded runs per task with ``checks`` and report pass^k.

    ``runs`` is either a list of runs of one task or a mapping of task name to
    its runs; every task needs the same number of runs (k). A run passes when
    every check passes. Checks take the run alone, so bind other arguments::

        result = consistency(
            {"refund": refund_runs, "status": status_runs},
            lambda r: assert_tool_called(r, "lookup_order"),
            lambda r: assert_cost_under(r, max_usd=0.01),
        )
        assert result.pass_hat_k >= 0.9

    Deterministic and $0: it reads recordings, it does not run the agent.
    Record the k runs first, for example by capturing the same scenario k times.
    """
    if not checks:
        raise ValueError("consistency() needs at least one check")
    if isinstance(runs, (str, bytes, Cassette, AgentRun)):
        raise TypeError("consistency() takes a list of runs or a mapping of task -> runs")
    tasks: dict[str, list[RunLike]] = (
        {str(name): list(task_runs) for name, task_runs in runs.items()}
        if isinstance(runs, Mapping)
        else {"task": list(runs)}
    )
    if not tasks:
        raise ValueError("consistency() needs at least one task")
    sizes = {len(v) for v in tasks.values()}
    if len(sizes) != 1 or 0 in sizes:
        raise ValueError(
            f"every task needs the same, non-zero number of runs; got {sorted(sizes)}"
        )
    k = sizes.pop()

    per_task: dict[str, list[bool]] = {}
    failures: dict[str, list[str]] = {}
    for name, task_runs in tasks.items():
        outcomes: list[bool] = []
        for index, run in enumerate(task_runs):
            failed = [r for r in (check(run) for check in checks) if not r.passed]
            outcomes.append(not failed)
            for r in failed:
                failures.setdefault(name, []).append(
                    f"run {index + 1}: {r.name}: {r.message}".rstrip(": ")
                )
        per_task[name] = outcomes

    total_runs = len(tasks) * k
    mean = sum(sum(v) for v in per_task.values()) / total_runs
    any_pass = sum(1 for v in per_task.values() if any(v)) / len(tasks)
    all_pass = sum(1 for v in per_task.values() if all(v)) / len(tasks)
    return ConsistencyResult(
        k=k,
        tasks=len(tasks),
        mean_at_k=mean,
        pass_at_k=any_pass,
        pass_hat_k=all_pass,
        consistency_gap=mean - all_pass,
        per_task=per_task,
        failures=failures,
    )


def assert_pass_hat_k(
    runs: Mapping[str, Sequence[RunLike]] | Sequence[RunLike],
    *checks: Check,
    at_least: float = 1.0,
) -> AssertionResult:
    """Assert that at least ``at_least`` of tasks pass on every one of their k runs.

    The default, 1.0, means every task must succeed on every recorded run. A
    single good run proves the agent *can* do a task; pass^k shows it does so
    reliably.
    """
    result = consistency(runs, *checks)
    ok = result.pass_hat_k >= at_least
    flaky = sorted(t for t, v in result.per_task.items() if not all(v))
    return AssertionResult(
        name=f"assert_pass_hat_k(k={result.k}, at_least={at_least})",
        passed=ok,
        expected=at_least,
        actual=result.pass_hat_k,
        message="" if ok else (
            f"pass^{result.k} = {result.pass_hat_k:.0%} (mean {result.mean_at_k:.0%}, "
            f"pass@{result.k} {result.pass_at_k:.0%}); tasks not passing on every run: "
            f"{flaky}. First failures: {[result.failures[t][0] for t in flaky[:3]]}"
        ),
    )
