"""Tests for evalcraft.adapters.anthropic_adapter.

The anthropic package is mocked so these tests run without it installed.
"""

from __future__ import annotations

import sys
from types import ModuleType
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from evalcraft.adapters.anthropic_adapter import (
    AnthropicAdapter,
    _estimate_cost,
    _messages_to_str,
    _response_to_str,
    _get_stop_reason,
)
from evalcraft.capture.recorder import CaptureContext, get_active_context
from evalcraft.core.models import SpanKind


# ---------------------------------------------------------------------------
# Helpers to build mock Anthropic response objects
# ---------------------------------------------------------------------------

def _make_text_block(text: str) -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _make_tool_use_block(name: str, input_data: dict) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.name = name
    block.input = input_data
    return block


def _make_response(
    model: str = "claude-3-5-sonnet-20241022",
    content_text: str = "Hello, world!",
    input_tokens: int = 10,
    output_tokens: int = 5,
    stop_reason: str = "end_turn",
    content_blocks: list | None = None,
) -> MagicMock:
    response = MagicMock()
    response.model = model
    response.stop_reason = stop_reason
    if content_blocks is not None:
        response.content = content_blocks
    else:
        response.content = [_make_text_block(content_text)]
    response.usage = MagicMock()
    response.usage.input_tokens = input_tokens
    response.usage.output_tokens = output_tokens
    return response


# ---------------------------------------------------------------------------
# Fixture: inject a fake anthropic module so imports succeed without the package
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_anthropic_module():
    """Inject a minimal fake anthropic.resources.messages module."""
    # Build minimal fake module tree
    fake_anthropic = ModuleType("anthropic")
    fake_resources = ModuleType("anthropic.resources")
    fake_messages_mod = ModuleType("anthropic.resources.messages")

    class FakeMessages:
        def create(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
            pass

    class FakeAsyncMessages:
        async def create(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
            pass

    fake_messages_mod.Messages = FakeMessages
    fake_messages_mod.AsyncMessages = FakeAsyncMessages

    fake_anthropic.resources = fake_resources
    fake_resources.messages = fake_messages_mod

    # Register in sys.modules so imports find them
    sys.modules.setdefault("anthropic", fake_anthropic)
    sys.modules["anthropic.resources"] = fake_resources
    sys.modules["anthropic.resources.messages"] = fake_messages_mod

    yield fake_messages_mod

    # Clean up
    for key in ("anthropic", "anthropic.resources", "anthropic.resources.messages"):
        sys.modules.pop(key, None)


# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------

class TestEstimateCost:
    def test_known_model(self):
        # claude-3-5-sonnet: $3.00 input, $15.00 output per 1M tokens
        cost = _estimate_cost("claude-3-5-sonnet-20241022", 1_000_000, 1_000_000)
        assert cost == pytest.approx(18.00)

    def test_haiku_model(self):
        cost = _estimate_cost("claude-3-haiku-20240307", 1_000_000, 0)
        assert cost == pytest.approx(0.25)

    def test_unknown_model_returns_none(self):
        assert _estimate_cost("claude-unknown-xyz", 100, 100) is None

    def test_zero_tokens(self):
        cost = _estimate_cost("claude-3-opus-20240229", 0, 0)
        assert cost == pytest.approx(0.0)

    def test_prefix_match(self):
        # "claude-3-5-sonnet-20241022-extra" should match "claude-3-5-sonnet-20241022"
        cost = _estimate_cost("claude-3-5-sonnet-20241022-extra", 0, 1_000_000)
        assert cost == pytest.approx(15.00)


class TestMessagesToStr:
    def test_simple_user_message(self):
        messages = [{"role": "user", "content": "Hello"}]
        assert _messages_to_str(messages) == "user: Hello"

    def test_multi_turn(self):
        messages = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
        ]
        result = _messages_to_str(messages)
        assert "user: Hi" in result
        assert "assistant: Hello!" in result

    def test_list_content_extracts_text(self):
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What is this?"},
                    {"type": "image_url", "url": "http://example.com/img.png"},
                ],
            }
        ]
        result = _messages_to_str(messages)
        assert "What is this?" in result

    def test_empty_messages(self):
        assert _messages_to_str([]) == ""


class TestResponseToStr:
    def test_text_content(self):
        response = _make_response(content_text="Paris is the capital.")
        assert _response_to_str(response) == "Paris is the capital."

    def test_tool_use_block(self):
        blocks = [_make_tool_use_block("search", {"query": "weather"})]
        response = _make_response(content_blocks=blocks)
        result = _response_to_str(response)
        assert "tool_use:search" in result
        assert "weather" in result

    def test_mixed_content(self):
        blocks = [
            _make_text_block("Let me search for that."),
            _make_tool_use_block("search", {"q": "Paris"}),
        ]
        response = _make_response(content_blocks=blocks)
        result = _response_to_str(response)
        assert "Let me search for that." in result
        assert "tool_use:search" in result

    def test_empty_content(self):
        response = _make_response(content_blocks=[])
        assert _response_to_str(response) == ""

    def test_fallback_on_bad_response(self):
        # Should not raise
        result = _response_to_str("not-a-response-object")
        assert isinstance(result, str)


class TestGetStopReason:
    def test_end_turn(self):
        response = _make_response(stop_reason="end_turn")
        assert _get_stop_reason(response) == "end_turn"

    def test_max_tokens(self):
        response = _make_response(stop_reason="max_tokens")
        assert _get_stop_reason(response) == "max_tokens"

    def test_missing_attribute(self):
        obj = MagicMock(spec=[])
        assert _get_stop_reason(obj) == ""


# ---------------------------------------------------------------------------
# AnthropicAdapter — context manager and patching
# ---------------------------------------------------------------------------

class TestAnthropicAdapterPatch:
    def test_patch_and_unpatch(self, mock_anthropic_module):
        Messages = mock_anthropic_module.Messages
        original = Messages.create

        adapter = AnthropicAdapter()
        adapter._patch()
        assert Messages.create is not original

        adapter._unpatch()
        assert Messages.create is original

    def test_context_manager_restores_on_exit(self, mock_anthropic_module):
        Messages = mock_anthropic_module.Messages
        original = Messages.create

        with AnthropicAdapter():
            assert Messages.create is not original
        assert Messages.create is original

    def test_context_manager_restores_on_exception(self, mock_anthropic_module):
        Messages = mock_anthropic_module.Messages
        original = Messages.create

        with pytest.raises(ValueError):
            with AnthropicAdapter():
                raise ValueError("oops")
        assert Messages.create is original

    def test_double_patch_is_noop(self, mock_anthropic_module):
        adapter = AnthropicAdapter()
        adapter._patch()
        patched = mock_anthropic_module.Messages.create
        adapter._patch()  # second call should be a no-op
        assert mock_anthropic_module.Messages.create is patched
        adapter._unpatch()

    @pytest.mark.asyncio
    async def test_async_context_manager(self, mock_anthropic_module):
        Messages = mock_anthropic_module.Messages
        original = Messages.create

        async with AnthropicAdapter():
            assert Messages.create is not original
        assert Messages.create is original

    def test_import_error_raises_helpful_message(self):
        """ImportError from anthropic is converted to a helpful message."""
        adapter = AnthropicAdapter()
        with patch.dict(sys.modules, {"anthropic.resources.messages": None}):  # type: ignore[dict-item]
            with pytest.raises(ImportError, match="evalcraft\\[anthropic\\]"):
                adapter._patch()


# ---------------------------------------------------------------------------
# AnthropicAdapter — recording into CaptureContext
# ---------------------------------------------------------------------------

class TestAnthropicAdapterRecording:
    def _run_patched_call(self, mock_anthropic_module, response: Any, kwargs: dict) -> CaptureContext:
        """Helper: run a patched sync create() inside a CaptureContext."""
        Messages = mock_anthropic_module.Messages
        original = Messages.create
        Messages.create = MagicMock(return_value=response)

        ctx = CaptureContext(name="test")
        adapter = AnthropicAdapter()
        with ctx:
            with adapter:
                # Call the patched method via the class (simulating instance call)
                Messages.create(MagicMock(), **kwargs)

        # Restore
        Messages.create = original
        return ctx

    def test_span_recorded_with_model(self, mock_anthropic_module):
        response = _make_response(model="claude-3-5-sonnet-20241022")
        ctx = self._run_patched_call(
            mock_anthropic_module,
            response,
            {"model": "claude-3-5-sonnet-20241022", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert len(ctx.cassette.spans) == 1
        span = ctx.cassette.spans[0]
        assert span.kind == SpanKind.LLM_RESPONSE
        assert span.model == "claude-3-5-sonnet-20241022"

    def test_token_usage_captured(self, mock_anthropic_module):
        response = _make_response(input_tokens=20, output_tokens=10)
        ctx = self._run_patched_call(
            mock_anthropic_module,
            response,
            {"model": "claude-3-haiku-20240307", "messages": []},
        )
        span = ctx.cassette.spans[0]
        assert span.token_usage.prompt_tokens == 20
        assert span.token_usage.completion_tokens == 10
        assert span.token_usage.total_tokens == 30

    def test_cost_estimated(self, mock_anthropic_module):
        # 1M input + 1M output for haiku = 0.25 + 1.25 = 1.50
        response = _make_response(
            model="claude-3-haiku-20240307",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        )
        ctx = self._run_patched_call(
            mock_anthropic_module,
            response,
            {"model": "claude-3-haiku-20240307", "messages": []},
        )
        span = ctx.cassette.spans[0]
        assert span.cost_usd == pytest.approx(1.50)

    def test_stop_reason_in_metadata(self, mock_anthropic_module):
        response = _make_response(stop_reason="max_tokens")
        ctx = self._run_patched_call(
            mock_anthropic_module,
            response,
            {"model": "claude-3-5-sonnet-20241022", "messages": []},
        )
        span = ctx.cassette.spans[0]
        assert span.metadata.get("stop_reason") == "max_tokens"

    def test_output_text_captured(self, mock_anthropic_module):
        response = _make_response(content_text="The answer is 42.")
        ctx = self._run_patched_call(
            mock_anthropic_module,
            response,
            {"model": "claude-3-5-sonnet-20241022", "messages": []},
        )
        span = ctx.cassette.spans[0]
        assert span.output == "The answer is 42."

    def test_no_span_without_context(self, mock_anthropic_module):
        """No span recorded when there is no active CaptureContext."""
        assert get_active_context() is None
        response = _make_response()

        Messages = mock_anthropic_module.Messages
        original = Messages.create
        Messages.create = MagicMock(return_value=response)

        adapter = AnthropicAdapter()
        with adapter:
            Messages.create(MagicMock(), model="claude-3-5-sonnet-20241022", messages=[])

        Messages.create = original
        # Nothing to assert — just confirm no error raised

    def test_error_recorded_as_span(self, mock_anthropic_module):
        """Exceptions during the API call are recorded as error spans."""
        Messages = mock_anthropic_module.Messages
        original = Messages.create
        Messages.create = MagicMock(side_effect=RuntimeError("API error"))

        ctx = CaptureContext(name="error_test")
        adapter = AnthropicAdapter()
        with ctx:
            with adapter:
                with pytest.raises(RuntimeError):
                    Messages.create(
                        MagicMock(),
                        model="claude-3-5-sonnet-20241022",
                        messages=[{"role": "user", "content": "hi"}],
                    )

        Messages.create = original
        assert len(ctx.cassette.spans) == 1
        span = ctx.cassette.spans[0]
        assert span.error == "API error"
        assert span.model == "claude-3-5-sonnet-20241022"


# ---------------------------------------------------------------------------
# Async recording
# ---------------------------------------------------------------------------

class TestAnthropicAdapterAsyncRecording:
    @pytest.mark.asyncio
    async def test_async_span_recorded(self, mock_anthropic_module):
        response = _make_response(
            model="claude-3-5-sonnet-20241022",
            content_text="Async reply",
            input_tokens=15,
            output_tokens=8,
        )
        AsyncMessages = mock_anthropic_module.AsyncMessages
        original = AsyncMessages.create
        AsyncMessages.create = AsyncMock(return_value=response)

        ctx = CaptureContext(name="async_test")
        async with ctx:
            async with AnthropicAdapter():
                await AsyncMessages.create(
                    MagicMock(),
                    model="claude-3-5-sonnet-20241022",
                    messages=[{"role": "user", "content": "async hi"}],
                )

        AsyncMessages.create = original

        assert len(ctx.cassette.spans) == 1
        span = ctx.cassette.spans[0]
        assert span.model == "claude-3-5-sonnet-20241022"
        assert span.token_usage.prompt_tokens == 15
        assert span.token_usage.completion_tokens == 8

    @pytest.mark.asyncio
    async def test_async_error_recorded(self, mock_anthropic_module):
        AsyncMessages = mock_anthropic_module.AsyncMessages
        original = AsyncMessages.create
        AsyncMessages.create = AsyncMock(side_effect=RuntimeError("async error"))

        ctx = CaptureContext(name="async_error_test")
        async with ctx:
            async with AnthropicAdapter():
                with pytest.raises(RuntimeError):
                    await AsyncMessages.create(
                        MagicMock(),
                        model="claude-3-5-sonnet-20241022",
                        messages=[],
                    )

        AsyncMessages.create = original

        assert len(ctx.cassette.spans) == 1
        assert ctx.cassette.spans[0].error == "async error"
