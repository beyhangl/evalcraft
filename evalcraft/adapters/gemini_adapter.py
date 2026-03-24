"""Google Gemini SDK adapter — auto-captures LLM calls into evalcraft spans.

Monkey-patches ``google.generativeai.GenerativeModel`` so every call to
``model.generate_content()`` (sync or async) is automatically recorded into
the active :class:`~evalcraft.capture.recorder.CaptureContext`.

Usage::

    from evalcraft.adapters import GeminiAdapter
    from evalcraft import CaptureContext
    import google.generativeai as genai

    genai.configure(api_key="...")
    model = genai.GenerativeModel("gemini-2.0-flash")

    with CaptureContext(name="gemini_test") as ctx:
        with GeminiAdapter():
            response = model.generate_content("What's the weather?")

    cassette = ctx.cassette
    print(cassette.total_tokens, cassette.total_cost_usd)

The adapter patches the class-level method rather than a specific model
instance, so all ``GenerativeModel`` instances are captured.

Thread / async safety: the adapter is NOT reentrant — don't nest two
``GeminiAdapter`` context managers.  It restores the original methods on
exit even if an exception is raised.
"""

from __future__ import annotations

import time
from typing import Any

from evalcraft.capture.recorder import get_active_context
from evalcraft.core.models import Span, SpanKind, TokenUsage


# ---------------------------------------------------------------------------
# Pricing table — approximate cost per 1 M tokens (input_usd, output_usd).
# Prices reflect Google's public rates as of early 2026; update as needed.
# ---------------------------------------------------------------------------
_MODEL_PRICING: dict[str, tuple[float, float]] = {
    # Gemini 2.5
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-2.5-flash": (0.15, 0.60),
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


def _contents_to_str(contents: Any) -> str:
    """Flatten Gemini ``contents`` into a single readable string."""
    if isinstance(contents, str):
        return contents

    if isinstance(contents, list):
        parts: list[str] = []
        for item in contents:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                # {"role": "user", "parts": ["text"]}
                role = item.get("role", "")
                item_parts = item.get("parts", [])
                text_parts = []
                for p in item_parts:
                    if isinstance(p, str):
                        text_parts.append(p)
                    elif isinstance(p, dict) and "text" in p:
                        text_parts.append(p["text"])
                parts.append(f"{role}: {' '.join(text_parts)}" if role else " ".join(text_parts))
            elif hasattr(item, "text"):
                parts.append(item.text)
            elif hasattr(item, "parts"):
                for p in item.parts:
                    if hasattr(p, "text"):
                        parts.append(p.text)
        return "\n".join(parts)

    # Protobuf Content or Part objects
    if hasattr(contents, "parts"):
        return " ".join(p.text for p in contents.parts if hasattr(p, "text"))

    return str(contents)


def _response_to_str(response: Any) -> str:
    """Extract text from a Gemini GenerateContentResponse."""
    try:
        # response.text is the convenience accessor
        return response.text
    except (AttributeError, ValueError):
        pass

    # Fallback: iterate candidates
    try:
        parts: list[str] = []
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if hasattr(part, "text") and part.text:
                    parts.append(part.text)
                elif hasattr(part, "function_call"):
                    fc = part.function_call
                    parts.append(f"[function_call:{fc.name}({dict(fc.args)})]")
        return " ".join(parts)
    except (AttributeError, IndexError):
        return str(response)


def _extract_model_name(model_obj: Any) -> str:
    """Extract the model name string from a GenerativeModel instance."""
    # GenerativeModel stores the model name in model_name attribute
    if hasattr(model_obj, "model_name"):
        name = model_obj.model_name
        # Remove "models/" prefix if present
        if isinstance(name, str) and name.startswith("models/"):
            return name[len("models/"):]
        return str(name)
    return _UNKNOWN_MODEL


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class GeminiAdapter:
    """Patches the Google Gemini SDK to auto-record every generate_content call.

    Works as both a **sync** and **async** context manager.  Patches the
    ``GenerativeModel`` class so *all* model instances are captured.

    .. code-block:: python

        with GeminiAdapter():
            response = model.generate_content(...)

        async with GeminiAdapter():
            response = await model.generate_content_async(...)

    Spans are silently dropped when no :class:`CaptureContext` is active —
    so the adapter is safe to leave in place during non-test code paths.

    Raises:
        ImportError: if ``google-generativeai`` is not installed.
    """

    def __init__(self) -> None:
        self._GenerativeModel: Any = None
        self._original_generate: Any = None
        self._original_generate_async: Any = None
        self._patched: bool = False

    # -- context manager protocol ------------------------------------------

    def __enter__(self) -> "GeminiAdapter":
        self._patch()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._unpatch()

    async def __aenter__(self) -> "GeminiAdapter":
        self._patch()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._unpatch()

    # -- patching -----------------------------------------------------------

    def _patch(self) -> None:
        if self._patched:
            return
        try:
            from google.generativeai import GenerativeModel  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "The 'google-generativeai' package is required for GeminiAdapter. "
                "Install it with: pip install 'evalcraft[gemini]'"
            ) from exc

        self._GenerativeModel = GenerativeModel
        self._original_generate = GenerativeModel.generate_content
        self._original_generate_async = getattr(GenerativeModel, "generate_content_async", None)

        adapter = self
        original_generate = self._original_generate
        original_generate_async = self._original_generate_async

        def patched_generate(self_model: Any, *args: Any, **kwargs: Any) -> Any:
            start = time.monotonic()
            try:
                response = original_generate(self_model, *args, **kwargs)
            except Exception as exc:
                duration_ms = (time.monotonic() - start) * 1000
                adapter._record_error(self_model, args, kwargs, duration_ms, str(exc))
                raise
            duration_ms = (time.monotonic() - start) * 1000
            adapter._record_response(self_model, args, kwargs, response, duration_ms)
            return response

        GenerativeModel.generate_content = patched_generate  # type: ignore[method-assign]

        if original_generate_async is not None:
            async def patched_generate_async(self_model: Any, *args: Any, **kwargs: Any) -> Any:
                start = time.monotonic()
                try:
                    response = await original_generate_async(self_model, *args, **kwargs)
                except Exception as exc:
                    duration_ms = (time.monotonic() - start) * 1000
                    adapter._record_error(self_model, args, kwargs, duration_ms, str(exc))
                    raise
                duration_ms = (time.monotonic() - start) * 1000
                adapter._record_response(self_model, args, kwargs, response, duration_ms)
                return response

            GenerativeModel.generate_content_async = patched_generate_async  # type: ignore[method-assign]

        self._patched = True

    def _unpatch(self) -> None:
        if not self._patched:
            return
        if self._GenerativeModel is not None and self._original_generate is not None:
            self._GenerativeModel.generate_content = self._original_generate  # type: ignore[method-assign]
        if self._GenerativeModel is not None and self._original_generate_async is not None:
            self._GenerativeModel.generate_content_async = self._original_generate_async  # type: ignore[method-assign]
        self._patched = False

    # -- recording helpers --------------------------------------------------

    def _record_response(
        self,
        model_obj: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        response: Any,
        duration_ms: float,
    ) -> None:
        ctx = get_active_context()
        if ctx is None:
            return

        model_name = _extract_model_name(model_obj)

        # Build input string from positional contents arg or kwarg
        contents = args[0] if args else kwargs.get("contents", "")
        input_str = _contents_to_str(contents)
        output_str = _response_to_str(response)

        prompt_tokens = 0
        completion_tokens = 0
        try:
            usage = response.usage_metadata
            if usage:
                prompt_tokens = getattr(usage, "prompt_token_count", 0) or 0
                completion_tokens = getattr(usage, "candidates_token_count", 0) or 0
        except AttributeError:
            pass

        cost_usd = _estimate_cost(model_name, prompt_tokens, completion_tokens)

        ctx.record_llm_call(
            model=model_name,
            input=input_str,
            output=output_str,
            duration_ms=duration_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
            metadata={
                "finish_reason": _get_finish_reason(response),
            },
        )

    def _record_error(
        self,
        model_obj: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        duration_ms: float,
        error: str,
    ) -> None:
        ctx = get_active_context()
        if ctx is None:
            return

        model_name = _extract_model_name(model_obj)
        contents = args[0] if args else kwargs.get("contents", "")
        input_str = _contents_to_str(contents)

        span = Span(
            kind=SpanKind.LLM_RESPONSE,
            name=f"llm:{model_name}",
            duration_ms=duration_ms,
            input=input_str,
            output=None,
            model=model_name,
            error=error,
        )
        ctx.record_span(span)


def _get_finish_reason(response: Any) -> str:
    """Extract the finish reason from a Gemini response."""
    try:
        candidates = response.candidates
        if candidates:
            reason = candidates[0].finish_reason
            if reason is not None:
                # finish_reason is an enum in the Gemini SDK
                return str(reason.name) if hasattr(reason, "name") else str(reason)
    except (AttributeError, IndexError):
        pass
    return ""
