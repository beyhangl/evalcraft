"""Tests for evalcraft.golden — golden-set management."""

import copy
import json
import pytest
from pathlib import Path

from evalcraft.core.models import Cassette, Span, SpanKind, TokenUsage
from evalcraft.golden.manager import (
    GoldenSet,
    ComparisonField,
    ComparisonResult,
    Thresholds,
)


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

@pytest.fixture
def golden_cassette():
    """A cassette representing the golden baseline."""
    c = Cassette(name="golden_baseline", agent_name="weather_agent", framework="test")
    c.add_span(Span(
        kind=SpanKind.TOOL_CALL,
        name="tool:get_weather",
        tool_name="get_weather",
        tool_args={"city": "NYC"},
        tool_result={"temp": 72, "condition": "sunny"},
        duration_ms=100.0,
    ))
    c.add_span(Span(
        kind=SpanKind.LLM_RESPONSE,
        name="llm:gpt-4",
        model="gpt-4",
        output="It is 72F and sunny in NYC.",
        token_usage=TokenUsage(prompt_tokens=20, completion_tokens=10, total_tokens=30),
        cost_usd=0.001,
        duration_ms=200.0,
    ))
    c.output_text = "It is 72F and sunny in NYC."
    c.input_text = "What is the weather?"
    return c


@pytest.fixture
def golden_set(golden_cassette):
    """A golden set with one baseline cassette."""
    gs = GoldenSet(name="weather_test", description="Weather agent baseline")
    gs.add_cassette(golden_cassette)
    return gs


# ──────────────────────────────────────────────
# Thresholds
# ──────────────────────────────────────────────

class TestThresholds:
    def test_defaults(self):
        t = Thresholds()
        assert t.tool_sequence_must_match is True
        assert t.output_must_match is False
        assert t.max_token_increase_ratio == 1.5
        assert t.max_cost_increase_ratio == 2.0
        assert t.max_latency_increase_ratio == 3.0
        assert t.max_tokens is None
        assert t.max_cost_usd is None
        assert t.max_latency_ms is None

    def test_to_dict(self):
        t = Thresholds(max_tokens=1000)
        d = t.to_dict()
        assert d["max_tokens"] == 1000
        assert d["tool_sequence_must_match"] is True

    def test_roundtrip(self):
        t = Thresholds(
            tool_sequence_must_match=False,
            output_must_match=True,
            max_token_increase_ratio=2.0,
            max_tokens=5000,
        )
        restored = Thresholds.from_dict(t.to_dict())
        assert restored.tool_sequence_must_match is False
        assert restored.output_must_match is True
        assert restored.max_token_increase_ratio == 2.0
        assert restored.max_tokens == 5000


# ──────────────────────────────────────────────
# ComparisonField
# ──────────────────────────────────────────────

class TestComparisonField:
    def test_to_dict(self):
        f = ComparisonField(
            name="tool_sequence",
            passed=False,
            golden_value=["a"],
            candidate_value=["b"],
            message="mismatch",
        )
        d = f.to_dict()
        assert d["name"] == "tool_sequence"
        assert d["passed"] is False
        assert d["message"] == "mismatch"


# ──────────────────────────────────────────────
# ComparisonResult
# ──────────────────────────────────────────────

class TestComparisonResult:
    def test_defaults(self):
        r = ComparisonResult()
        assert r.passed is True
        assert r.fields == []

    def test_failed_fields(self):
        r = ComparisonResult(
            passed=False,
            fields=[
                ComparisonField(name="a", passed=True),
                ComparisonField(name="b", passed=False),
                ComparisonField(name="c", passed=False),
            ],
        )
        assert len(r.failed_fields) == 2

    def test_to_dict(self):
        r = ComparisonResult(passed=True, golden_name="test", golden_version=2)
        d = r.to_dict()
        assert d["passed"] is True
        assert d["golden_name"] == "test"
        assert d["golden_version"] == 2

    def test_summary_pass(self):
        r = ComparisonResult(
            passed=True,
            golden_name="test",
            golden_version=1,
            fields=[ComparisonField(name="tool_sequence", passed=True)],
        )
        s = r.summary()
        assert "PASS" in s
        assert "test" in s

    def test_summary_fail(self):
        r = ComparisonResult(
            passed=False,
            golden_name="test",
            golden_version=1,
            fields=[
                ComparisonField(name="tool_sequence", passed=False, message="changed"),
            ],
        )
        s = r.summary()
        assert "FAIL" in s
        assert "changed" in s


# ──────────────────────────────────────────────
# GoldenSet construction
# ──────────────────────────────────────────────

class TestGoldenSetConstruction:
    def test_defaults(self):
        gs = GoldenSet()
        assert gs.name == ""
        assert gs.version == 1
        assert gs.cassette_count == 0
        assert gs.get_primary_cassette() is None

    def test_with_name_and_description(self):
        gs = GoldenSet(name="test", description="A test golden set")
        assert gs.name == "test"
        assert gs.description == "A test golden set"

    def test_add_cassette(self, golden_cassette):
        gs = GoldenSet(name="test")
        gs.add_cassette(golden_cassette)
        assert gs.cassette_count == 1
        assert gs.get_primary_cassette() is not None

    def test_add_cassette_deep_copies(self, golden_cassette):
        gs = GoldenSet(name="test")
        gs.add_cassette(golden_cassette)
        golden_cassette.name = "modified"
        assert gs.get_primary_cassette().name != "modified"

    def test_cassettes_returns_copy(self, golden_set):
        cassettes = golden_set.cassettes
        cassettes.clear()
        assert golden_set.cassette_count == 1

    def test_bump_version(self, golden_set):
        assert golden_set.version == 1
        new_v = golden_set.bump_version()
        assert new_v == 2
        assert golden_set.version == 2


# ──────────────────────────────────────────────
# GoldenSet persistence
# ──────────────────────────────────────────────

class TestGoldenSetPersistence:
    def test_to_dict_structure(self, golden_set):
        d = golden_set.to_dict()
        assert d["evalcraft_golden_set"] is True
        assert d["name"] == "weather_test"
        assert d["version"] == 1
        assert len(d["cassettes"]) == 1
        assert "thresholds" in d

    def test_from_dict(self, golden_set):
        d = golden_set.to_dict()
        restored = GoldenSet.from_dict(d)
        assert restored.name == golden_set.name
        assert restored.version == golden_set.version
        assert restored.cassette_count == golden_set.cassette_count

    def test_save_and_load(self, golden_set, tmp_path):
        path = tmp_path / "test.golden.json"
        golden_set.save(path)
        assert path.exists()

        loaded = GoldenSet.load(path)
        assert loaded.name == golden_set.name
        assert loaded.version == golden_set.version
        assert loaded.cassette_count == 1

    def test_save_creates_parent_dirs(self, golden_set, tmp_path):
        path = tmp_path / "deep" / "nested" / "golden.json"
        golden_set.save(path)
        assert path.exists()

    def test_roundtrip_preserves_thresholds(self, tmp_path):
        gs = GoldenSet(
            name="test",
            thresholds=Thresholds(max_tokens=5000, output_must_match=True),
        )
        gs.add_cassette(Cassette(name="c1"))
        path = tmp_path / "gs.json"
        gs.save(path)

        loaded = GoldenSet.load(path)
        assert loaded.thresholds.max_tokens == 5000
        assert loaded.thresholds.output_must_match is True

    def test_save_produces_valid_json(self, golden_set, tmp_path):
        path = tmp_path / "test.golden.json"
        golden_set.save(path)
        with open(path) as f:
            data = json.load(f)
        assert data["evalcraft_golden_set"] is True


# ──────────────────────────────────────────────
# GoldenSet comparison — passing
# ──────────────────────────────────────────────

class TestGoldenSetComparePass:
    def test_identical_cassette_passes(self, golden_set, golden_cassette):
        candidate = copy.deepcopy(golden_cassette)
        result = golden_set.compare(candidate)
        assert result.passed
        assert len(result.failed_fields) == 0

    def test_pass_with_minor_token_increase(self, golden_set, golden_cassette):
        candidate = copy.deepcopy(golden_cassette)
        # Increase tokens by 20% (under 1.5x threshold)
        for s in candidate.spans:
            if s.token_usage:
                s.token_usage = TokenUsage(
                    prompt_tokens=24,
                    completion_tokens=12,
                    total_tokens=36,
                )
        result = golden_set.compare(candidate)
        assert result.passed

    def test_pass_with_minor_cost_increase(self, golden_set, golden_cassette):
        candidate = copy.deepcopy(golden_cassette)
        # 50% cost increase (under 2.0x threshold)
        for s in candidate.spans:
            if s.cost_usd:
                s.cost_usd = 0.0015
        result = golden_set.compare(candidate)
        assert result.passed

    def test_pass_with_different_output_when_not_required(self, golden_set, golden_cassette):
        candidate = copy.deepcopy(golden_cassette)
        candidate.output_text = "Totally different output"
        result = golden_set.compare(candidate)
        # output_must_match defaults to False
        assert result.passed


# ──────────────────────────────────────────────
# GoldenSet comparison — failing
# ──────────────────────────────────────────────

class TestGoldenSetCompareFail:
    def test_fail_on_tool_sequence_change(self, golden_set, golden_cassette):
        candidate = copy.deepcopy(golden_cassette)
        candidate.add_span(Span(
            kind=SpanKind.TOOL_CALL,
            tool_name="unexpected_tool",
        ))
        result = golden_set.compare(candidate)
        assert not result.passed
        failed = [f for f in result.fields if f.name == "tool_sequence"]
        assert len(failed) == 1
        assert not failed[0].passed

    def test_fail_on_excessive_token_increase(self, golden_set, golden_cassette):
        candidate = copy.deepcopy(golden_cassette)
        for s in candidate.spans:
            if s.token_usage:
                s.token_usage = TokenUsage(
                    prompt_tokens=100,
                    completion_tokens=50,
                    total_tokens=150,  # 5x increase
                )
        result = golden_set.compare(candidate)
        assert not result.passed
        failed = [f for f in result.fields if f.name == "token_count"]
        assert len(failed) == 1

    def test_fail_on_excessive_cost_increase(self, golden_set, golden_cassette):
        candidate = copy.deepcopy(golden_cassette)
        for s in candidate.spans:
            if s.cost_usd:
                s.cost_usd = 0.01  # 10x increase
        result = golden_set.compare(candidate)
        assert not result.passed
        failed = [f for f in result.fields if f.name == "cost"]
        assert len(failed) == 1

    def test_fail_on_output_mismatch_when_required(self, golden_set, golden_cassette):
        golden_set.thresholds.output_must_match = True
        candidate = copy.deepcopy(golden_cassette)
        candidate.output_text = "Different output"
        result = golden_set.compare(candidate)
        assert not result.passed

    def test_fail_on_absolute_token_limit(self, golden_cassette):
        gs = GoldenSet(
            name="strict",
            thresholds=Thresholds(
                tool_sequence_must_match=False,
                max_tokens=10,
            ),
        )
        gs.add_cassette(golden_cassette)
        candidate = copy.deepcopy(golden_cassette)
        result = gs.compare(candidate)
        assert not result.passed
        failed = [f for f in result.fields if f.name == "max_tokens"]
        assert len(failed) == 1

    def test_fail_on_absolute_cost_limit(self, golden_cassette):
        gs = GoldenSet(
            name="strict",
            thresholds=Thresholds(
                tool_sequence_must_match=False,
                max_cost_usd=0.0001,
            ),
        )
        gs.add_cassette(golden_cassette)
        candidate = copy.deepcopy(golden_cassette)
        result = gs.compare(candidate)
        assert not result.passed

    def test_fail_on_absolute_latency_limit(self, golden_cassette):
        gs = GoldenSet(
            name="strict",
            thresholds=Thresholds(
                tool_sequence_must_match=False,
                max_latency_ms=1.0,
            ),
        )
        gs.add_cassette(golden_cassette)
        candidate = copy.deepcopy(golden_cassette)
        result = gs.compare(candidate)
        assert not result.passed

    def test_empty_golden_set_fails(self):
        gs = GoldenSet(name="empty")
        candidate = Cassette(name="test")
        result = gs.compare(candidate)
        assert not result.passed
        assert result.fields[0].name == "golden_set_empty"


# ──────────────────────────────────────────────
# GoldenSet comparison — custom thresholds
# ──────────────────────────────────────────────

class TestGoldenSetCustomThresholds:
    def test_custom_thresholds_override_defaults(self, golden_set, golden_cassette):
        candidate = copy.deepcopy(golden_cassette)
        candidate.add_span(Span(
            kind=SpanKind.TOOL_CALL,
            tool_name="new_tool",
        ))
        # Should fail with default thresholds
        result = golden_set.compare(candidate)
        assert not result.passed

        # Pass with relaxed custom thresholds
        relaxed = Thresholds(tool_sequence_must_match=False)
        result = golden_set.compare(candidate, thresholds=relaxed)
        assert result.passed

    def test_strict_thresholds(self, golden_set, golden_cassette):
        candidate = copy.deepcopy(golden_cassette)
        candidate.output_text = "Different"
        strict = Thresholds(
            tool_sequence_must_match=True,
            output_must_match=True,
        )
        result = golden_set.compare(candidate, thresholds=strict)
        assert not result.passed

    def test_skip_ratio_check_when_golden_is_zero(self, golden_cassette):
        """When golden has zero tokens/cost/latency, ratio checks are skipped."""
        zero_cassette = Cassette(name="zero")
        zero_cassette.add_span(Span(
            kind=SpanKind.TOOL_CALL,
            tool_name="get_weather",
        ))

        gs = GoldenSet(name="zero_baseline")
        gs.add_cassette(zero_cassette)

        candidate = copy.deepcopy(zero_cassette)
        result = gs.compare(candidate)
        assert result.passed


# ──────────────────────────────────────────────
# GoldenSet comparison result details
# ──────────────────────────────────────────────

class TestGoldenSetCompareDetails:
    def test_result_has_golden_name_and_version(self, golden_set, golden_cassette):
        result = golden_set.compare(copy.deepcopy(golden_cassette))
        assert result.golden_name == "weather_test"
        assert result.golden_version == 1

    def test_result_fields_have_values(self, golden_set, golden_cassette):
        candidate = copy.deepcopy(golden_cassette)
        candidate.add_span(Span(
            kind=SpanKind.TOOL_CALL,
            tool_name="extra",
        ))
        result = golden_set.compare(candidate)
        tool_field = next(f for f in result.fields if f.name == "tool_sequence")
        assert tool_field.golden_value == ["get_weather"]
        assert "extra" in tool_field.candidate_value

    def test_latency_ratio_comparison(self, golden_cassette):
        gs = GoldenSet(
            name="latency_test",
            thresholds=Thresholds(
                tool_sequence_must_match=False,
                max_latency_increase_ratio=2.0,
            ),
        )
        gs.add_cassette(golden_cassette)

        candidate = copy.deepcopy(golden_cassette)
        # Triple the latency — should fail at 2.0x threshold
        for s in candidate.spans:
            s.duration_ms *= 3
        result = gs.compare(candidate)
        assert not result.passed
        latency_field = next(f for f in result.fields if f.name == "latency")
        assert not latency_field.passed
