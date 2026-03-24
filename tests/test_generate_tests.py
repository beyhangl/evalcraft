"""Tests for evalcraft.cli.generate_cmd — auto-test generation."""

from __future__ import annotations

import pytest

from evalcraft.cli.generate_cmd import _extract_key_terms, generate_test_code
from evalcraft.core.models import Cassette, Span, SpanKind, TokenUsage


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

@pytest.fixture
def weather_cassette():
    """A realistic weather agent cassette."""
    c = Cassette(name="weather_agent", agent_name="weather_bot", framework="openai")
    c.add_span(Span(
        kind=SpanKind.USER_INPUT,
        name="user_input",
        input="What's the weather in Paris?",
    ))
    c.add_span(Span(
        kind=SpanKind.TOOL_CALL,
        name="tool:get_weather",
        tool_name="get_weather",
        tool_args={"city": "Paris"},
        tool_result={"temp": 18, "condition": "cloudy"},
    ))
    c.add_span(Span(
        kind=SpanKind.LLM_RESPONSE,
        name="llm:gpt-4o",
        model="gpt-4o",
        input="User asked about weather",
        output="It's 18°C and cloudy in Paris.",
        token_usage=TokenUsage(prompt_tokens=120, completion_tokens=15, total_tokens=135),
        cost_usd=0.0008,
        duration_ms=450.0,
    ))
    c.add_span(Span(
        kind=SpanKind.AGENT_OUTPUT,
        name="agent_output",
        output="It's 18°C and cloudy in Paris.",
    ))
    c.input_text = "What's the weather in Paris?"
    c.output_text = "It's 18°C and cloudy in Paris."
    return c


@pytest.fixture
def multi_tool_cassette():
    """A cassette with multiple tools called in sequence."""
    c = Cassette(name="research_agent", agent_name="research_bot")
    for tool in ["web_search", "summarize", "send_email"]:
        c.add_span(Span(
            kind=SpanKind.TOOL_CALL,
            name=f"tool:{tool}",
            tool_name=tool,
            tool_args={"query": "AI testing"},
            tool_result={"status": "ok"},
        ))
    c.add_span(Span(
        kind=SpanKind.LLM_RESPONSE,
        name="llm:gpt-4",
        model="gpt-4",
        token_usage=TokenUsage(prompt_tokens=200, completion_tokens=100, total_tokens=300),
        cost_usd=0.02,
        duration_ms=1200.0,
    ))
    c.output_text = "Research complete. Email sent with summary."
    return c


@pytest.fixture
def minimal_cassette():
    """A cassette with no tools, no cost, no output."""
    return Cassette(name="minimal")


# ──────────────────────────────────────────────
# generate_test_code
# ──────────────────────────────────────────────

class TestGenerateTestCode:
    def test_generates_valid_python(self, weather_cassette):
        code = generate_test_code(weather_cassette, "tests/cassettes/weather.json")
        # Should be valid Python
        compile(code, "<test>", "exec")

    def test_contains_cassette_path(self, weather_cassette):
        code = generate_test_code(weather_cassette, "tests/cassettes/weather.json")
        assert 'CASSETTE_PATH = "tests/cassettes/weather.json"' in code

    def test_generates_tool_call_test(self, weather_cassette):
        code = generate_test_code(weather_cassette, "cassettes/w.json")
        assert "def test_weather_agent_calls_get_weather" in code
        assert 'assert_tool_called(run, "get_weather"' in code

    def test_generates_tool_args_test(self, weather_cassette):
        code = generate_test_code(weather_cassette, "cassettes/w.json")
        assert "def test_weather_agent_get_weather_args" in code
        assert "with_args=" in code
        assert "'city': 'Paris'" in code

    def test_generates_output_test(self, weather_cassette):
        code = generate_test_code(weather_cassette, "cassettes/w.json")
        assert "def test_weather_agent_output_contains_key_term" in code
        assert "assert_output_contains" in code

    def test_generates_output_not_empty_test(self, weather_cassette):
        code = generate_test_code(weather_cassette, "cassettes/w.json")
        assert "def test_weather_agent_output_not_empty" in code
        assert "assert_output_matches" in code

    def test_generates_cost_test(self, weather_cassette):
        code = generate_test_code(weather_cassette, "cassettes/w.json")
        assert "def test_weather_agent_cost_budget" in code
        assert "assert_cost_under" in code

    def test_generates_token_test(self, weather_cassette):
        code = generate_test_code(weather_cassette, "cassettes/w.json")
        assert "def test_weather_agent_token_budget" in code
        assert "assert_token_count_under" in code

    def test_generates_latency_test(self, weather_cassette):
        code = generate_test_code(weather_cassette, "cassettes/w.json")
        assert "def test_weather_agent_latency_budget" in code
        assert "assert_latency_under" in code

    def test_generates_tool_order_test(self, multi_tool_cassette):
        code = generate_test_code(multi_tool_cassette, "cassettes/r.json")
        assert "def test_research_agent_tool_order" in code
        assert "assert_tool_order" in code
        assert "web_search" in code
        assert "summarize" in code
        assert "send_email" in code

    def test_multi_tool_generates_per_tool_tests(self, multi_tool_cassette):
        code = generate_test_code(multi_tool_cassette, "cassettes/r.json")
        assert "def test_research_agent_calls_web_search" in code
        assert "def test_research_agent_calls_summarize" in code
        assert "def test_research_agent_calls_send_email" in code

    def test_minimal_cassette_still_compiles(self, minimal_cassette):
        code = generate_test_code(minimal_cassette, "cassettes/m.json")
        compile(code, "<test>", "exec")
        # Should have the replay helper but no tool/cost tests
        assert "def _replay" in code
        assert "assert_tool_called" not in code
        assert "assert_cost_under" not in code

    def test_cost_budget_is_2x(self, weather_cassette):
        code = generate_test_code(weather_cassette, "cassettes/w.json")
        # Actual cost is 0.0008, budget should be ~0.0016
        assert "max_usd=0.0016" in code

    def test_token_budget_is_2x(self, weather_cassette):
        code = generate_test_code(weather_cassette, "cassettes/w.json")
        # Actual tokens 135, budget should be 270
        assert "max_tokens=270" in code

    def test_header_docstring(self, weather_cassette):
        code = generate_test_code(weather_cassette, "cassettes/w.json")
        assert "Auto-generated tests" in code
        assert "weather_bot" in code  # agent_name
        assert "openai" in code  # framework

    def test_imports_only_needed_modules(self, minimal_cassette):
        code = generate_test_code(minimal_cassette, "cassettes/m.json")
        assert "from evalcraft import replay" in code
        assert "assert_tool_called" not in code

    def test_sanitises_name_with_special_chars(self):
        c = Cassette(name="my-agent.v2 (test)")
        c.output_text = "Output"
        code = generate_test_code(c, "cassettes/test.json")
        # Function names should be valid Python identifiers
        assert "def test_my_agent_v2_test_" in code


# ──────────────────────────────────────────────
# _extract_key_terms
# ──────────────────────────────────────────────

class TestExtractKeyTerms:
    def test_extracts_meaningful_words(self):
        terms = _extract_key_terms("It's 18°C and cloudy in Paris right now.")
        assert len(terms) > 0
        # Should prefer longer, non-stopword terms
        assert "cloudy" in terms or "Paris" in terms

    def test_filters_stopwords(self):
        terms = _extract_key_terms("the quick brown fox jumps over the lazy dog")
        for t in terms:
            assert t.lower() not in {"the", "over"}

    def test_max_terms(self):
        terms = _extract_key_terms("alpha bravo charlie delta echo foxtrot", max_terms=2)
        assert len(terms) == 2

    def test_empty_text(self):
        assert _extract_key_terms("") == []

    def test_deduplicates(self):
        terms = _extract_key_terms("Paris Paris Paris London London")
        assert len([t for t in terms if t == "Paris"]) <= 1
