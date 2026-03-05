"""Anthropic SDK adapter — auto-captures LLM calls into evalcraft spans.

Monkey-patches ``anthropic.resources.messages.Messages`` so every call to
``client.messages.create()`` (sync or async) is automatically recorded into
the active :class:`~evalcraft.capture.recorder.CaptureContext`.

Usage::

    from evalcraft.adapters import AnthropicAdapter
    from evalcraft import CaptureContext
    import anthropic

    client = anthropic.Anthropic()

    with CaptureContext(name="weather_test") as ctx:
        with AnthropicAdapter():
            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1024,
                messages=[{"role": "user", "content": "What's the weather?"}],
            )

    cassette = ctx.cassette
    print(cassette.total_tokens, cassette.total_cost_usd)

The adapter works with any Anthropic client instance because it patches the
class-level method rather than a specific client instance.

Thread / async safety: the adapter is NOT reentrant — don't nest two
``AnthropicAdapter`` context managers.  It restores the original methods on
exit even if an exception is raised.
"""

from __future__ import annotations

import time
from typing import Any

from evalcraft.capture.recorder import get_active_context
from evalcraft.core.models import Span, SpanKind, TokenUsage


# ---------------------------------------------------------------------------
# Pricing table — approximate cost per 1 M tokens (input_usd, output_usd).
# Prices reflect Anthropic's public rates as of early 2026; update as needed.
# ---------------------------------------------------------------------------
_MODEL_PRICING: dict[str, tuple[float, float]] = {
    # Claude 4.x
    "claude-opus-4-6": (15.00, 75.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5-20251001": (0.80, 4.00),
    # Claude 3.5
    "claude-3-5-sonnet-20241022": (3.00, 15.00),
    "claude-3-5-sonnet-20240620": (3.00, 15.00),
    "claude-3-5-haiku-20241022": (0.80, 4.00),
    # Claude 3
    "claude-3-opus-20240229": (15.00, 75.00),
    "claude-3-sonnet-20240229": (3.00, 15.00),
    "claude-3-haiku-20240307": (0.25, 1.25),
    # Claude 2
    "claude-2.1": (8.00, 24.00),
    "claude-2.0": (8.00, 24.00),
    # Claude Instant
    "claude-instant-1.2": (0.80, 2.40),
}

_UNKNOWN_MODEL = "unknown"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """Return an estimated USD cost or *None* if the model is not in the table."""
    pricing = _MODEL_PRICING.get(model)
    if pricing is None:
        # Prefix-match for dated model variants not listed explicitly.
        for key, prices in _MODEL_PRICING.items():
            if model.startswith(key):
                pricing = prices
                break
    if pricing is None:
        return None
    input_usd, output_usd = pricing
    return (input_tokens * input_usd + output_tokens * output_usd) / 1_000_000


def _messages_to_str(messages: list[dict[str, Any]]) -> str:
    """Flatten an Anthropic ``messages`` list into a single readable string."""
    parts: list[str] = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if isinstance(content, list):
            # Multi-modal content blocks — extract text parts only.
            text_parts = [
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in content
                if not isinstance(block, dict) or block.get("type") == "text"
            ]
            content = " ".join(text_parts)
        parts.append(f"{role}: {content}")
    return "\n".join(parts)


def _response_to_str(response: Any) -> str:
    """Extract assistant text (and any tool-use summaries) from a Message response."""
    try:
        content_blocks = response.content
        if not content_blocks:
            return ""
        parts: list[str] = []
        for block in content_blocks:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                parts.append(getattr(block, "text", ""))
            elif block_type == "tool_use":
                name = getattr(block, "name", "")
                tool_input = getattr(block, "input", {})
                parts.append(f"[tool_use:{name}({tool_input})]")
        return " ".join(parts).strip()
    except (AttributeError, TypeError):
        return str(response)


def _get_stop_reason(response: Any) -> str:
    try:
        return getattr(response, "stop_reason", "") or ""
    except AttributeError:
        return ""


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class AnthropicAdapter:
    """Patches the Anthropic SDK to auto-record every messages.create() call.

    Works as both a **sync** and **async** context manager.  Patches the
    ``Messages`` and ``AsyncMessages`` classes so *all* client instances
    are captured.

    .. code-block:: python

        with AnthropicAdapter():
            response = client.messages.create(...)

        async with AnthropicAdapter():
            response = await client.messages.create(...)

    Spans are silently dropped when no :class:`CaptureContext` is active —
    so the adapter is safe to leave in place during non-test code paths.

    Raises:
        ImportError: if ``anthropic`` is not installed.
    """

    def __init__(self) -> None:
        self._Messages: Any = None
        self._AsyncMessages: Any = None
        self._original_sync_create: Any = None
        self._original_async_create: Any = None
        self._patched: bool = False

    # -- context manager protocol ------------------------------------------

    def __enter__(self) -> "AnthropicAdapter":
        self._patch()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._unpatch()

    async def __aenter__(self) -> "AnthropicAdapter":
        self._patch()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._unpatch()

    # -- patching -----------------------------------------------------------

    def _patch(self) -> None:
        if self._patched:
            return
        try:
            from anthropic.resources.messages import (  # type: ignore[import]
                AsyncMessages,
                Messages,
            )
        except ImportError as exc:
            raise ImportError(
                "The 'anthropic' package is required for AnthropicAdapter. "
                "Install it with: pip install 'evalcraft[anthropic]'"
            ) from exc

        self._Messages = Messages
        self._AsyncMessages = AsyncMessages
        self._original_sync_create = Messages.create
        self._original_async_create = AsyncMessages.create

        adapter = self
        original_sync = self._original_sync_create
        original_async = self._original_async_create

        def patched_sync_create(self_messages: Any, *args: Any, **kwargs: Any) -> Any:
            start = time.monotonic()
            try:
                response = original_sync(self_messages, *args, **kwargs)
            except Exception as exc:
                duration_ms = (time.monotonic() - start) * 1000
                adapter._record_error(kwargs, duration_ms, str(exc))
                raise
            duration_ms = (time.monotonic() - start) * 1000
            adapter._record_response(kwargs, response, duration_ms)
            return response

        async def patched_async_create(self_messages: Any, *args: Any, **kwargs: Any) -> Any:
            start = time.monotonic()
            try:
                response = await original_async(self_messages, *args, **kwargs)
            except Exception as exc:
                duration_ms = (time.monotonic() - start) * 1000
                adapter._record_error(kwargs, duration_ms, str(exc))
                raise
            duration_ms = (time.monotonic() - start) * 1000
            adapter._record_response(kwargs, response, duration_ms)
            return response

        Messages.create = patched_sync_create  # type: ignore[method-assign]
        AsyncMessages.create = patched_async_create  # type: ignore[method-assign]
        self._patched = True

    def _unpatch(self) -> None:
        if not self._patched:
            return
        if self._Messages is not None and self._original_sync_create is not None:
            self._Messages.create = self._original_sync_create  # type: ignore[method-assign]
        if self._AsyncMessages is not None and self._original_async_create is not None:
            self._AsyncMessages.create = self._original_async_create  # type: ignore[method-assign]
        self._patched = False

    # -- recording helpers --------------------------------------------------

    def _record_response(self, kwargs: dict[str, Any], response: Any, duration_ms: float) -> None:
        ctx = get_active_context()
        if ctx is None:
            return

        model: str = getattr(response, "model", None) or kwargs.get("model", _UNKNOWN_MODEL)
        messages = kwargs.get("messages", [])
        input_str = _messages_to_str(messages) if isinstance(messages, list) else str(messages)
        output_str = _response_to_str(response)

        input_tokens = 0
        output_tokens = 0
        try:
            usage = response.usage
            if usage:
                input_tokens = getattr(usage, "input_tokens", 0) or 0
                output_tokens = getattr(usage, "output_tokens", 0) or 0
        except AttributeError:
            pass

        cost_usd = _estimate_cost(model, input_tokens, output_tokens)

        ctx.record_llm_call(
            model=model,
            input=input_str,
            output=output_str,
            duration_ms=duration_ms,
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
            cost_usd=cost_usd,
            metadata={"stop_reason": _get_stop_reason(response)},
        )

    def _record_error(self, kwargs: dict[str, Any], duration_ms: float, error: str) -> None:
        ctx = get_active_context()
        if ctx is None:
            return

        model: str = kwargs.get("model", _UNKNOWN_MODEL)
        messages = kwargs.get("messages", [])
        input_str = _messages_to_str(messages) if isinstance(messages, list) else str(messages)

        span = Span(
            kind=SpanKind.LLM_RESPONSE,
            name=f"llm:{model}",
            duration_ms=duration_ms,
            input=input_str,
            output=None,
            model=model,
            error=error,
        )
        ctx.record_span(span)
