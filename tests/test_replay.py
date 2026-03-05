"""Tests for evalcraft.replay.engine."""

import json
import pytest
from pathlib import Path

from evalcraft.core.models import Cassette, Span, SpanKind, TokenUsage, AgentRun
from evalcraft.replay.engine import ReplayEngine, ReplayDiff, replay


@pytest.fixture
def cassette_with_tools(simple_cassette):
    """Cassette that has tool calls to replay."""
    return simple_cassette


@pytest.fixture
def cassette_file(simple_cassette, tmp_path):
    """Save a cassette to a file and return the path."""
    path = tmp_path / "test.json"
    simple_cassette.save(path)
    return path, simple_cassette


# ──────────────────────────────────────────────
# ReplayEngine construction
# ──────────────────────────────────────────────

class TestReplayEngineConstruction:
    def test_from_cassette_object(self, simple_cassette):
        engine = ReplayEngine(simple_cassette)
        assert len(engine.cassette.spans) == len(simple_cassette.spans)

    def test_from_path_string(self, cassette_file):
        path, original = cassette_file
        engine = ReplayEngine(str(path))
        assert engine.cassette.name == original.name

    def test_from_path_object(self, cassette_file):
        path, original = cassette_file
        engine = ReplayEngine(path)
        assert engine.cassette.name == original.name

    def test_cassette_is_deep_copied(self, simple_cassette):
        engine = ReplayEngine(simple_cassette)
        simple_cassette.name = "modified"
        assert engine.cassette.name != "modified"


# ──────────────────────────────────────────────
# Overrides
# ──────────────────────────────────────────────

class TestReplayEngineOverrides:
    def test_override_tool_result(self, simple_cassette):
        engine = ReplayEngine(simple_cassette)
        engine.override_tool_result("get_weather", {"temp": 0, "condition": "snowy"})
        run = engine.run()
        tool_spans = [s for s in run.cassette.spans if s.kind == SpanKind.TOOL_CALL]
        assert tool_spans[0].tool_result == {"temp": 0, "condition": "snowy"}

    def test_override_tool_result_returns_self(self, simple_cassette):
        engine = ReplayEngine(simple_cassette)
        result = engine.override_tool_result("get_weather", {})
        assert result is engine

    def test_override_llm_response(self, simple_cassette):
        engine = ReplayEngine(simple_cassette)
        engine.override_llm_response(0, "Custom response from override")
        run = engine.run()
        llm_spans = [s for s in run.cassette.spans if s.kind == SpanKind.LLM_RESPONSE]
        assert llm_spans[0].output == "Custom response from override"

    def test_override_llm_response_returns_self(self, simple_cassette):
        engine = ReplayEngine(simple_cassette)
        result = engine.override_llm_response(0, "response")
        assert result is engine

    def test_unmatched_tool_override_is_ignored(self, simple_cassette):
        engine = ReplayEngine(simple_cassette)
        engine.override_tool_result("nonexistent_tool", {"data": "x"})
        run = engine.run()
        tool_spans = [s for s in run.cassette.spans if s.kind == SpanKind.TOOL_CALL]
        # Original tool result preserved
        assert tool_spans[0].tool_result == {"temp": 72, "condition": "sunny"}


# ──────────────────────────────────────────────
# Filter spans
# ──────────────────────────────────────────────

class TestFilterSpans:
    def test_filter_spans(self, simple_cassette):
        engine = ReplayEngine(simple_cassette)
        engine.filter_spans(lambda s: s.kind == SpanKind.TOOL_CALL)
        assert all(s.kind == SpanKind.TOOL_CALL for s in engine.spans)

    def test_filter_returns_self(self, simple_cassette):
        engine = ReplayEngine(simple_cassette)
        result = engine.filter_spans(lambda s: True)
        assert result is engine

    def test_no_filter_returns_all_spans(self, simple_cassette):
        engine = ReplayEngine(simple_cassette)
        assert len(engine.spans) == len(simple_cassette.spans)


# ──────────────────────────────────────────────
# run()
# ──────────────────────────────────────────────

class TestReplayEngineRun:
    def test_run_returns_agent_run(self, simple_cassette):
        engine = ReplayEngine(simple_cassette)
        run = engine.run()
        assert isinstance(run, AgentRun)
        assert run.success is True
        assert run.replayed is True

    def test_run_preserves_span_count(self, simple_cassette):
        engine = ReplayEngine(simple_cassette)
        run = engine.run()
        assert len(run.cassette.spans) == len(simple_cassette.spans)

    def test_run_does_not_mutate_original(self, simple_cassette):
        original_name = simple_cassette.name
        engine = ReplayEngine(simple_cassette)
        engine.run()
        assert simple_cassette.name == original_name


# ──────────────────────────────────────────────
# step() and reset()
# ──────────────────────────────────────────────

class TestStepAndReset:
    def test_step_returns_spans_in_order(self, simple_cassette):
        engine = ReplayEngine(simple_cassette)
        steps = []
        while (span := engine.step()) is not None:
            steps.append(span)
        assert len(steps) == len(simple_cassette.spans)

    def test_step_returns_none_when_done(self, simple_cassette):
        engine = ReplayEngine(simple_cassette)
        for _ in simple_cassette.spans:
            engine.step()
        assert engine.step() is None

    def test_reset_allows_restart(self, simple_cassette):
        engine = ReplayEngine(simple_cassette)
        first = engine.step()
        engine.reset()
        second = engine.step()
        assert first.id == second.id

    def test_step_applies_tool_override(self, simple_cassette):
        engine = ReplayEngine(simple_cassette)
        engine.override_tool_result("get_weather", {"temp": -10})
        tool_span = None
        while (span := engine.step()) is not None:
            if span.kind == SpanKind.TOOL_CALL:
                tool_span = span
        assert tool_span is not None
        assert tool_span.tool_result == {"temp": -10}


# ──────────────────────────────────────────────
# Accessors
# ──────────────────────────────────────────────

class TestReplayEngineAccessors:
    def test_get_tool_calls(self, simple_cassette):
        engine = ReplayEngine(simple_cassette)
        calls = engine.get_tool_calls()
        assert all(s.kind == SpanKind.TOOL_CALL for s in calls)
        assert len(calls) == 1

    def test_get_llm_calls(self, simple_cassette):
        engine = ReplayEngine(simple_cassette)
        calls = engine.get_llm_calls()
        assert all(s.kind in (SpanKind.LLM_REQUEST, SpanKind.LLM_RESPONSE) for s in calls)

    def test_get_tool_sequence(self, multi_tool_cassette):
        engine = ReplayEngine(multi_tool_cassette)
        seq = engine.get_tool_sequence()
        assert seq == ["web_search", "summarize", "send_email"]


# ──────────────────────────────────────────────
# diff()
# ──────────────────────────────────────────────

class TestReplayDiff:
    def test_no_changes_identical_cassette(self, simple_cassette):
        import copy
        clone = copy.deepcopy(simple_cassette)
        diff = ReplayDiff.compute(simple_cassette, clone)
        assert not diff.has_changes

    def test_detects_output_change(self, simple_cassette):
        import copy
        modified = copy.deepcopy(simple_cassette)
        modified.output_text = "Different output"
        diff = ReplayDiff.compute(simple_cassette, modified)
        assert diff.output_changed
        assert diff.has_changes

    def test_detects_tool_sequence_change(self, simple_cassette):
        import copy
        modified = copy.deepcopy(simple_cassette)
        modified.add_span(Span(
            kind=SpanKind.TOOL_CALL, name="tool:extra",
            tool_name="extra_tool",
        ))
        diff = ReplayDiff.compute(simple_cassette, modified)
        assert diff.tool_sequence_changed
        assert diff.span_count_changed

    def test_detects_token_count_change(self):
        c1 = Cassette()
        c1.add_span(Span(
            kind=SpanKind.LLM_RESPONSE,
            token_usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        ))
        c1.compute_metrics()
        c2 = Cassette()
        c2.add_span(Span(
            kind=SpanKind.LLM_RESPONSE,
            token_usage=TokenUsage(prompt_tokens=20, completion_tokens=10, total_tokens=30),
        ))
        c2.compute_metrics()
        diff = ReplayDiff.compute(c1, c2)
        assert diff.token_count_changed

    def test_summary_no_changes(self):
        c = Cassette()
        diff = ReplayDiff.compute(c, c)
        assert "No changes" in diff.summary()

    def test_summary_with_changes(self, simple_cassette):
        import copy
        modified = copy.deepcopy(simple_cassette)
        modified.output_text = "Changed!"
        diff = ReplayDiff.compute(simple_cassette, modified)
        summary = diff.summary()
        assert "Output" in summary

    def test_to_dict(self, simple_cassette):
        import copy
        diff = ReplayDiff.compute(simple_cassette, copy.deepcopy(simple_cassette))
        d = diff.to_dict()
        assert "has_changes" in d
        assert "tool_sequence_changed" in d
        assert "output_changed" in d

    def test_diff_from_engine(self, simple_cassette, tmp_path):
        import copy
        path = tmp_path / "other.json"
        other = copy.deepcopy(simple_cassette)
        other.save(path)
        engine = ReplayEngine(simple_cassette)
        diff = engine.diff(path)
        assert isinstance(diff, ReplayDiff)


# ──────────────────────────────────────────────
# replay() convenience function
# ──────────────────────────────────────────────

class TestReplayConvenienceFn:
    def test_replay_from_file(self, cassette_file):
        path, original = cassette_file
        run = replay(path)
        assert isinstance(run, AgentRun)
        assert run.replayed is True

    def test_replay_with_tool_overrides(self, cassette_file):
        path, _ = cassette_file
        run = replay(path, tool_overrides={"get_weather": {"temp": 0}})
        tool_spans = [s for s in run.cassette.spans if s.kind == SpanKind.TOOL_CALL]
        assert tool_spans[0].tool_result == {"temp": 0}

    def test_replay_without_overrides(self, cassette_file):
        path, _ = cassette_file
        run = replay(path)
        assert run.success is True
