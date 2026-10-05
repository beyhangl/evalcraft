"""Pydantic AI adapter — auto-captures agent runs into evalcraft spans.

Patches ``pydantic_ai.Agent`` so every call to ``agent.run()`` and
``agent.run_sync()`` is automatically recorded into the active
:class:`~evalcraft.capture.recorder.CaptureContext`.

Captures: model calls (with token usage and cost), tool calls made by the
agent, and the final structured or text result.

Usage::

    from evalcraft.adapters import PydanticAIAdapter
    from evalcraft import CaptureContext
    from pydantic_ai import Agent

    agent = Agent("openai:gpt-5.4-nano", system_prompt="You are helpful.")

    with CaptureContext(name="pydantic_ai_test") as ctx:
        with PydanticAIAdapter():
            result = agent.run_sync("What's the weather in Paris?")

    cassette = ctx.cassette
    print(cassette.total_tokens, cassette.total_cost_usd)

The adapter patches the class-level methods on ``Agent`` so all agent
instances are captured.

Thread / async safety: the adapter is NOT reentrant — don't nest two
``PydanticAIAdapter`` context managers.  It restores the original methods
on exit even if an exception is raised.
"""

from __future__ import annotations

import time
from typing import Any

from evalcraft.capture.recorder import get_active_context
from evalcraft.core.models import Span, SpanKind
from evalcraft.core.pricing import (
    NO_CACHE_DISCOUNT,
    PriceTable,
    price_for,
    resolve_price,
)

# ---------------------------------------------------------------------------
# Pricing — OpenAI, Anthropic and Gemini models are priced from the shared
# tables (evalcraft.core.pricing.price_for) so the adapters can't disagree.
# This table only holds models served through other providers.
# ---------------------------------------------------------------------------
_MODEL_PRICING: PriceTable = {
    # Groq
    "llama-3.3-70b-versatile": (0.59, 0.79),
    "llama-3.1-8b-instant": (0.05, 0.08),
}

_UNKNOWN_MODEL = "unknown"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float | None:
    """Return an estimated USD cost or *None* if the model is not in the table."""
    price = price_for(model) or resolve_price(
        model, _MODEL_PRICING, NO_CACHE_DISCOUNT, NO_CACHE_DISCOUNT
    )
    return price.cost(prompt_tokens, completion_tokens) if price is not None else None


def _normalize_model_name(model_str: str) -> str:
    """Strip provider prefix from Pydantic AI model strings.

    Pydantic AI uses "openai:gpt-5.4-nano" or "anthropic:claude-sonnet-4-6".
    We strip the provider prefix to match our pricing table.
    """
    if ":" in model_str:
        return model_str.split(":", 1)[1]
    return model_str


def _extract_model_name(agent: Any) -> str:
    """Extract the model name from a Pydantic AI Agent instance."""
    try:
        model = agent.model
        if model is None:
            return _UNKNOWN_MODEL
        # model can be a string or a Model object
        if isinstance(model, str):
            return _normalize_model_name(model)
        # Model objects have a model_name or name attribute
        if hasattr(model, "model_name"):
            return _normalize_model_name(str(model.model_name))
        if hasattr(model, "name"):
            return _normalize_model_name(str(model.name))
        return _normalize_model_name(str(model))
    except (AttributeError, TypeError):
        return _UNKNOWN_MODEL


def _extract_usage(result: Any) -> tuple[int, int]:
    """Extract token usage from a Pydantic AI RunResult."""
    prompt_tokens = 0
    completion_tokens = 0
    try:
        usage = result.usage()
        if usage:
            prompt_tokens = getattr(usage, "request_tokens", 0) or 0
            completion_tokens = getattr(usage, "response_tokens", 0) or 0
            # Fallback to total_tokens if available
            if not prompt_tokens and not completion_tokens:
                total = getattr(usage, "total_tokens", 0) or 0
                prompt_tokens = total // 2
                completion_tokens = total - prompt_tokens
    except (AttributeError, TypeError):
        pass
    return prompt_tokens, completion_tokens


def _extract_output(result: Any) -> str:
    """Extract the text output from a Pydantic AI RunResult."""
    try:
        # result.data is the structured or text result
        data = result.data
        if isinstance(data, str):
            return data
        return str(data)
    except (AttributeError, TypeError):
        return str(result)


def _extract_tool_calls(result: Any) -> list[dict[str, Any]]:
    """Extract tool call information from a Pydantic AI RunResult."""
    tool_calls: list[dict[str, Any]] = []
    try:
        # Pydantic AI stores messages in result.all_messages()
        for msg in result.all_messages():
            # Look for tool call parts in model responses
            if hasattr(msg, "parts"):
                for part in msg.parts:
                    if hasattr(part, "tool_name"):
                        tool_calls.append({
                            "tool_name": part.tool_name,
                            "args": getattr(part, "args", None),
                            "tool_call_id": getattr(part, "tool_call_id", None),
                        })
                    # Also check for ToolReturn parts
                    if hasattr(part, "tool_name") and hasattr(part, "content"):
                        # This is a tool return, find matching call
                        pass
    except (AttributeError, TypeError):
        pass
    return tool_calls


def _extract_tool_results(result: Any) -> dict[str, Any]:
    """Extract tool results keyed by tool_call_id from a Pydantic AI RunResult."""
    results: dict[str, Any] = {}
    try:
        for msg in result.all_messages():
            if hasattr(msg, "parts"):
                for part in msg.parts:
                    # ToolReturnPart has tool_name, content, tool_call_id
                    part_type = type(part).__name__
                    if "ToolReturn" in part_type or "tool_return" in part_type.lower():
                        tool_id = getattr(part, "tool_call_id", None)
                        if tool_id:
                            results[tool_id] = getattr(part, "content", None)
    except (AttributeError, TypeError):
        pass
    return results


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class PydanticAIAdapter:
    """Patches Pydantic AI's Agent to auto-record every run into evalcraft.

    Works as both a **sync** and **async** context manager.  Patches the
    ``Agent`` class so *all* agent instances are captured.

    .. code-block:: python

        with PydanticAIAdapter():
            result = agent.run_sync("Hello")

        async with PydanticAIAdapter():
            result = await agent.run("Hello")

    Spans are silently dropped when no :class:`CaptureContext` is active.

    Raises:
        ImportError: if ``pydantic-ai`` is not installed.
    """

    def __init__(self) -> None:
        self._Agent: Any = None
        self._original_run: Any = None
        self._original_run_sync: Any = None
        self._patched: bool = False

    # -- context manager protocol ------------------------------------------

    def __enter__(self) -> PydanticAIAdapter:
        self._patch()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._unpatch()

    async def __aenter__(self) -> PydanticAIAdapter:
        self._patch()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._unpatch()

    # -- patching -----------------------------------------------------------

    def _patch(self) -> None:
        if self._patched:
            return
        try:
            from pydantic_ai import Agent  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "The 'pydantic-ai' package is required for PydanticAIAdapter. "
                "Install it with: pip install 'evalcraft[pydantic-ai]'"
            ) from exc

        self._Agent = Agent
        self._original_run = Agent.run
        self._original_run_sync = Agent.run_sync

        adapter = self
        original_run = self._original_run
        original_run_sync = self._original_run_sync

        async def patched_run(self_agent: Any, *args: Any, **kwargs: Any) -> Any:
            start = time.monotonic()
            try:
                result = await original_run(self_agent, *args, **kwargs)
            except Exception as exc:
                duration_ms = (time.monotonic() - start) * 1000
                adapter._record_error(self_agent, args, kwargs, duration_ms, str(exc))
                raise
            duration_ms = (time.monotonic() - start) * 1000
            adapter._record_result(self_agent, args, kwargs, result, duration_ms)
            return result

        def patched_run_sync(self_agent: Any, *args: Any, **kwargs: Any) -> Any:
            start = time.monotonic()
            try:
                result = original_run_sync(self_agent, *args, **kwargs)
            except Exception as exc:
                duration_ms = (time.monotonic() - start) * 1000
                adapter._record_error(self_agent, args, kwargs, duration_ms, str(exc))
                raise
            duration_ms = (time.monotonic() - start) * 1000
            adapter._record_result(self_agent, args, kwargs, result, duration_ms)
            return result

        Agent.run = patched_run  # type: ignore[method-assign]
        Agent.run_sync = patched_run_sync  # type: ignore[method-assign]
        self._patched = True

    def _unpatch(self) -> None:
        if not self._patched:
            return
        if self._Agent is not None and self._original_run is not None:
            self._Agent.run = self._original_run  # type: ignore[method-assign]
        if self._Agent is not None and self._original_run_sync is not None:
            self._Agent.run_sync = self._original_run_sync  # type: ignore[method-assign]
        self._patched = False

    # -- recording helpers --------------------------------------------------

    def _record_result(
        self,
        agent: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        result: Any,
        duration_ms: float,
    ) -> None:
        ctx = get_active_context()
        if ctx is None:
            return

        model_name = _extract_model_name(agent)
        user_prompt = args[0] if args else kwargs.get("user_prompt", "")
        if not isinstance(user_prompt, str):
            user_prompt = str(user_prompt)

        output_str = _extract_output(result)
        prompt_tokens, completion_tokens = _extract_usage(result)
        cost_usd = _estimate_cost(model_name, prompt_tokens, completion_tokens)

        # Record tool calls as separate spans
        tool_calls = _extract_tool_calls(result)
        tool_results = _extract_tool_results(result)

        for tc in tool_calls:
            tool_result = tool_results.get(tc.get("tool_call_id", ""))
            ctx.record_tool_call(
                tool_name=tc["tool_name"],
                args=tc.get("args"),
                result=tool_result,
            )

        # Record the LLM call
        ctx.record_llm_call(
            model=model_name,
            input=user_prompt,
            output=output_str,
            duration_ms=duration_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
            metadata={
                "framework": "pydantic-ai",
                "agent_name": getattr(agent, "name", None) or "",
                "tool_count": len(tool_calls),
            },
        )

    def _record_error(
        self,
        agent: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        duration_ms: float,
        error: str,
    ) -> None:
        ctx = get_active_context()
        if ctx is None:
            return

        model_name = _extract_model_name(agent)
        user_prompt = args[0] if args else kwargs.get("user_prompt", "")
        if not isinstance(user_prompt, str):
            user_prompt = str(user_prompt)

        span = Span(
            kind=SpanKind.LLM_RESPONSE,
            name=f"llm:{model_name}",
            duration_ms=duration_ms,
            input=user_prompt,
            output=None,
            model=model_name,
            error=error,
            metadata={"framework": "pydantic-ai"},
        )
        ctx.record_span(span)
