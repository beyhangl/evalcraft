"""Tests for evalcraft.capture.recorder."""

import asyncio
import pytest
from pathlib import Path

from evalcraft.capture.recorder import (
    CaptureContext, capture, get_active_context, record_span, record_llm_call, record_tool_call
)
from evalcraft.core.models import Span, SpanKind, TokenUsage


# ──────────────────────────────────────────────
# get_active_context
# ──────────────────────────────────────────────

class TestGetActiveContext:
    def test_no_active_context_returns_none(self):
        assert get_active_context() is None

    def test_returns_context_inside_manager(self):
        with CaptureContext(name="test") as ctx:
            assert get_active_context() is ctx

    def test_context_cleared_after_exit(self):
        with CaptureContext(name="test"):
            pass
        assert get_active_context() is None

    @pytest.mark.asyncio
    async def test_async_context_is_active(self):
        async with CaptureContext(name="async_test") as ctx:
            assert get_active_context() is ctx
        assert get_active_context() is None


# ──────────────────────────────────────────────
# CaptureContext — sync
# ──────────────────────────────────────────────

class TestCaptureContextSync:
    def test_basic_context_manager(self):
        with CaptureContext(name="test", agent_name="my_agent") as ctx:
            assert ctx.cassette.name == "test"
            assert ctx.cassette.agent_name == "my_agent"

    def test_cassette_initialized(self):
        with CaptureContext(name="x", framework="openai") as ctx:
            assert ctx.cassette.framework == "openai"

    def test_record_span(self):
        with CaptureContext() as ctx:
            span = Span(kind=SpanKind.TOOL_CALL, name="tool:search")
            ctx.record_span(span)
        assert len(ctx.cassette.spans) == 1
        assert ctx.cassette.spans[0].kind == SpanKind.TOOL_CALL

    def test_record_llm_call(self):
        with CaptureContext() as ctx:
            ctx.record_llm_call(
                model="gpt-4",
                input="hello",
                output="hi",
                duration_ms=100.0,
                prompt_tokens=5,
                completion_tokens=3,
                cost_usd=0.001,
            )
        assert len(ctx.cassette.spans) == 1
        span = ctx.cassette.spans[0]
        assert span.kind == SpanKind.LLM_RESPONSE
        assert span.model == "gpt-4"
        assert span.token_usage.prompt_tokens == 5
        assert span.token_usage.completion_tokens == 3
        assert span.token_usage.total_tokens == 8
        assert span.cost_usd == 0.001

    def test_record_tool_call(self):
        with CaptureContext() as ctx:
            ctx.record_tool_call(
                tool_name="search",
                args={"q": "test"},
                result={"results": []},
                duration_ms=50.0,
                error=None,
            )
        span = ctx.cassette.spans[0]
        assert span.kind == SpanKind.TOOL_CALL
        assert span.tool_name == "search"
        assert span.tool_args == {"q": "test"}
        assert span.tool_result == {"results": []}

    def test_record_input(self):
        with CaptureContext() as ctx:
            ctx.record_input("What is the weather?")
        assert ctx.cassette.input_text == "What is the weather?"
        assert ctx.cassette.spans[0].kind == SpanKind.USER_INPUT

    def test_record_output(self):
        with CaptureContext() as ctx:
            ctx.record_output("It's sunny.")
        assert ctx.cassette.output_text == "It's sunny."
        assert ctx.cassette.spans[0].kind == SpanKind.AGENT_OUTPUT

    def test_finalize_computes_metrics(self):
        with CaptureContext() as ctx:
            ctx.record_llm_call(
                model="gpt-4",
                input="hi",
                output="hello",
                prompt_tokens=10,
                completion_tokens=5,
            )
        assert ctx.cassette.total_tokens == 15
        assert ctx.cassette.fingerprint != ""

    def test_save_path(self, tmp_path):
        path = tmp_path / "cassette.json"
        with CaptureContext(name="saved", save_path=path) as ctx:
            ctx.record_input("test")
        assert path.exists()

    def test_metadata(self):
        with CaptureContext(metadata={"env": "test", "version": "1"}) as ctx:
            pass
        assert ctx.cassette.metadata == {"env": "test", "version": "1"}


# ──────────────────────────────────────────────
# CaptureContext — async
# ──────────────────────────────────────────────

class TestCaptureContextAsync:
    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        async with CaptureContext(name="async") as ctx:
            span = Span(kind=SpanKind.TOOL_CALL, name="tool:search")
            ctx.record_span(span)
        assert len(ctx.cassette.spans) == 1

    @pytest.mark.asyncio
    async def test_async_record_llm_call(self):
        async with CaptureContext() as ctx:
            ctx.record_llm_call(
                model="claude-3",
                input="prompt",
                output="response",
                prompt_tokens=20,
                completion_tokens=10,
            )
        assert ctx.cassette.total_tokens == 30


# ──────────────────────────────────────────────
# capture decorator
# ──────────────────────────────────────────────

class TestCaptureDecorator:
    def test_sync_decorator(self):
        @capture(name="test_fn", agent_name="my_agent")
        def my_fn():
            ctx = get_active_context()
            ctx.record_input("hello")
            return "done"

        result = my_fn()
        assert result == "done"

    def test_sync_decorator_uses_fn_name_when_no_name(self):
        @capture()
        def my_named_function():
            pass

        my_named_function()

    @pytest.mark.asyncio
    async def test_async_decorator(self):
        @capture(name="async_test")
        async def my_async_fn():
            ctx = get_active_context()
            ctx.record_input("async input")
            return "async done"

        result = await my_async_fn()
        assert result == "async done"

    def test_sync_decorator_preserves_return_value(self):
        @capture()
        def returns_value():
            return {"key": "value"}

        assert returns_value() == {"key": "value"}


# ──────────────────────────────────────────────
# Module-level helpers
# ──────────────────────────────────────────────

class TestModuleLevelHelpers:
    def test_record_span_with_context(self):
        with CaptureContext() as ctx:
            span = Span(kind=SpanKind.TOOL_CALL)
            result = record_span(span)
            assert result is span
        assert len(ctx.cassette.spans) == 1

    def test_record_span_without_context_returns_none(self):
        result = record_span(Span())
        assert result is None

    def test_record_llm_call_with_context(self):
        with CaptureContext() as ctx:
            result = record_llm_call(
                model="gpt-4", input="hi", output="hello", prompt_tokens=5, completion_tokens=3
            )
            assert result is not None
        assert len(ctx.cassette.spans) == 1

    def test_record_llm_call_without_context_returns_none(self):
        result = record_llm_call(model="gpt-4", input="hi", output="hello")
        assert result is None

    def test_record_tool_call_with_context(self):
        with CaptureContext() as ctx:
            result = record_tool_call(tool_name="search", args={"q": "test"})
            assert result is not None
        assert len(ctx.cassette.spans) == 1

    def test_record_tool_call_without_context_returns_none(self):
        result = record_tool_call(tool_name="search")
        assert result is None
