"""Google GenAI SDK adapter for non-streaming Gemini content generation.

``GeminiAdapter()`` records ``client.models.generate_content()`` and
``await client.aio.models.generate_content()`` into the active CaptureContext.
It patches the SDK resource classes, covering clients created before entry.
The legacy ``google-generativeai`` SDK and streaming methods are not captured.

Usage::

    from google import genai
    from evalcraft import CaptureContext
    from evalcraft.adapters import GeminiAdapter

    client = genai.Client(api_key="...")
    with CaptureContext(name="gemini_test") as ctx, GeminiAdapter():
        response = client.models.generate_content(
            model="gemini-2.5-flash", contents="What's the weather?"
        )

Model function-call requests are recorded in output and metadata. They do not
prove that a function ran; use evalcraft's tool capture around actual execution.
Do not nest adapters. Original methods are restored even when a call fails.
"""

from __future__ import annotations

import time
from functools import wraps
from typing import Any, ClassVar

from evalcraft.adapters.openai_adapter import _int_or_zero
from evalcraft.capture.recorder import get_active_context
from evalcraft.core.models import Span, SpanKind
from evalcraft.core.pricing import NO_CACHE_DISCOUNT, PriceTable, resolve_price

# Historical text-token rates, retained for cassette cost estimates. Cache
# storage, multimodal tiers, grounding, and provider tool charges are not priced.
# Register current account-specific rates with evalcraft.register_price().
_MODEL_PRICING: PriceTable = {
    # Gemini 2.5
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    # Gemini 2.0
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-2.0-flash-lite": (0.075, 0.30),
    # Gemini 1.5
    "gemini-1.5-pro": (1.25, 5.00),
    "gemini-1.5-pro-latest": (1.25, 5.00),
    "gemini-1.5-flash": (0.075, 0.30),
    "gemini-1.5-flash-latest": (0.075, 0.30),
    "gemini-1.5-flash-8b": (0.0375, 0.15),
    # Gemini 1.0
    "gemini-1.0-pro": (0.50, 1.50),
    "gemini-pro": (0.50, 1.50),
}

_UNKNOWN_MODEL = "unknown"


def _estimate_cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cache_read_tokens: int = 0,
) -> float | None:
    """Estimate text-token cost, or return None for an unlisted model.

    Prompt tokens are fresh input. Built-in rates conservatively price cache
    reads at the input rate; register_price can supply a cached-input discount.
    """
    price = resolve_price(model, _MODEL_PRICING, NO_CACHE_DISCOUNT, NO_CACHE_DISCOUNT)
    if price is None:
        return None
    return price.cost(prompt_tokens, completion_tokens, cache_read_tokens)


def _field(value: Any, name: str, default: Any = None) -> Any:
    return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)


def _part_to_str(part: Any) -> str:
    if isinstance(part, str):
        return part
    text = _field(part, "text")
    if isinstance(text, str) and text and _field(part, "thought") is not True:
        return text
    for field in ("function_call", "function_response"):
        function = _field(part, field)
        name = _field(function, "name")
        if isinstance(name, str) and name:
            payload = _field(function, "args" if field == "function_call" else "response", {})
            return f"[{field}:{name}({payload if isinstance(payload, dict) else {}})]"
    return ""


def _contents_to_str(contents: Any) -> str:
    """Extract readable text and function parts from dicts or SDK types."""
    if isinstance(contents, str):
        return contents
    if isinstance(contents, (list, tuple)):
        return "\n".join(_contents_to_str(item) for item in contents)
    parts = _field(contents, "parts")
    if isinstance(parts, (list, tuple)):
        text = " ".join(filter(None, (_part_to_str(part) for part in parts)))
        role = _field(contents, "role")
        return f"{role}: {text}" if isinstance(role, str) and role else text
    return _part_to_str(contents)


def _response_parts(response: Any) -> list[Any]:
    candidates = _field(response, "candidates")
    if isinstance(candidates, (list, tuple)) and candidates:
        parts = _field(_field(candidates[0], "content"), "parts")
        if isinstance(parts, (list, tuple)):
            return list(parts)
    return []


def _response_to_str(response: Any) -> str:
    """Extract the first candidate's visible text and function-call requests."""
    parts = _response_parts(response)
    if parts:
        return " ".join(filter(None, (_part_to_str(part) for part in parts)))
    try:
        text = response.text
    except (AttributeError, ValueError):
        return ""
    return text if isinstance(text, str) else ""


def _extract_model_name(model: Any) -> str:
    return model.removeprefix("models/") if isinstance(model, str) and model else _UNKNOWN_MODEL


def _get_finish_reason(response: Any) -> str:
    candidates = _field(response, "candidates")
    if isinstance(candidates, (list, tuple)) and candidates:
        reason = _field(candidates[0], "finish_reason")
        name = _field(reason, "name")
        if isinstance(name, str):
            return name
        if isinstance(reason, str):
            return reason
    return ""


def _function_calls(response: Any) -> list[dict[str, Any]]:
    calls = []
    for part in _response_parts(response):
        function = _field(part, "function_call")
        name = _field(function, "name")
        arguments = _field(function, "args")
        if isinstance(name, str) and name:
            calls.append({"name": name, "args": arguments if isinstance(arguments, dict) else {}})
    return calls


class GeminiAdapter:
    """Capture google-genai Models/AsyncModels non-streaming calls.

    This helper works as a sync or async context manager. An active capture
    context is needed to record a span. Streaming, Live API, and legacy SDK
    methods are outside its coverage. Automatic SDK tool executions are not
    separately captured; wrap those functions explicitly to record tool spans.
    """

    _active: ClassVar[GeminiAdapter | None] = None

    def __init__(self) -> None:
        self._Models: Any = None
        self._AsyncModels: Any = None
        self._original_generate: Any = None
        self._original_generate_async: Any = None
        self._patched = False

    def __enter__(self) -> GeminiAdapter:
        self._patch()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._unpatch()

    async def __aenter__(self) -> GeminiAdapter:
        self._patch()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._unpatch()

    def _patch(self) -> None:
        if GeminiAdapter._active is not None:
            raise RuntimeError("GeminiAdapter context managers must not be nested")
        try:
            from google.genai.models import AsyncModels, Models
        except ImportError as exc:
            raise ImportError(
                "The 'google-genai' package is required for GeminiAdapter. "
                "Install it with: pip install 'evalcraft[gemini]'"
            ) from exc

        self._Models, self._AsyncModels = Models, AsyncModels
        self._original_generate = Models.generate_content
        self._original_generate_async = AsyncModels.generate_content
        adapter = self
        original_generate = self._original_generate
        original_generate_async = self._original_generate_async

        @wraps(original_generate)
        def patched_generate(self_models: Any, *args: Any, **kwargs: Any) -> Any:
            start = time.monotonic()
            try:
                response = original_generate(self_models, *args, **kwargs)
            except Exception as exc:
                adapter._record_error(kwargs, (time.monotonic() - start) * 1000, str(exc))
                raise
            adapter._record_response(kwargs, response, (time.monotonic() - start) * 1000)
            return response

        @wraps(original_generate_async)
        async def patched_generate_async(self_models: Any, *args: Any, **kwargs: Any) -> Any:
            start = time.monotonic()
            try:
                response = await original_generate_async(self_models, *args, **kwargs)
            except Exception as exc:
                adapter._record_error(kwargs, (time.monotonic() - start) * 1000, str(exc))
                raise
            adapter._record_response(kwargs, response, (time.monotonic() - start) * 1000)
            return response

        Models.generate_content = patched_generate
        AsyncModels.generate_content = patched_generate_async
        self._patched = True
        GeminiAdapter._active = self

    def _unpatch(self) -> None:
        if not self._patched:
            return
        self._Models.generate_content = self._original_generate
        self._AsyncModels.generate_content = self._original_generate_async
        self._patched = False
        GeminiAdapter._active = None

    def _record_response(
        self,
        kwargs: dict[str, Any],
        response: Any,
        duration_ms: float,
    ) -> None:
        ctx = get_active_context()
        if ctx is None:
            return
        model_name = _extract_model_name(kwargs.get("model"))
        usage = _field(response, "usage_metadata")
        total_prompt = max(_int_or_zero(_field(usage, "prompt_token_count")), 0)
        cached = min(
            max(_int_or_zero(_field(usage, "cached_content_token_count")), 0), total_prompt
        )
        fresh = total_prompt - cached
        candidates = max(_int_or_zero(_field(usage, "candidates_token_count")), 0)
        thoughts = max(_int_or_zero(_field(usage, "thoughts_token_count")), 0)
        completion_tokens = candidates + thoughts
        ctx.record_llm_call(
            model=model_name,
            input=_contents_to_str(kwargs.get("contents", "")),
            output=_response_to_str(response),
            duration_ms=duration_ms,
            prompt_tokens=fresh,
            completion_tokens=completion_tokens,
            cache_read_tokens=cached,
            cost_usd=_estimate_cost(model_name, fresh, completion_tokens, cached),
            metadata={
                "finish_reason": _get_finish_reason(response),
                "thoughts_token_count": thoughts,
                "function_calls": _function_calls(response),
            },
        )

    def _record_error(self, kwargs: dict[str, Any], duration_ms: float, error: str) -> None:
        ctx = get_active_context()
        if ctx is None:
            return
        model_name = _extract_model_name(kwargs.get("model"))
        ctx.record_span(
            Span(
                kind=SpanKind.LLM_RESPONSE,
                name=f"llm:{model_name}",
                duration_ms=duration_ms,
                input=_contents_to_str(kwargs.get("contents", "")),
                output=None,
                model=model_name,
                error=error,
            )
        )
