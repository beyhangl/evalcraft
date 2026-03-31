"""Tests for TrendDetector — multi-run gradual drift analysis."""

from __future__ import annotations

import math
import pytest

from evalcraft.core.models import Cassette, Span, SpanKind
from evalcraft.regression.trend import TrendDetector, TrendReport, TrendRegression
from evalcraft.regression.detector import Severity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cassette(
    name: str,
    cost: float = 0.0,
    duration_ms: float = 0.0,
    llm_calls: int = 0,
    tool_calls: int = 0,
    error_count: int = 0,
) -> Cassette:
    """Build a minimal cassette with the given aggregate metrics."""
    c = Cassette(name=name)
    # Set aggregates directly (bypassing span accumulation) for test speed
    c.total_cost_usd = cost
    c.total_duration_ms = duration_ms
    c.llm_call_count = llm_calls
    c.tool_call_count = tool_calls
    # Inject error spans if requested
    for i in range(error_count):
        span = Span(
            span_id=f"err-{name}-{i}",
            kind=SpanKind.AGENT_STEP,
            error=f"simulated error {i}",
        )
        c.spans.append(span)
    return c


def _flat(value: float, n: int, prefix: str = "run") -> list[Cassette]:
    """N cassettes with constant cost (no drift)."""
    return [_make_cassette(f"{prefix}{i}", cost=value) for i in range(n)]


# ---------------------------------------------------------------------------
# Basic API
# ---------------------------------------------------------------------------


class TestTrendDetectorInit:
    def test_default_parameters(self):
        d = TrendDetector()
        assert d.window_size == 5
        assert d.slope_warning_pct == 0.05
        assert d.slope_critical_pct == 0.15

    def test_custom_parameters(self):
        d = TrendDetector(window_size=10, slope_warning_pct=0.02, slope_critical_pct=0.08)
        assert d.window_size == 10
        assert d.slope_warning_pct == 0.02

    def test_window_size_below_minimum_raises(self):
        with pytest.raises(ValueError, match="window_size must be at least 2"):
            TrendDetector(window_size=1)

    def test_fewer_than_3_cassettes_returns_empty_report(self):
        d = TrendDetector()
        cassettes = _flat(0.10, 2)
        report = d.detect(cassettes)
        assert not report.has_drift
        assert report.run_count == 2


# ---------------------------------------------------------------------------
# No drift
# ---------------------------------------------------------------------------


class TestNoDrift:
    def test_constant_cost_no_drift(self):
        d = TrendDetector()
        cassettes = _flat(0.10, 6)
        report = d.detect(cassettes)
        assert not report.has_drift
        assert report.run_count == 5  # window_size=5, last 5 of 6

    def test_decreasing_cost_no_drift(self):
        """Decreasing metrics should not trigger drift alerts."""
        cassettes = [
            _make_cassette(f"run{i}", cost=0.20 - i * 0.02) for i in range(5)
        ]
        d = TrendDetector()
        report = d.detect(cassettes)
        assert not report.has_drift

    def test_zero_cost_no_drift(self):
        """Zero-cost cassettes (below min_baseline) should be skipped."""
        cassettes = [_make_cassette(f"run{i}", cost=0.0) for i in range(5)]
        d = TrendDetector()
        report = d.detect(cassettes)
        assert not report.has_drift


# ---------------------------------------------------------------------------
# Warning drift
# ---------------------------------------------------------------------------


class TestWarningDrift:
    def test_cost_warning_threshold(self):
        """Cost growing at ~8%/run should be WARNING."""
        # baseline $0.10, grows 8% per run: 0.10, 0.108, 0.117, 0.126, 0.136
        cassettes = [
            _make_cassette(f"run{i}", cost=0.10 * (1.08 ** i)) for i in range(5)
        ]
        d = TrendDetector(slope_warning_pct=0.05, slope_critical_pct=0.20)
        report = d.detect(cassettes)
        assert report.has_drift
        cost_trends = [t for t in report.trends if t.category == "cost_usd"]
        assert len(cost_trends) == 1
        assert cost_trends[0].severity == Severity.WARNING

    def test_llm_call_warning(self):
        """LLM call count growing at ~10%/run should be WARNING."""
        cassettes = [
            _make_cassette(f"run{i}", llm_calls=int(10 * (1.10 ** i))) for i in range(5)
        ]
        d = TrendDetector()
        report = d.detect(cassettes)
        llm_trends = [t for t in report.trends if t.category == "llm_calls"]
        assert len(llm_trends) == 1
        assert llm_trends[0].severity in (Severity.WARNING, Severity.CRITICAL)

    def test_duration_warning(self):
        """Latency growing at 6%/run should be WARNING."""
        cassettes = [
            _make_cassette(f"run{i}", duration_ms=500 * (1.06 ** i)) for i in range(5)
        ]
        d = TrendDetector()
        report = d.detect(cassettes)
        dur_trends = [t for t in report.trends if t.category == "duration_ms"]
        assert dur_trends, "Expected duration trend"
        assert dur_trends[0].severity == Severity.WARNING


# ---------------------------------------------------------------------------
# Critical drift
# ---------------------------------------------------------------------------


class TestCriticalDrift:
    def test_cost_critical_threshold(self):
        """Cost growing at ~20%/run should be CRITICAL."""
        cassettes = [
            _make_cassette(f"run{i}", cost=0.10 * (1.20 ** i)) for i in range(5)
        ]
        d = TrendDetector(slope_warning_pct=0.05, slope_critical_pct=0.15)
        report = d.detect(cassettes)
        assert report.has_critical_drift
        cost_trends = [t for t in report.trends if t.category == "cost_usd"]
        assert cost_trends[0].severity == Severity.CRITICAL

    def test_has_critical_drift_property(self):
        cassettes = [
            _make_cassette(f"run{i}", cost=0.10 * (1.25 ** i)) for i in range(5)
        ]
        report = TrendDetector().detect(cassettes)
        assert report.has_critical_drift
        assert report.max_severity == Severity.CRITICAL


# ---------------------------------------------------------------------------
# Window slicing
# ---------------------------------------------------------------------------


class TestWindowSlicing:
    def test_window_size_respected(self):
        """Only the last window_size cassettes should be analysed."""
        # First 5 runs constant; last 5 drifting heavily
        flat = _flat(0.10, 5, prefix="flat")
        drifting = [
            _make_cassette(f"drift{i}", cost=0.10 * (1.30 ** i)) for i in range(5)
        ]
        d = TrendDetector(window_size=5)
        # Only drifting window visible
        report = d.detect(flat + drifting)
        assert report.cassette_names[0].startswith("drift")
        assert report.has_drift

    def test_fewer_cassettes_than_window_size(self):
        """When fewer cassettes than window_size are provided, all are used."""
        cassettes = [
            _make_cassette(f"run{i}", cost=0.10 * (1.10 ** i)) for i in range(3)
        ]
        d = TrendDetector(window_size=10)
        report = d.detect(cassettes)
        assert report.run_count == 3


# ---------------------------------------------------------------------------
# TrendReport API
# ---------------------------------------------------------------------------


class TestTrendReportAPI:
    def _drifting_report(self) -> TrendReport:
        cassettes = [
            _make_cassette(f"run{i}", cost=0.10 * (1.20 ** i)) for i in range(5)
        ]
        return TrendDetector().detect(cassettes)

    def test_by_severity_filter(self):
        report = self._drifting_report()
        critical = report.by_severity(Severity.CRITICAL)
        for t in critical:
            assert t.severity == Severity.CRITICAL

    def test_to_dict_structure(self):
        report = self._drifting_report()
        d = report.to_dict()
        assert "run_count" in d
        assert "cassette_names" in d
        assert "has_drift" in d
        assert "has_critical_drift" in d
        assert "trends" in d
        assert isinstance(d["trends"], list)

    def test_summary_no_drift(self):
        cassettes = _flat(0.10, 4)
        report = TrendDetector().detect(cassettes)
        summary = report.summary()
        assert "No drift" in summary

    def test_summary_with_drift(self):
        cassettes = [
            _make_cassette(f"run{i}", cost=0.10 * (1.25 ** i)) for i in range(5)
        ]
        report = TrendDetector().detect(cassettes)
        summary = report.summary()
        assert "Drift detected" in summary
        assert "run" in summary

    def test_trend_regression_to_dict(self):
        cassettes = [
            _make_cassette(f"run{i}", cost=0.10 * (1.20 ** i)) for i in range(5)
        ]
        report = TrendDetector().detect(cassettes)
        if report.trends:
            d = report.trends[0].to_dict()
            assert "category" in d
            assert "slope_per_run" in d
            assert "slope_pct" in d
            assert "values" in d


# ---------------------------------------------------------------------------
# Linear slope correctness
# ---------------------------------------------------------------------------


class TestLinearSlope:
    def test_known_slope(self):
        """Linear sequence 0,1,2,3,4 has slope exactly 1.0."""
        slope = TrendDetector._linear_slope([float(i) for i in range(5)])
        assert math.isclose(slope, 1.0, rel_tol=1e-9)

    def test_constant_sequence_slope_zero(self):
        slope = TrendDetector._linear_slope([3.0, 3.0, 3.0, 3.0])
        assert slope == 0.0

    def test_negative_slope(self):
        slope = TrendDetector._linear_slope([4.0, 3.0, 2.0, 1.0])
        assert slope < 0
