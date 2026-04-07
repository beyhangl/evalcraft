"""OpenAI SDK adapter — auto-captures LLM calls into evalcraft spans.

Monkey-patches ``openai.resources.chat.completions.Completions`` so every
call to ``client.chat.completions.create()`` (sync or async) is automatically
recorded into the active :class:`~evalcraft.capture.recorder.CaptureContext`.

Usage::

    from evalcraft.adapters import OpenAIAdapter
    from evalcraft import CaptureContext
    import openai

    client = openai.OpenAI()

    with CaptureContext(name="weather_test") as ctx:
        with OpenAIAdapter():
            response = client.chat.completions.create(
                model="gpt-5.4-nano",
                messages=[{"role": "user", "content": "What's the weather?"}],
            )

    cassette = ctx.cassette
    print(cassette.total_tokens, cassette.total_cost_usd)

The adapter works with any OpenAI-compatible client (custom ``base_url``,
Azure OpenAI, etc.) because it patches the class-level method rather than
a specific client instance.

Thread / async safety: the adapter is NOT reentrant — don't nest two
``OpenAIAdapter`` context managers.  It restores the original methods on
exit even if an exception is raised.
"""

from __future__ import annotations

import time
from typing import Any

from evalcraft.capture.recorder import get_active_context
from evalcraft.core.models import Span, SpanKind, TokenUsage


# ---------------------------------------------------------------------------
# Pricing table — approximate cost per 1 M tokens (input_usd, output_usd).
# Prices reflect OpenAI's public rates as of early 2026; update as needed.
# ---------------------------------------------------------------------------
_MODEL_PRICING: dict[str, tuple[float, float]] = {
    # GPT-5.4 (latest flagship, April 2026)
    "gpt-5.4": (2.50, 15.00),
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5.4-nano": (0.20, 1.25),
    "gpt-5.4-pro": (30.00, 180.00),
    # GPT-5.3
    "gpt-5.3-codex": (1.75, 14.00),
    # GPT-5.2
    "gpt-5.2": (1.75, 14.00),
    "gpt-5.2-pro": (10.50, 84.00),
    # GPT-5.1
    "gpt-5.1-codex-mini": (0.25, 2.00),
    "gpt-5.1": (1.25, 10.00),
    # GPT-5
    "gpt-5": (1.25, 10.00),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5-nano": (0.05, 0.40),
    # GPT-4.1
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.20, 0.80),
    "gpt-4.1-nano": (0.10, 0.40),
    # GPT-4o (legacy)
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    # GPT-4 (legacy)
    "gpt-4-turbo": (10.00, 30.00),
    "gpt-4": (30.00, 60.00),
    # GPT-3.5 (legacy)
    "gpt-3.5-turbo": (0.50, 1.50),
    # Reasoning (o-series)
    "o3": (2.00, 8.00),
    "o3-mini": (1.10, 4.40),
    "o4-mini": (0.55, 2.20),
    "o4-mini-high": (1.10, 4.40),
    "o1": (15.00, 60.00),
    "o1-mini": (0.55, 2.20),
    "o1-pro": (150.00, 600.00),
    # GPT-OSS (open source)
    "gpt-oss-20b": (0.03, 0.10),
    "gpt-oss-120b": (0.039, 0.10),
}

# Names of internal LangChain/generic models to skip cost estimation for.
_UNKNOWN_MODEL = "unknown"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float | None:
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
    return (prompt_tokens * input_usd + completion_tokens * output_usd) / 1_000_000


def _messages_to_str(messages: list[Any]) -> str:
    """Flatten an OpenAI ``messages`` list into a single readable string.

    Handles both plain dicts and Pydantic model objects (e.g.
    ``ChatCompletionMessage``) that the SDK returns and agents append
    back to the conversation.
    """
    parts: list[str] = []
    for msg in messages:
        # Extract role and content — works for both dicts and Pydantic objects
        if isinstance(msg, dict):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
        else:
            role = getattr(msg, "role", "unknown") or "unknown"
            content = getattr(msg, "content", "") or ""

        if isinstance(content, list):
            # Multi-modal content blocks — extract text parts only.
            text_parts = [
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            content = " ".join(text_parts)
        elif not isinstance(content, str):
            content = str(content) if content else ""

        parts.append(f"{role}: {content}")
    return "\n".join(parts)


def _response_to_str(response: Any) -> str:
    """Extract assistant text (and any tool-call summaries) from a ChatCompletion."""
    try:
        choices = response.choices
        if not choices:
            return ""
        msg = choices[0].message
        content: str = msg.content or ""
        if msg.tool_calls:
            summaries = [
                f"[tool_call:{tc.function.name}({tc.function.arguments})]"
                for tc in msg.tool_calls
            ]
            content = (content + " " + " ".join(summaries)).strip()
        return content
    except (AttributeError, IndexError):
        return str(response)


def _get_finish_reason(response: Any) -> str:
    try:
        choices = response.choices
        if choices:
            return choices[0].finish_reason or ""
    except (AttributeError, IndexError):
        pass
    return ""


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class OpenAIAdapter:
    """Patches the OpenAI SDK to auto-record every chat completion call.

    Works as both a **sync** and **async** context manager.  Patches the
    ``Completions`` and ``AsyncCompletions`` classes so *all* client
    instances are captured, including those pointing at custom base URLs.

    .. code-block:: python

        with OpenAIAdapter():
            response = client.chat.completions.create(...)

        async with OpenAIAdapter():
            response = await client.chat.completions.create(...)

    Spans are silently dropped when no :class:`CaptureContext` is active —
    so the adapter is safe to leave in place during non-test code paths.

    Raises:
        ImportError: if ``openai`` is not installed.
    """

    def __init__(self) -> None:
        self._Completions: Any = None
        self._AsyncCompletions: Any = None
        self._original_sync_create: Any = None
        self._original_async_create: Any = None
        self._patched: bool = False

    # -- context manager protocol ------------------------------------------

    def __enter__(self) -> "OpenAIAdapter":
        self._patch()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._unpatch()

    async def __aenter__(self) -> "OpenAIAdapter":
        self._patch()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._unpatch()

    # -- patching -----------------------------------------------------------

    def _patch(self) -> None:
        if self._patched:
            return
        try:
            from openai.resources.chat.completions import (  # type: ignore[import]
                AsyncCompletions,
                Completions,
            )
        except ImportError as exc:
            raise ImportError(
                "The 'openai' package is required for OpenAIAdapter. "
                "Install it with: pip install 'evalcraft[openai]'"
            ) from exc

        self._Completions = Completions
        self._AsyncCompletions = AsyncCompletions
        self._original_sync_create = Completions.create
        self._original_async_create = AsyncCompletions.create

        adapter = self
        original_sync = self._original_sync_create
        original_async = self._original_async_create

        def patched_sync_create(self_completions: Any, *args: Any, **kwargs: Any) -> Any:
            start = time.monotonic()
            try:
                response = original_sync(self_completions, *args, **kwargs)
            except Exception as exc:
                duration_ms = (time.monotonic() - start) * 1000
                adapter._record_error(kwargs, duration_ms, str(exc))
                raise
            duration_ms = (time.monotonic() - start) * 1000
            adapter._record_response(kwargs, response, duration_ms)
            return response

        async def patched_async_create(self_completions: Any, *args: Any, **kwargs: Any) -> Any:
            start = time.monotonic()
            try:
                response = await original_async(self_completions, *args, **kwargs)
            except Exception as exc:
                duration_ms = (time.monotonic() - start) * 1000
                adapter._record_error(kwargs, duration_ms, str(exc))
                raise
            duration_ms = (time.monotonic() - start) * 1000
            adapter._record_response(kwargs, response, duration_ms)
            return response

        Completions.create = patched_sync_create  # type: ignore[method-assign]
        AsyncCompletions.create = patched_async_create  # type: ignore[method-assign]
        self._patched = True

    def _unpatch(self) -> None:
        if not self._patched:
            return
        if self._Completions is not None and self._original_sync_create is not None:
            self._Completions.create = self._original_sync_create  # type: ignore[method-assign]
        if self._AsyncCompletions is not None and self._original_async_create is not None:
            self._AsyncCompletions.create = self._original_async_create  # type: ignore[method-assign]
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

        prompt_tokens = 0
        completion_tokens = 0
        try:
            usage = response.usage
            if usage:
                prompt_tokens = usage.prompt_tokens or 0
                completion_tokens = usage.completion_tokens or 0
        except AttributeError:
            pass

        cost_usd = _estimate_cost(model, prompt_tokens, completion_tokens)

        # Record tool call spans when the LLM requests tool use
        try:
            msg = response.choices[0].message
            if msg.tool_calls:
                import json as _json
                for tc in msg.tool_calls:
                    try:
                        args = _json.loads(tc.function.arguments) if tc.function.arguments else {}
                    except (ValueError, AttributeError):
                        args = {"raw": str(getattr(tc.function, "arguments", ""))}
                    ctx.record_tool_call(
                        tool_name=tc.function.name,
                        args=args,
                    )
        except (AttributeError, IndexError):
            pass

        ctx.record_llm_call(
            model=model,
            input=input_str,
            output=output_str,
            duration_ms=duration_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
            metadata={"finish_reason": _get_finish_reason(response)},
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
