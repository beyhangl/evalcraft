"""Tests for evalcraft.regression — regression detection."""

import copy
import json
import pytest
from pathlib import Path

from evalcraft.core.models import Cassette, Span, SpanKind, TokenUsage
from evalcraft.regression.detector import (
    RegressionDetector,
    Regression,
    RegressionReport,
    Severity,
)


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

@pytest.fixture
def baseline():
    """A baseline cassette to detect regressions against."""
    c = Cassette(name="baseline", agent_name="test_agent")
    c.add_span(Span(
        kind=SpanKind.TOOL_CALL,
        name="tool:search",
        tool_name="web_search",
        tool_args={"query": "test"},
        tool_result={"results": ["a"]},
        duration_ms=100.0,
    ))
    c.add_span(Span(
        kind=SpanKind.TOOL_CALL,
        name="tool:summarize",
        tool_name="summarize",
        tool_args={"text": "test"},
        tool_result={"summary": "ok"},
        duration_ms=50.0,
    ))
    c.add_span(Span(
        kind=SpanKind.LLM_RESPONSE,
        name="llm:gpt-4",
        model="gpt-4",
        output="Here is the summary.",
        token_usage=TokenUsage(prompt_tokens=50, completion_tokens=20, total_tokens=70),
        cost_usd=0.005,
        duration_ms=300.0,
    ))
    c.output_text = "Here is the summary."
    c.compute_metrics()
    return c


@pytest.fixture
def detector():
    return RegressionDetector()


# ──────────────────────────────────────────────
# Severity enum
# ──────────────────────────────────────────────

class TestSeverity:
    def test_string_values(self):
        assert Severity.INFO == "INFO"
        assert Severity.WARNING == "WARNING"
        assert Severity.CRITICAL == "CRITICAL"

    def test_from_string(self):
        assert Severity("WARNING") == Severity.WARNING


# ──────────────────────────────────────────────
# Regression dataclass
# ──────────────────────────────────────────────

class TestRegression:
    def test_to_dict(self):
        r = Regression(
            category="test",
            severity=Severity.WARNING,
            message="something changed",
            golden_value=10,
            current_value=20,
        )
        d = r.to_dict()
        assert d["category"] == "test"
        assert d["severity"] == "WARNING"
        assert d["golden_value"] == 10


# ──────────────────────────────────────────────
# RegressionReport
# ──────────────────────────────────────────────

class TestRegressionReport:
    def test_empty_report(self):
        r = RegressionReport(golden_name="test")
        assert not r.has_regressions
        assert not r.has_critical
        assert not r.has_warnings
        assert r.max_severity is None

    def test_with_regressions(self):
        r = RegressionReport(
            golden_name="test",
            regressions=[
                Regression(category="a", severity=Severity.INFO, message="info"),
                Regression(category="b", severity=Severity.WARNING, message="warn"),
                Regression(category="c", severity=Severity.CRITICAL, message="crit"),
            ],
        )
        assert r.has_regressions
        assert r.has_critical
        assert r.has_warnings
        assert r.max_severity == Severity.CRITICAL

    def test_by_severity(self):
        r = RegressionReport(
            golden_name="test",
            regressions=[
                Regression(category="a", severity=Severity.INFO, message="1"),
                Regression(category="b", severity=Severity.INFO, message="2"),
                Regression(category="c", severity=Severity.WARNING, message="3"),
            ],
        )
        assert len(r.by_severity(Severity.INFO)) == 2
        assert len(r.by_severity(Severity.WARNING)) == 1
        assert len(r.by_severity(Severity.CRITICAL)) == 0

    def test_to_dict(self):
        r = RegressionReport(
            golden_name="test",
            regressions=[
                Regression(category="a", severity=Severity.INFO, message="msg"),
            ],
        )
        d = r.to_dict()
        assert d["golden_name"] == "test"
        assert d["has_regressions"] is True
        assert d["regression_count"] == 1
        assert d["max_severity"] == "INFO"

    def test_summary_no_regressions(self):
        r = RegressionReport(golden_name="test")
        s = r.summary()
        assert "No regressions" in s

    def test_summary_with_regressions(self):
        r = RegressionReport(
            golden_name="test",
            regressions=[
                Regression(category="cost", severity=Severity.WARNING, message="cost went up"),
            ],
        )
        s = r.summary()
        assert "WARNING" in s
        assert "cost went up" in s


# ──────────────────────────────────────────────
# RegressionDetector — no regressions
# ──────────────────────────────────────────────

class TestDetectorNoRegressions:
    def test_identical_cassettes(self, detector, baseline):
        current = copy.deepcopy(baseline)
        report = detector.compare(baseline, current)
        assert not report.has_regressions

    def test_minor_token_change(self, detector, baseline):
        current = copy.deepcopy(baseline)
        for s in current.spans:
            if s.token_usage:
                s.token_usage = TokenUsage(
                    prompt_tokens=55,
                    completion_tokens=22,
                    total_tokens=77,  # ~10% increase, under 1.3x warning
                )
        report = detector.compare(baseline, current)
        token_regs = [r for r in report.regressions if r.category == "token_bloat"]
        assert len(token_regs) == 0


# ──────────────────────────────────────────────
# RegressionDetector — tool sequence
# ──────────────────────────────────────────────

class TestDetectorToolSequence:
    def test_detects_removed_tool(self, detector, baseline):
        current = copy.deepcopy(baseline)
        # Remove the summarize tool
        current.spans = [s for s in current.spans if s.tool_name != "summarize"]
        report = detector.compare(baseline, current)
        tool_regs = [r for r in report.regressions if r.category == "tool_sequence"]
        assert any(r.severity == Severity.CRITICAL for r in tool_regs)
        assert any("removed" in r.message.lower() for r in tool_regs)

    def test_detects_added_tool(self, detector, baseline):
        current = copy.deepcopy(baseline)
        current.add_span(Span(
            kind=SpanKind.TOOL_CALL,
            tool_name="new_tool",
        ))
        report = detector.compare(baseline, current)
        tool_regs = [r for r in report.regressions if r.category == "tool_sequence"]
        assert any(r.severity == Severity.WARNING for r in tool_regs)
        assert any("added" in r.message.lower() for r in tool_regs)

    def test_detects_order_change(self, detector, baseline):
        current = copy.deepcopy(baseline)
        # Swap the two tool calls
        tools = [s for s in current.spans if s.kind == SpanKind.TOOL_CALL]
        non_tools = [s for s in current.spans if s.kind != SpanKind.TOOL_CALL]
        current.spans = list(reversed(tools)) + non_tools
        report = detector.compare(baseline, current)
        tool_regs = [r for r in report.regressions if r.category == "tool_sequence"]
        assert any("order" in r.message.lower() for r in tool_regs)


# ──────────────────────────────────────────────
# RegressionDetector — output drift
# ──────────────────────────────────────────────

class TestDetectorOutputDrift:
    def test_detects_output_change(self, detector, baseline):
        current = copy.deepcopy(baseline)
        current.output_text = "Completely different output."
        report = detector.compare(baseline, current)
        output_regs = [r for r in report.regressions if r.category == "output_drift"]
        assert len(output_regs) == 1
        assert output_regs[0].severity == Severity.INFO

    def test_detects_empty_output(self, detector, baseline):
        current = copy.deepcopy(baseline)
        current.output_text = ""
        report = detector.compare(baseline, current)
        output_regs = [r for r in report.regressions if r.category == "output_drift"]
        assert len(output_regs) == 1
        assert output_regs[0].severity == Severity.CRITICAL

    def test_no_regression_on_same_output(self, detector, baseline):
        current = copy.deepcopy(baseline)
        report = detector.compare(baseline, current)
        output_regs = [r for r in report.regressions if r.category == "output_drift"]
        assert len(output_regs) == 0


# ──────────────────────────────────────────────
# RegressionDetector — token bloat
# ──────────────────────────────────────────────

class TestDetectorTokenBloat:
    def test_warning_on_moderate_increase(self, detector, baseline):
        current = copy.deepcopy(baseline)
        for s in current.spans:
            if s.token_usage:
                # 1.4x increase — between 1.3x warning and 2.0x critical
                s.token_usage = TokenUsage(
                    prompt_tokens=70,
                    completion_tokens=28,
                    total_tokens=98,
                )
        report = detector.compare(baseline, current)
        token_regs = [r for r in report.regressions if r.category == "token_bloat"]
        assert len(token_regs) == 1
        assert token_regs[0].severity == Severity.WARNING

    def test_critical_on_large_increase(self, detector, baseline):
        current = copy.deepcopy(baseline)
        for s in current.spans:
            if s.token_usage:
                # 3x increase
                s.token_usage = TokenUsage(
                    prompt_tokens=150,
                    completion_tokens=60,
                    total_tokens=210,
                )
        report = detector.compare(baseline, current)
        token_regs = [r for r in report.regressions if r.category == "token_bloat"]
        assert len(token_regs) == 1
        assert token_regs[0].severity == Severity.CRITICAL

    def test_no_regression_when_golden_has_zero_tokens(self, detector):
        golden = Cassette(name="zero")
        golden.add_span(Span(kind=SpanKind.TOOL_CALL, tool_name="a"))
        golden.compute_metrics()

        current = copy.deepcopy(golden)
        current.add_span(Span(
            kind=SpanKind.LLM_RESPONSE,
            token_usage=TokenUsage(total_tokens=100),
        ))
        current.compute_metrics()

        report = detector.compare(golden, current)
        token_regs = [r for r in report.regressions if r.category == "token_bloat"]
        assert len(token_regs) == 0


# ──────────────────────────────────────────────
# RegressionDetector — cost increase
# ──────────────────────────────────────────────

class TestDetectorCostIncrease:
    def test_warning_on_moderate_increase(self, detector, baseline):
        current = copy.deepcopy(baseline)
        for s in current.spans:
            if s.cost_usd:
                s.cost_usd = 0.0075  # 1.5x
        report = detector.compare(baseline, current)
        cost_regs = [r for r in report.regressions if r.category == "cost_increase"]
        assert len(cost_regs) == 1
        assert cost_regs[0].severity == Severity.WARNING

    def test_critical_on_large_increase(self, detector, baseline):
        current = copy.deepcopy(baseline)
        for s in current.spans:
            if s.cost_usd:
                s.cost_usd = 0.05  # 10x
        report = detector.compare(baseline, current)
        cost_regs = [r for r in report.regressions if r.category == "cost_increase"]
        assert len(cost_regs) == 1
        assert cost_regs[0].severity == Severity.CRITICAL


# ──────────────────────────────────────────────
# RegressionDetector — latency increase
# ──────────────────────────────────────────────

class TestDetectorLatencyIncrease:
    def test_warning_on_moderate_increase(self, detector, baseline):
        current = copy.deepcopy(baseline)
        for s in current.spans:
            s.duration_ms *= 2  # 2x — between 1.5x warning and 3.0x critical
        report = detector.compare(baseline, current)
        lat_regs = [r for r in report.regressions if r.category == "latency_increase"]
        assert len(lat_regs) == 1
        assert lat_regs[0].severity == Severity.WARNING

    def test_critical_on_large_increase(self, detector, baseline):
        current = copy.deepcopy(baseline)
        for s in current.spans:
            s.duration_ms *= 5  # 5x
        report = detector.compare(baseline, current)
        lat_regs = [r for r in report.regressions if r.category == "latency_increase"]
        assert len(lat_regs) == 1
        assert lat_regs[0].severity == Severity.CRITICAL


# ──────────────────────────────────────────────
# RegressionDetector — call counts
# ──────────────────────────────────────────────

class TestDetectorCallCounts:
    def test_detects_llm_call_increase(self, detector, baseline):
        current = copy.deepcopy(baseline)
        current.add_span(Span(
            kind=SpanKind.LLM_RESPONSE,
            token_usage=TokenUsage(total_tokens=10),
            cost_usd=0.001,
        ))
        report = detector.compare(baseline, current)
        llm_regs = [r for r in report.regressions if r.category == "llm_call_count"]
        assert len(llm_regs) == 1

    def test_detects_tool_call_increase(self, detector, baseline):
        current = copy.deepcopy(baseline)
        current.add_span(Span(
            kind=SpanKind.TOOL_CALL,
            tool_name="web_search",
        ))
        current.add_span(Span(
            kind=SpanKind.TOOL_CALL,
            tool_name="web_search",
        ))
        report = detector.compare(baseline, current)
        tool_regs = [r for r in report.regressions if r.category == "tool_call_count"]
        assert len(tool_regs) == 1


# ──────────────────────────────────────────────
# RegressionDetector — errors
# ──────────────────────────────────────────────

class TestDetectorErrors:
    def test_detects_new_errors(self, detector, baseline):
        current = copy.deepcopy(baseline)
        current.add_span(Span(
            kind=SpanKind.TOOL_CALL,
            tool_name="broken_tool",
            error="Connection timeout",
        ))
        report = detector.compare(baseline, current)
        err_regs = [r for r in report.regressions if r.category == "new_errors"]
        assert len(err_regs) == 1
        assert err_regs[0].severity == Severity.CRITICAL
        assert "timeout" in err_regs[0].message.lower()

    def test_no_regression_when_same_error_count(self, detector, baseline):
        # Add an error to both
        baseline.add_span(Span(
            kind=SpanKind.TOOL_CALL,
            error="known error",
        ))
        baseline.compute_metrics()

        current = copy.deepcopy(baseline)
        report = detector.compare(baseline, current)
        err_regs = [r for r in report.regressions if r.category == "new_errors"]
        assert len(err_regs) == 0


# ──────────────────────────────────────────────
# RegressionDetector — custom thresholds
# ──────────────────────────────────────────────

class TestDetectorCustomThresholds:
    def test_custom_cost_thresholds(self, baseline):
        detector = RegressionDetector(
            cost_warning_ratio=1.0,
            cost_critical_ratio=1.1,
        )
        current = copy.deepcopy(baseline)
        for s in current.spans:
            if s.cost_usd:
                s.cost_usd = 0.006  # 20% increase
        report = detector.compare(baseline, current)
        cost_regs = [r for r in report.regressions if r.category == "cost_increase"]
        assert len(cost_regs) == 1
        assert cost_regs[0].severity == Severity.CRITICAL

    def test_custom_token_thresholds(self, baseline):
        detector = RegressionDetector(
            token_warning_ratio=1.01,
            token_critical_ratio=1.05,
        )
        current = copy.deepcopy(baseline)
        for s in current.spans:
            if s.token_usage:
                s.token_usage = TokenUsage(total_tokens=80)  # ~14% increase
        report = detector.compare(baseline, current)
        token_regs = [r for r in report.regressions if r.category == "token_bloat"]
        assert len(token_regs) == 1
        assert token_regs[0].severity == Severity.CRITICAL


# ──────────────────────────────────────────────
# RegressionDetector — check_directory
# ──────────────────────────────────────────────

class TestDetectorCheckDirectory:
    def test_matches_by_filename(self, detector, baseline, tmp_path):
        golden_dir = tmp_path / "golden"
        current_dir = tmp_path / "current"
        golden_dir.mkdir()
        current_dir.mkdir()

        baseline.save(golden_dir / "agent.json")
        current = copy.deepcopy(baseline)
        current.save(current_dir / "agent.json")

        reports = detector.check_directory(golden_dir, current_dir)
        assert len(reports) == 1
        assert not reports[0].has_regressions

    def test_new_cassette_without_baseline(self, detector, baseline, tmp_path):
        golden_dir = tmp_path / "golden"
        current_dir = tmp_path / "current"
        golden_dir.mkdir()
        current_dir.mkdir()

        current = copy.deepcopy(baseline)
        current.save(current_dir / "new_agent.json")

        reports = detector.check_directory(golden_dir, current_dir)
        assert len(reports) == 1
        assert reports[0].regressions[0].category == "new_cassette"
        assert reports[0].regressions[0].severity == Severity.INFO

    def test_directory_with_regressions(self, detector, baseline, tmp_path):
        golden_dir = tmp_path / "golden"
        current_dir = tmp_path / "current"
        golden_dir.mkdir()
        current_dir.mkdir()

        baseline.save(golden_dir / "agent.json")
        current = copy.deepcopy(baseline)
        current.output_text = ""  # Empty output — critical regression
        current.save(current_dir / "agent.json")

        reports = detector.check_directory(golden_dir, current_dir)
        assert len(reports) == 1
        assert reports[0].has_critical


# ──────────────────────────────────────────────
# RegressionDetector — combined scenario
# ──────────────────────────────────────────────

class TestDetectorCombinedScenarios:
    def test_multiple_regressions_in_one_report(self, detector, baseline):
        """A cassette that regresses on multiple dimensions."""
        current = copy.deepcopy(baseline)
        # Remove a tool
        current.spans = [s for s in current.spans if s.tool_name != "summarize"]
        # Add errors
        current.add_span(Span(
            kind=SpanKind.TOOL_CALL,
            tool_name="broken",
            error="timeout",
        ))
        # Increase cost
        for s in current.spans:
            if s.cost_usd:
                s.cost_usd = 0.05

        report = detector.compare(baseline, current)
        assert report.has_regressions
        assert report.has_critical
        categories = {r.category for r in report.regressions}
        assert "tool_sequence" in categories
        assert "new_errors" in categories
        assert "cost_increase" in categories

    def test_report_includes_metadata_ratios(self, detector, baseline):
        current = copy.deepcopy(baseline)
        for s in current.spans:
            if s.token_usage:
                s.token_usage = TokenUsage(total_tokens=200)
        report = detector.compare(baseline, current)
        token_regs = [r for r in report.regressions if r.category == "token_bloat"]
        assert len(token_regs) == 1
        assert "ratio" in token_regs[0].metadata
        assert token_regs[0].metadata["ratio"] > 2.0
