"""Tests for evalcraft.eval.statistical — statistical evaluation mode."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from evalcraft.core.models import AgentRun, AssertionResult, Cassette, Span, SpanKind
from evalcraft.eval.statistical import StatisticalResult, _wilson_ci, eval_n


@pytest.fixture
def weather_cassette():
    c = Cassette(name="weather_test")
    c.output_text = "It's 18C and cloudy in Paris."
    return c


class TestEvalN:
    def test_all_pass(self, weather_cassette):
        def always_pass(cassette, **kwargs):
            return AssertionResult(name="test", passed=True)

        result = eval_n(weather_cassette, always_pass, n=5)

        assert result.n == 5
        assert result.passes == 5
        assert result.failures == 0
        assert result.pass_rate == 1.0
        assert result.passed is True
        assert len(result.results) == 5

    def test_all_fail(self, weather_cassette):
        def always_fail(cassette, **kwargs):
            return AssertionResult(name="test", passed=False, message="bad")

        result = eval_n(weather_cassette, always_fail, n=3)

        assert result.passes == 0
        assert result.failures == 3
        assert result.pass_rate == 0.0
        assert result.passed is False

    def test_mixed_results(self, weather_cassette):
        call_count = 0

        def alternating(cassette, **kwargs):
            nonlocal call_count
            call_count += 1
            return AssertionResult(name="test", passed=(call_count % 2 == 1))

        result = eval_n(weather_cassette, alternating, n=5)

        assert result.passes == 3  # 1, 3, 5 pass
        assert result.failures == 2  # 2, 4 fail
        assert result.pass_rate == pytest.approx(0.6)
        assert result.passed is True  # >= 0.5

    def test_passes_kwargs_to_scorer(self, weather_cassette):
        received_kwargs = {}

        def capture_kwargs(cassette, **kwargs):
            received_kwargs.update(kwargs)
            return AssertionResult(name="test", passed=True)

        eval_n(weather_cassette, capture_kwargs, n=1, criteria="test criteria", threshold=0.8)

        assert received_kwargs["criteria"] == "test criteria"
        assert received_kwargs["threshold"] == 0.8

    def test_works_with_agent_run(self, weather_cassette):
        run = AgentRun(cassette=weather_cassette)

        def scorer(cassette, **kwargs):
            return AssertionResult(name="test", passed=True)

        result = eval_n(run, scorer, n=3)
        assert result.passes == 3

    def test_n_must_be_positive(self, weather_cassette):
        with pytest.raises(ValueError, match="n must be >= 1"):
            eval_n(weather_cassette, lambda c: AssertionResult(), n=0)

    def test_confidence_interval_computed(self, weather_cassette):
        def always_pass(cassette, **kwargs):
            return AssertionResult(name="test", passed=True)

        result = eval_n(weather_cassette, always_pass, n=10)

        assert result.ci_lower > 0.0
        assert result.ci_upper <= 1.0
        assert result.ci_lower <= result.pass_rate <= result.ci_upper

    def test_numeric_scores_extracted(self, weather_cassette):
        call_count = 0

        def scorer_with_score(cassette, **kwargs):
            nonlocal call_count
            call_count += 1
            score = 0.7 + call_count * 0.05
            return AssertionResult(name="test", passed=True, actual=score)

        result = eval_n(weather_cassette, scorer_with_score, n=4)

        assert result.mean_score > 0
        assert result.std_score >= 0

    def test_to_dict(self, weather_cassette):
        def scorer(cassette, **kwargs):
            return AssertionResult(name="test", passed=True)

        result = eval_n(weather_cassette, scorer, n=2)
        d = result.to_dict()

        assert d["n"] == 2
        assert d["passes"] == 2
        assert d["pass_rate"] == 1.0
        assert "ci_lower" in d
        assert "ci_upper" in d
        assert len(d["results"]) == 2


class TestWilsonCI:
    def test_all_successes(self):
        lower, upper = _wilson_ci(10, 10)
        assert lower > 0.5
        assert upper == pytest.approx(1.0, abs=0.01)

    def test_no_successes(self):
        lower, upper = _wilson_ci(0, 10)
        assert lower == pytest.approx(0.0, abs=0.01)
        assert upper < 0.5

    def test_half_successes(self):
        lower, upper = _wilson_ci(5, 10)
        assert lower < 0.5
        assert upper > 0.5

    def test_zero_total(self):
        lower, upper = _wilson_ci(0, 0)
        assert lower == 0.0
        assert upper == 0.0

    def test_single_trial(self):
        lower, upper = _wilson_ci(1, 1)
        assert 0.0 < lower < 1.0
        assert 0.0 < upper <= 1.0

    def test_ci_width_decreases_with_n(self):
        _, upper_small = _wilson_ci(5, 10)
        _, upper_large = _wilson_ci(50, 100)
        width_small = upper_small - _wilson_ci(5, 10)[0]
        width_large = upper_large - _wilson_ci(50, 100)[0]
        assert width_large < width_small
