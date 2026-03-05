"""Shared fixtures for evalcraft tests."""

import pytest
from evalcraft.core.models import (
    Cassette, Span, SpanKind, TokenUsage, AgentRun, EvalResult, AssertionResult
)


@pytest.fixture
def simple_cassette():
    """A cassette with a simple tool call and LLM response."""
    c = Cassette(name="test_cassette", agent_name="test_agent", framework="test")
    c.add_span(Span(
        kind=SpanKind.USER_INPUT,
        name="user_input",
        input="What is the weather?",
    ))
    c.add_span(Span(
        kind=SpanKind.TOOL_CALL,
        name="tool:get_weather",
        tool_name="get_weather",
        tool_args={"city": "NYC"},
        tool_result={"temp": 72, "condition": "sunny"},
    ))
    c.add_span(Span(
        kind=SpanKind.LLM_RESPONSE,
        name="llm:gpt-4",
        model="gpt-4",
        input="What is the weather?",
        output="It is 72°F and sunny in NYC.",
        token_usage=TokenUsage(prompt_tokens=20, completion_tokens=10, total_tokens=30),
        cost_usd=0.001,
    ))
    c.add_span(Span(
        kind=SpanKind.AGENT_OUTPUT,
        name="agent_output",
        output="It is 72°F and sunny in NYC.",
    ))
    c.input_text = "What is the weather?"
    c.output_text = "It is 72°F and sunny in NYC."
    return c


@pytest.fixture
def multi_tool_cassette():
    """A cassette with multiple tool calls in sequence."""
    c = Cassette(name="multi_tool", agent_name="research_agent")
    tools = ["web_search", "summarize", "send_email"]
    for tool in tools:
        c.add_span(Span(
            kind=SpanKind.TOOL_CALL,
            name=f"tool:{tool}",
            tool_name=tool,
            tool_args={"query": "test"},
            tool_result={"status": "ok"},
        ))
    c.output_text = "Done"
    c.add_span(Span(
        kind=SpanKind.LLM_RESPONSE,
        name="llm:gpt-4",
        model="gpt-4",
        token_usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        cost_usd=0.01,
        duration_ms=500.0,
    ))
    c.compute_metrics()
    return c
