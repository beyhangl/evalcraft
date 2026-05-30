"""Live-eval mode — run scorers against the REAL model on a golden input set.

Replay tests a *recorded* run, so it cannot catch model / prompt / retrieval
drift (see ``docs/user-guide/replay.md``). Live-eval is the complementary layer:
it executes your agent **live** over a curated set of *inputs* (not frozen
outputs), scores each run, and compares aggregate scores against a stored
baseline so quality regressions can fail the build.

This path makes real model calls — it is **non-deterministic and costs money**.
Run it in a nightly / gated job, not on every commit.

Example::

    from evalcraft.eval.live import LiveEvalCase, run_live_eval, compare_to_baseline
    from evalcraft import assert_output_contains

    cases = [
        LiveEvalCase(
            name="paris_weather",
            input="What's the weather in Paris?",
            scorers=[lambda c: assert_output_contains(c, "Paris")],
        ),
    ]

    def runner(case):
        # Call your real agent here; return its output (str) or a Cassette/AgentRun.
        return my_agent.run(case.input)

    result = run_live_eval(cases, runner)        # live, paid, non-deterministic
    print(result.pass_rate)

    # Gate against a saved baseline (e.g. last good run)
    comparison = compare_to_baseline(result, LiveEvalResult.load("baseline.json"))
    assert comparison.passed, comparison.summary()
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Union

from evalcraft.core.models import AgentRun, AssertionResult, Cassette

# A scorer takes the (live) cassette and returns an AssertionResult.
Scorer = Callable[[Cassette], AssertionResult]
# A runner executes the real agent for a case and returns its output.
Runner = Callable[["LiveEvalCase"], Union[Cassette, AgentRun, str]]


@dataclass
class LiveEvalCase:
    """A golden *input* to evaluate against the live model.

    Unlike a cassette (a frozen output), a case stores an input plus the scorers
    to apply to whatever the live agent produces for it.
    """

    name: str
    input: Any
    scorers: list[Scorer] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class LiveCaseResult:
    """Outcome of evaluating a single case against the live model."""

    name: str
    passed: bool
    score: float
    assertions: list[AssertionResult] = field(default_factory=list)
    output: str = ""
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "score": self.score,
            "assertions": [a.to_dict() for a in self.assertions],
            "output": self.output,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> LiveCaseResult:
        assertions = [
            AssertionResult(
                name=a.get("name", ""),
                passed=bool(a.get("passed", False)),
                expected=a.get("expected"),
                actual=a.get("actual"),
                message=a.get("message", ""),
            )
            for a in data.get("assertions", [])
        ]
        return cls(
            name=data.get("name", ""),
            passed=bool(data.get("passed", False)),
            score=float(data.get("score", 0.0)),
            assertions=assertions,
            output=data.get("output", ""),
            error=data.get("error"),
        )


@dataclass
class LiveEvalResult:
    """Aggregate result of a live-eval run."""

    cases: list[LiveCaseResult] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.cases)

    @property
    def n_passed(self) -> int:
        return sum(1 for c in self.cases if c.passed)

    @property
    def pass_rate(self) -> float:
        return self.n_passed / self.n if self.n else 0.0

    @property
    def mean_score(self) -> float:
        return sum(c.score for c in self.cases) / self.n if self.n else 0.0

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.cases)

    def scores(self) -> dict[str, float]:
        """Per-case scores — the comparable baseline payload."""
        return {c.name: c.score for c in self.cases}

    def to_dict(self) -> dict:
        return {
            "type": "evalcraft_live_eval",
            "n": self.n,
            "n_passed": self.n_passed,
            "pass_rate": self.pass_rate,
            "mean_score": self.mean_score,
            "cases": [c.to_dict() for c in self.cases],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> LiveEvalResult:
        return cls(cases=[LiveCaseResult.from_dict(c) for c in data.get("cases", [])])

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2, default=str))
        return p

    @classmethod
    def load(cls, path: str | Path) -> LiveEvalResult:
        return cls.from_dict(json.loads(Path(path).read_text()))


@dataclass
class CaseDelta:
    """Per-case score change between a baseline and a current run."""

    name: str
    baseline_score: float
    current_score: float

    @property
    def delta(self) -> float:
        return self.current_score - self.baseline_score


@dataclass
class LiveEvalComparison:
    """Result of comparing a live-eval run against a baseline."""

    regressions: list[CaseDelta] = field(default_factory=list)
    improvements: list[CaseDelta] = field(default_factory=list)
    unchanged: list[CaseDelta] = field(default_factory=list)
    new_cases: list[str] = field(default_factory=list)
    removed_cases: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """True when no case regressed beyond the allowed drop."""
        return not self.regressions

    def summary(self) -> str:
        lines = [
            f"live-eval vs baseline: "
            f"{len(self.regressions)} regressed, "
            f"{len(self.improvements)} improved, "
            f"{len(self.unchanged)} unchanged, "
            f"{len(self.new_cases)} new, {len(self.removed_cases)} removed"
        ]
        for d in self.regressions:
            lines.append(
                f"  REGRESSION  {d.name}: {d.baseline_score:.2f} -> {d.current_score:.2f} "
                f"({d.delta:+.2f})"
            )
        return "\n".join(lines)


def _coerce_cassette(produced: Cassette | AgentRun | str) -> Cassette:
    """Normalize whatever the runner returned into a Cassette for scoring."""
    if isinstance(produced, AgentRun):
        return produced.cassette
    if isinstance(produced, Cassette):
        return produced
    cassette = Cassette(name="live")
    cassette.output_text = str(produced)
    return cassette


def run_live_eval(cases: list[LiveEvalCase], runner: Runner) -> LiveEvalResult:
    """Run each case against the live model via ``runner`` and score it.

    ``runner`` receives a :class:`LiveEvalCase` and must execute the real agent,
    returning its output as a ``str`` (or a ``Cassette`` / ``AgentRun`` for
    trace-level scoring). An exception in the runner or in a scorer fails that
    case (score ``0.0``) without aborting the whole run.

    .. warning::
        This makes real, paid, non-deterministic model calls. Use it in a
        nightly / gated job, not on the per-commit deterministic path.
    """
    results: list[LiveCaseResult] = []
    for case in cases:
        try:
            cassette = _coerce_cassette(runner(case))
        except Exception as exc:  # noqa: BLE001 - surface as a failed case
            results.append(
                LiveCaseResult(
                    name=case.name, passed=False, score=0.0, error=f"runner error: {exc}"
                )
            )
            continue

        assertions: list[AssertionResult] = []
        for scorer in case.scorers:
            try:
                assertions.append(scorer(cassette))
            except Exception as exc:  # noqa: BLE001 - a broken scorer fails the case
                assertions.append(
                    AssertionResult(
                        name=getattr(scorer, "__name__", "scorer"),
                        passed=False,
                        message=f"scorer error: {exc}",
                    )
                )

        if assertions:
            n_pass = sum(1 for a in assertions if a.passed)
            score = n_pass / len(assertions)
            passed = n_pass == len(assertions)
        else:
            # No scorers attached: a run that completed counts as a pass.
            score, passed = 1.0, True

        results.append(
            LiveCaseResult(
                name=case.name,
                passed=passed,
                score=score,
                assertions=assertions,
                output=cassette.output_text,
            )
        )

    return LiveEvalResult(cases=results)


def compare_to_baseline(
    result: LiveEvalResult,
    baseline: LiveEvalResult | Mapping[str, float],
    *,
    max_score_drop: float = 0.0,
) -> LiveEvalComparison:
    """Compare a live-eval ``result`` against a ``baseline``.

    A case is a **regression** if its score dropped by more than
    ``max_score_drop`` relative to the baseline. Cases absent from the baseline
    are reported as ``new_cases`` (never regressions); cases missing from the
    current run are ``removed_cases``.
    """
    base_scores: dict[str, float] = (
        baseline.scores() if isinstance(baseline, LiveEvalResult) else dict(baseline)
    )
    current_scores = result.scores()

    comparison = LiveEvalComparison()
    for name, current in current_scores.items():
        if name not in base_scores:
            comparison.new_cases.append(name)
            continue
        delta = CaseDelta(name=name, baseline_score=base_scores[name], current_score=current)
        if current < base_scores[name] - max_score_drop:
            comparison.regressions.append(delta)
        elif current > base_scores[name]:
            comparison.improvements.append(delta)
        else:
            comparison.unchanged.append(delta)

    for name in base_scores:
        if name not in current_scores:
            comparison.removed_cases.append(name)

    return comparison
