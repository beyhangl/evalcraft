"""End-to-end pipeline validation — proves the ENTIRE evalcraft pipeline works.

This test does NOT mock internal evalcraft code. It exercises the full path:

  capture → save to disk → load from disk → replay → assertions → diff → golden → regression

Using MockLLM and MockTool to simulate the agent (so no API key needed), but
the evalcraft pipeline itself is tested for real.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evalcraft import (
    CaptureContext,
    MockLLM,
    MockTool,
    replay,
    ReplayEngine,
    Cassette,
    assert_tool_called,
    assert_tool_order,
    assert_no_tool_called,
    assert_output_contains,
    assert_output_matches,
    assert_cost_under,
    assert_latency_under,
    assert_token_count_under,
)
from evalcraft.eval.scorers import Evaluator
from evalcraft.golden.manager import GoldenSet
from evalcraft.regression.detector import RegressionDetector


# ──────────────────────────────────────────────
# Phase 1: Capture a full agent run
# ──────────────────────────────────────────────

class TestE2ECapture:
    """Test that CaptureContext records a complete agent run to disk."""

    def test_capture_full_agent_run(self, tmp_path):
        cassette_path = tmp_path / "weather_agent.json"

        # Capture a full agent run using manual recording
        # (MockLLM/MockTool auto-record when a CaptureContext is active,
        # so we use manual record_* calls to avoid double-recording)
        with CaptureContext(
            name="weather_agent_run",
            agent_name="weather_bot",
            framework="openai",
            save_path=str(cassette_path),
        ) as ctx:
            ctx.record_input("What's the weather in Paris?")

            ctx.record_tool_call(
                tool_name="get_weather",
                args={"city": "Paris"},
                result={"temp": 18, "condition": "cloudy", "city": "Paris"},
                duration_ms=45.0,
            )

            ctx.record_llm_call(
                model="gpt-4o-mini",
                input="What's the weather in Paris?",
                output="It's 18°C and cloudy in Paris right now.",
                prompt_tokens=120,
                completion_tokens=15,
                cost_usd=0.0001,
                duration_ms=320.0,
            )

            ctx.record_output("It's 18°C and cloudy in Paris right now.")

        # Verify file was saved
        assert cassette_path.exists()

        # Verify JSON is valid and contains expected data
        data = json.loads(cassette_path.read_text())
        assert data.get("evalcraft_version") == "0.1.0"
        assert data["cassette"]["name"] == "weather_agent_run"
        assert data["cassette"]["agent_name"] == "weather_bot"
        assert data["cassette"]["framework"] == "openai"
        assert len(data["spans"]) == 4  # input, tool, llm, output
        assert data["cassette"]["fingerprint"]  # Non-empty fingerprint

        # Verify metrics were computed
        assert data["cassette"]["total_tokens"] > 0
        assert data["cassette"]["total_cost_usd"] > 0
        assert data["cassette"]["tool_call_count"] == 1
        assert data["cassette"]["llm_call_count"] == 1


# ──────────────────────────────────────────────
# Phase 2: Load and replay
# ──────────────────────────────────────────────

class TestE2EReplay:
    """Test that a saved cassette can be loaded and replayed."""

    @pytest.fixture
    def saved_cassette(self, tmp_path):
        path = tmp_path / "replay_test.json"
        # Use manual recording only (no MockLLM/MockTool to avoid auto-recording)
        with CaptureContext(
            name="replay_test",
            agent_name="weather_bot",
            save_path=str(path),
        ) as ctx:
            ctx.record_input("Weather in Paris?")
            ctx.record_tool_call(tool_name="get_weather", args={"city": "Paris"}, result={"temp": 18})
            ctx.record_llm_call(model="gpt-4o-mini", input="test", output="Paris is 18°C and cloudy.",
                                prompt_tokens=50, completion_tokens=10, cost_usd=0.00005)
            ctx.record_output("Paris is 18°C and cloudy.")
        return path

    def test_load_cassette_from_disk(self, saved_cassette):
        c = Cassette.load(saved_cassette)
        assert c.name == "replay_test"
        assert c.output_text == "Paris is 18°C and cloudy."
        assert len(c.spans) == 4

    def test_replay_returns_agent_run(self, saved_cassette):
        run = replay(str(saved_cassette))
        assert run.replayed is True
        assert run.cassette.output_text == "Paris is 18°C and cloudy."

    def test_replay_preserves_spans(self, saved_cassette):
        run = replay(str(saved_cassette))
        tool_calls = run.cassette.get_tool_calls()
        assert len(tool_calls) == 1
        assert tool_calls[0].tool_name == "get_weather"
        assert tool_calls[0].tool_args == {"city": "Paris"}


# ──────────────────────────────────────────────
# Phase 3: All assertions work on replayed run
# ──────────────────────────────────────────────

class TestE2EAssertions:
    """Test that ALL scorer types work on a replayed cassette."""

    @pytest.fixture
    def run(self, tmp_path):
        path = tmp_path / "assertions_test.json"
        with CaptureContext(name="assertions_test", save_path=str(path)) as ctx:
            ctx.record_input("Weather?")
            ctx.record_tool_call(tool_name="search", args={"q": "weather"}, result="sunny", duration_ms=10)
            ctx.record_tool_call(tool_name="format", args={"style": "brief"}, result="It's sunny", duration_ms=5)
            ctx.record_llm_call(model="gpt-4o", input="test", output="It's sunny in NYC",
                                prompt_tokens=100, completion_tokens=20, cost_usd=0.002, duration_ms=500)
            ctx.record_output("It's sunny in NYC")
        return replay(str(path))

    def test_assert_tool_called(self, run):
        assert assert_tool_called(run, "search").passed
        assert assert_tool_called(run, "search", times=1).passed
        assert assert_tool_called(run, "search", with_args={"q": "weather"}).passed
        assert not assert_tool_called(run, "nonexistent").passed

    def test_assert_tool_order(self, run):
        assert assert_tool_order(run, ["search", "format"]).passed
        assert assert_tool_order(run, ["search", "format"], strict=True).passed
        assert not assert_tool_order(run, ["format", "search"], strict=True).passed

    def test_assert_no_tool_called(self, run):
        assert assert_no_tool_called(run, "delete").passed
        assert not assert_no_tool_called(run, "search").passed

    def test_assert_output_contains(self, run):
        assert assert_output_contains(run, "sunny").passed
        assert assert_output_contains(run, "NYC").passed
        assert not assert_output_contains(run, "rainy").passed

    def test_assert_output_matches(self, run):
        assert assert_output_matches(run, r"sunny.*NYC").passed
        assert not assert_output_matches(run, r"^\d+$").passed

    def test_assert_cost_under(self, run):
        assert assert_cost_under(run, max_usd=0.01).passed
        assert not assert_cost_under(run, max_usd=0.001).passed

    def test_assert_token_count_under(self, run):
        assert assert_token_count_under(run, max_tokens=500).passed
        assert not assert_token_count_under(run, max_tokens=10).passed

    def test_assert_latency_under(self, run):
        assert assert_latency_under(run, max_ms=10000).passed

    def test_evaluator_composite(self, run):
        evaluator = Evaluator()
        evaluator.add(assert_tool_called, run, "search")
        evaluator.add(assert_output_contains, run, "sunny")
        evaluator.add(assert_cost_under, run, max_usd=0.01)
        result = evaluator.run()
        assert result.passed
        assert result.score == 1.0
        assert len(result.assertions) == 3


# ──────────────────────────────────────────────
# Phase 4: Diff two cassettes
# ──────────────────────────────────────────────

class TestE2EDiff:
    """Test that diffing two cassettes detects real changes."""

    def _make_cassette(self, tmp_path, name, output, tools, cost):
        path = tmp_path / f"{name}.json"
        with CaptureContext(name=name, save_path=str(path)) as ctx:
            ctx.record_input("Test input")
            for tool in tools:
                ctx.record_tool_call(tool_name=tool, args={}, result="ok")
            ctx.record_llm_call(model="gpt-4o", input="test", output=output,
                                prompt_tokens=100, completion_tokens=20, cost_usd=cost)
            ctx.record_output(output)
        return path

    def test_identical_cassettes_no_diff(self, tmp_path):
        p1 = self._make_cassette(tmp_path, "v1", "Hello", ["search"], 0.001)
        p2 = self._make_cassette(tmp_path, "v2", "Hello", ["search"], 0.001)
        c1 = Cassette.load(p1)
        c2 = Cassette.load(p2)

        from evalcraft.replay.engine import ReplayDiff
        diff = ReplayDiff.compute(c1, c2)
        assert not diff.tool_sequence_changed
        assert not diff.output_changed

    def test_detects_tool_sequence_change(self, tmp_path):
        p1 = self._make_cassette(tmp_path, "v1", "Hello", ["search"], 0.001)
        p2 = self._make_cassette(tmp_path, "v2", "Hello", ["search", "notify"], 0.001)
        c1 = Cassette.load(p1)
        c2 = Cassette.load(p2)

        from evalcraft.replay.engine import ReplayDiff
        diff = ReplayDiff.compute(c1, c2)
        assert diff.tool_sequence_changed

    def test_detects_output_change(self, tmp_path):
        p1 = self._make_cassette(tmp_path, "v1", "Hello", ["search"], 0.001)
        p2 = self._make_cassette(tmp_path, "v2", "Goodbye", ["search"], 0.001)
        c1 = Cassette.load(p1)
        c2 = Cassette.load(p2)

        from evalcraft.replay.engine import ReplayDiff
        diff = ReplayDiff.compute(c1, c2)
        assert diff.output_changed


# ──────────────────────────────────────────────
# Phase 5: Golden sets and regression detection
# ──────────────────────────────────────────────

class TestE2EGoldenRegression:
    """Test golden set creation and regression detection end-to-end."""

    @pytest.fixture
    def baseline_cassette(self, tmp_path):
        path = tmp_path / "baseline.json"
        with CaptureContext(name="baseline", agent_name="bot", save_path=str(path)) as ctx:
            ctx.record_input("Hello")
            ctx.record_tool_call(tool_name="greet", args={"name": "User"}, result="Hi User!")
            ctx.record_llm_call(model="gpt-4o-mini", input="Hello", output="Hi there!",
                                prompt_tokens=50, completion_tokens=10, cost_usd=0.0001)
            ctx.record_output("Hi there!")
        return path

    def test_golden_set_create_and_compare(self, baseline_cassette, tmp_path):
        golden_path = tmp_path / "golden.json"
        c = Cassette.load(baseline_cassette)

        # Create golden set
        gs = GoldenSet(name="greet_agent", description="Greeting agent baseline")
        gs.add_cassette(c)
        gs.save(golden_path)

        # Verify golden set was saved
        assert golden_path.exists()
        loaded_gs = GoldenSet.load(golden_path)
        assert loaded_gs.name == "greet_agent"
        assert loaded_gs.cassette_count == 1

    def test_regression_detector_no_regression(self, baseline_cassette, tmp_path):
        baseline = Cassette.load(baseline_cassette)

        # Create identical "new" cassette
        new_path = tmp_path / "new_run.json"
        with CaptureContext(name="new_run", agent_name="bot", save_path=str(new_path)) as ctx:
            ctx.record_input("Hello")
            ctx.record_tool_call(tool_name="greet", args={"name": "User"}, result="Hi User!")
            ctx.record_llm_call(model="gpt-4o-mini", input="Hello", output="Hi there!",
                                prompt_tokens=50, completion_tokens=10, cost_usd=0.0001)
            ctx.record_output("Hi there!")

        new = Cassette.load(new_path)
        detector = RegressionDetector()
        report = detector.compare(baseline, new)
        assert not report.has_critical

    def test_regression_detector_catches_cost_spike(self, baseline_cassette, tmp_path):
        baseline = Cassette.load(baseline_cassette)

        # Create "new" cassette with 10x cost
        new_path = tmp_path / "expensive.json"
        with CaptureContext(name="expensive", agent_name="bot", save_path=str(new_path)) as ctx:
            ctx.record_input("Hello")
            ctx.record_tool_call(tool_name="greet", args={"name": "User"}, result="Hi User!")
            ctx.record_llm_call(model="gpt-4o-mini", input="Hello", output="Hi there!",
                                prompt_tokens=500, completion_tokens=100, cost_usd=0.01)
            ctx.record_output("Hi there!")

        new = Cassette.load(new_path)
        detector = RegressionDetector()
        report = detector.compare(baseline, new)
        assert report.has_regressions


# ──────────────────────────────────────────────
# Phase 6: Auto-test generation end-to-end
# ──────────────────────────────────────────────

class TestE2EAutoGenerate:
    """Test that auto-generated test code is valid and runnable."""

    def test_generated_code_compiles(self, tmp_path):
        from evalcraft.cli.generate_cmd import generate_test_code

        path = tmp_path / "source.json"
        with CaptureContext(name="gen_test", agent_name="bot", save_path=str(path)) as ctx:
            ctx.record_input("Hello")
            ctx.record_tool_call(tool_name="search", args={"q": "hello"}, result="found")
            ctx.record_llm_call(model="gpt-4o", input="test", output="World",
                                prompt_tokens=50, completion_tokens=10, cost_usd=0.001, duration_ms=200)
            ctx.record_output("World")

        c = Cassette.load(path)
        code = generate_test_code(c, str(path))

        # Must be valid Python
        compile(code, "<generated>", "exec")

        # Must contain real test functions
        assert "def test_gen_test_calls_search" in code
        assert "def test_gen_test_cost_budget" in code
        assert "def test_gen_test_output_not_empty" in code


# ──────────────────────────────────────────────
# Phase 7: Full round-trip (capture → save → load → replay → assert → golden → regression)
# ──────────────────────────────────────────────

class TestE2EFullRoundTrip:
    """The ultimate integration test — proves the entire evalcraft pipeline works."""

    def test_full_pipeline(self, tmp_path):
        cassette_path = tmp_path / "cassettes" / "support_agent.json"
        golden_path = tmp_path / "golden" / "support.golden.json"

        # ── Step 1: Capture ──────────────────────────────────────────────
        with CaptureContext(
            name="support_agent",
            agent_name="shopeasy_bot",
            framework="openai",
            save_path=str(cassette_path),
        ) as ctx:
            ctx.record_input("Where is my order ORD-1042?")

            ctx.record_tool_call(
                tool_name="lookup_order",
                args={"order_id": "ORD-1042"},
                result={"status": "shipped", "tracking": "1Z999AA1"},
                duration_ms=23.0,
            )
            ctx.record_tool_call(
                tool_name="search_knowledge_base",
                args={"query": "order tracking"},
                result=[{"title": "How to track your order"}],
                duration_ms=15.0,
            )
            ctx.record_llm_call(
                model="gpt-4o-mini",
                input="Where is my order ORD-1042?",
                output="Your order ORD-1042 has shipped! Track it with 1Z999AA1.",
                prompt_tokens=200,
                completion_tokens=30,
                cost_usd=0.00005,
                duration_ms=450.0,
            )
            ctx.record_output("Your order ORD-1042 has shipped! Track it with 1Z999AA1.")

        # ── Step 2: Verify file on disk ──────────────────────────────────
        assert cassette_path.exists()
        raw = json.loads(cassette_path.read_text())
        assert raw["cassette"]["name"] == "support_agent"
        assert len(raw["spans"]) == 5

        # ── Step 3: Load and replay ──────────────────────────────────────
        run = replay(str(cassette_path))
        assert run.replayed is True
        assert run.cassette.name == "support_agent"

        # ── Step 4: Run ALL assertion types ──────────────────────────────
        assert assert_tool_called(run, "lookup_order").passed
        assert assert_tool_called(run, "lookup_order", with_args={"order_id": "ORD-1042"}).passed
        assert assert_tool_called(run, "search_knowledge_base").passed
        assert assert_tool_order(run, ["lookup_order", "search_knowledge_base"]).passed
        assert assert_no_tool_called(run, "delete_account").passed
        assert assert_output_contains(run, "ORD-1042").passed
        assert assert_output_contains(run, "1Z999AA1").passed
        assert assert_output_matches(run, r"shipped").passed
        assert assert_cost_under(run, max_usd=0.01).passed
        assert assert_token_count_under(run, max_tokens=1000).passed

        # ── Step 5: Composite evaluator ──────────────────────────────────
        evaluator = Evaluator()
        evaluator.add(assert_tool_called, run, "lookup_order")
        evaluator.add(assert_tool_called, run, "search_knowledge_base")
        evaluator.add(assert_output_contains, run, "shipped")
        evaluator.add(assert_cost_under, run, max_usd=0.01)
        result = evaluator.run()
        assert result.passed
        assert result.score == 1.0

        # ── Step 6: Create golden set ────────────────────────────────────
        gs = GoldenSet(name="support_agent_golden")
        gs.add_cassette(run.cassette)
        gs.save(golden_path)
        assert golden_path.exists()

        # ── Step 7: Regression detection (no regression) ─────────────────
        loaded = Cassette.load(cassette_path)
        detector = RegressionDetector()
        report = detector.compare(run.cassette, loaded)
        assert not report.has_critical

        # ── Step 8: Verify fingerprint consistency ───────────────────────
        c1 = Cassette.load(cassette_path)
        c2 = Cassette.load(cassette_path)
        c1.compute_fingerprint()
        c2.compute_fingerprint()
        assert c1.fingerprint == c2.fingerprint
