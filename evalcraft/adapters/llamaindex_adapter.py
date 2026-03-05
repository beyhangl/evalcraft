"""LlamaIndex adapter — captures query engine and agent events as evalcraft spans.

Hooks into LlamaIndex's callback system by registering a custom
:class:`BaseCallbackHandler` that converts LlamaIndex events into evalcraft
spans.  The handler is injected into LlamaIndex's global
``Settings.callback_manager`` (or an explicitly provided one) for the
duration of the ``with`` block.

Events captured:

- **LLM calls** (``CBEventType.LLM``) — prompt / response text, duration.
- **Queries** (``CBEventType.QUERY``) — query string, overall duration.
- **Retrieval** (``CBEventType.RETRIEVE``) — query string, retrieved nodes.
- **Synthesis** (``CBEventType.SYNTHESIZE``) — query string, final response.
- **Function / tool calls** (``CBEventType.FUNCTION_CALL``) — tool name,
  arguments, and return value.
- **Agent steps** (``CBEventType.AGENT_STEP``) — step input and output.

Usage::

    from evalcraft.adapters import LlamaIndexAdapter
    from evalcraft import CaptureContext
    from llama_index.core import VectorStoreIndex, SimpleDirectoryReader

    index = VectorStoreIndex.from_documents(documents)
    query_engine = index.as_query_engine()

    with CaptureContext(name="llamaindex_run") as ctx:
        with LlamaIndexAdapter():
            response = query_engine.query("What is RAG?")

    cassette = ctx.cassette
    print(cassette.total_tokens)
    print(cassette.get_tool_sequence())

The adapter is safe to use when no :class:`CaptureContext` is active — spans
are simply dropped.

Requirements:
    ``llama-index-core >= 0.10`` must be installed.
"""

from __future__ import annotations

import time
from typing import Any

from evalcraft.capture.recorder import get_active_context
from evalcraft.core.models import Span, SpanKind


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_str(obj: Any, max_len: int = 2000) -> str:
    """Convert *obj* to string, truncated to *max_len* characters."""
    try:
        text = str(obj)
    except Exception:
        return "<unserializable>"
    return text[:max_len] if len(text) > max_len else text


def _extract_nodes_summary(nodes: Any) -> str:
    """Summarise a list of retrieved NodeWithScore objects."""
    if not nodes:
        return ""
    try:
        parts = []
        for i, node in enumerate(nodes[:10]):  # limit to first 10 nodes
            score = getattr(node, "score", None)
            text = ""
            n = getattr(node, "node", node)
            text = _safe_str(getattr(n, "text", "") or getattr(n, "get_content", lambda: "")())
            text = text[:200]
            score_str = f" (score={score:.4f})" if score is not None else ""
            parts.append(f"[node{i}{score_str}]: {text}")
        return "\n".join(parts)
    except Exception:
        return _safe_str(nodes)


def _extract_llm_messages(messages: Any) -> str:
    """Flatten a list of LlamaIndex ChatMessage objects into a readable string."""
    if not messages:
        return ""
    if isinstance(messages, str):
        return messages[:2000]
    try:
        parts = []
        for msg in messages:
            role = str(getattr(msg, "role", "unknown"))
            content = str(getattr(msg, "content", "") or "")
            parts.append(f"{role}: {content[:500]}")
        return "\n".join(parts)
    except Exception:
        return _safe_str(messages)


def _extract_llm_response(response: Any) -> tuple[str, int, int]:
    """Return ``(text, prompt_tokens, completion_tokens)`` from an LLM response.

    Handles both ``CompletionResponse`` and ``ChatResponse`` types.
    """
    text = ""
    prompt_tokens = 0
    completion_tokens = 0
    try:
        # ChatResponse: .message.content
        msg = getattr(response, "message", None)
        if msg is not None:
            text = _safe_str(getattr(msg, "content", "") or "")
        else:
            # CompletionResponse: .text
            text = _safe_str(getattr(response, "text", "") or "")

        # Token usage from raw response or additional_kwargs.
        raw = getattr(response, "raw", None)
        if raw is not None:
            usage = getattr(raw, "usage", None) or (
                raw.get("usage") if isinstance(raw, dict) else None
            )
            if usage is not None:
                if isinstance(usage, dict):
                    prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
                    completion_tokens = int(usage.get("completion_tokens", 0) or 0)
                else:
                    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
                    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    except (AttributeError, TypeError, ValueError):
        pass
    return text, prompt_tokens, completion_tokens


# ---------------------------------------------------------------------------
# Handler factory (lazy import)
# ---------------------------------------------------------------------------

def _build_handler_class(CBEventType: Any, EventPayload: Any, BaseCallbackHandler: Any) -> type:
    """Build and return the concrete ``BaseCallbackHandler`` subclass.

    Built dynamically so that ``llama_index`` is only imported when the adapter
    is actually entered.
    """

    class _EvalcraftLlamaIndexHandler(BaseCallbackHandler):  # type: ignore[misc]
        """Converts LlamaIndex callback events into evalcraft spans."""

        def __init__(self) -> None:
            # BaseCallbackHandler accepts event_starts_to_ignore / event_ends_to_ignore
            super().__init__(event_starts_to_ignore=[], event_ends_to_ignore=[])
            self._pending: dict[str, float] = {}

        def _mark_start(self, event_id: str) -> None:
            self._pending[event_id] = time.monotonic()

        def _pop_duration(self, event_id: str) -> float:
            start = self._pending.pop(event_id, time.monotonic())
            return (time.monotonic() - start) * 1000

        # -- Required abstract methods -------------------------------------

        def start_trace(self, trace_id: str | None = None) -> None:
            pass

        def end_trace(
            self,
            trace_id: str | None = None,
            trace_map: dict[str, list[str]] | None = None,
        ) -> None:
            pass

        # -- Event lifecycle -----------------------------------------------

        def on_event_start(
            self,
            event_type: Any,
            payload: dict[str, Any] | None = None,
            event_id: str = "",
            parent_id: str = "",
            **kwargs: Any,
        ) -> str:
            self._mark_start(event_id)
            return event_id

        def on_event_end(
            self,
            event_type: Any,
            payload: dict[str, Any] | None = None,
            event_id: str = "",
            **kwargs: Any,
        ) -> None:
            duration_ms = self._pop_duration(event_id)
            ctx = get_active_context()
            if ctx is None:
                return

            payload = payload or {}

            # -- LLM call --------------------------------------------------
            if event_type == CBEventType.LLM:
                response = payload.get(EventPayload.RESPONSE) or payload.get(
                    getattr(EventPayload, "COMPLETION", "completion"), None
                )
                messages = payload.get(EventPayload.MESSAGES) or payload.get(
                    getattr(EventPayload, "PROMPT", "prompt"), None
                )
                serialized = payload.get(getattr(EventPayload, "SERIALIZED", "serialized"), {}) or {}

                model = (
                    serialized.get("model")
                    or serialized.get("model_name")
                    or "unknown"
                )
                input_str = _extract_llm_messages(messages) if messages is not None else ""
                output_str, prompt_tokens, completion_tokens = ("", 0, 0)
                if response is not None:
                    output_str, prompt_tokens, completion_tokens = _extract_llm_response(response)

                ctx.record_llm_call(
                    model=str(model),
                    input=input_str,
                    output=output_str,
                    duration_ms=duration_ms,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )

            # -- Query -----------------------------------------------------
            elif event_type == CBEventType.QUERY:
                query_str = _safe_str(
                    payload.get(EventPayload.QUERY_STR)
                    or payload.get(getattr(EventPayload, "QUERY", "query"), "")
                )
                response = payload.get(EventPayload.RESPONSE) or ""
                span = Span(
                    kind=SpanKind.AGENT_STEP,
                    name="query",
                    input=query_str,
                    output=_safe_str(response),
                    duration_ms=duration_ms,
                )
                ctx.record_span(span)

            # -- Retrieval -------------------------------------------------
            elif event_type == CBEventType.RETRIEVE:
                query_str = _safe_str(
                    payload.get(EventPayload.QUERY_STR)
                    or payload.get(getattr(EventPayload, "QUERY", "query"), "")
                )
                nodes = payload.get(EventPayload.NODES) or []
                nodes_summary = _extract_nodes_summary(nodes)
                span = Span(
                    kind=SpanKind.AGENT_STEP,
                    name="retrieve",
                    input=query_str,
                    output=nodes_summary or None,
                    duration_ms=duration_ms,
                    metadata={"num_nodes": len(nodes) if nodes else 0},
                )
                ctx.record_span(span)

            # -- Synthesis -------------------------------------------------
            elif event_type == getattr(CBEventType, "SYNTHESIZE", None):
                query_str = _safe_str(
                    payload.get(EventPayload.QUERY_STR)
                    or payload.get(getattr(EventPayload, "QUERY", "query"), "")
                )
                response = payload.get(EventPayload.RESPONSE) or ""
                span = Span(
                    kind=SpanKind.AGENT_STEP,
                    name="synthesize",
                    input=query_str,
                    output=_safe_str(response),
                    duration_ms=duration_ms,
                )
                ctx.record_span(span)

            # -- Function / tool call ---------------------------------------
            elif event_type == getattr(CBEventType, "FUNCTION_CALL", None):
                tool = payload.get(getattr(EventPayload, "TOOL", "tool"))
                tool_name = "unknown"
                if tool is not None:
                    tool_name = _safe_str(getattr(tool, "name", None) or tool)
                func_call = payload.get(getattr(EventPayload, "FUNCTION_CALL", "function_call"))
                func_output = payload.get(
                    getattr(EventPayload, "FUNCTION_OUTPUT", "function_output")
                )

                tool_args: dict[str, Any] | None = None
                if isinstance(func_call, dict):
                    tool_args = func_call
                elif func_call is not None:
                    tool_args = {"input": _safe_str(func_call)}

                ctx.record_tool_call(
                    tool_name=tool_name,
                    args=tool_args,
                    result=_safe_str(func_output) if func_output is not None else None,
                    duration_ms=duration_ms,
                )

            # -- Agent step ------------------------------------------------
            elif event_type == getattr(CBEventType, "AGENT_STEP", None):
                messages = payload.get(EventPayload.MESSAGES) or payload.get(
                    getattr(EventPayload, "PROMPT", "prompt"), None
                )
                response = payload.get(EventPayload.RESPONSE) or ""
                input_str = _extract_llm_messages(messages) if messages is not None else ""
                span = Span(
                    kind=SpanKind.AGENT_STEP,
                    name="agent:step",
                    input=input_str or None,
                    output=_safe_str(response) or None,
                    duration_ms=duration_ms,
                )
                ctx.record_span(span)

    return _EvalcraftLlamaIndexHandler


# ---------------------------------------------------------------------------
# Public adapter
# ---------------------------------------------------------------------------

class LlamaIndexAdapter:
    """Hooks into LlamaIndex's callback system to record events as evalcraft spans.

    Registers a custom :class:`BaseCallbackHandler` with LlamaIndex's global
    ``Settings.callback_manager`` (or an explicitly provided callback manager)
    so that LLM calls, retrieval, synthesis, and function calls are captured
    automatically for the duration of the ``with`` block.

    .. code-block:: python

        with LlamaIndexAdapter():
            response = query_engine.query("What is RAG?")

        async with LlamaIndexAdapter():
            response = await query_engine.aquery("What is RAG?")

        # Inject into a specific callback manager instead of global Settings:
        cm = CallbackManager()
        with LlamaIndexAdapter(callback_manager=cm):
            index = VectorStoreIndex.from_documents(docs, callback_manager=cm)
            response = index.as_query_engine().query("...")

    The adapter restores the callback manager to its original state on exit,
    even if an exception is raised inside the ``with`` block.

    Args:
        callback_manager: Optional ``llama_index.core.callbacks.CallbackManager``
            instance.  If *None*, the adapter injects into
            ``llama_index.core.Settings.callback_manager``.

    Raises:
        ImportError: if ``llama-index-core`` is not installed.
    """

    def __init__(self, callback_manager: Any = None) -> None:
        self._explicit_callback_manager = callback_manager
        self._actual_callback_manager: Any = None
        self._handler: Any = None
        self._patched: bool = False

    # -- context manager protocol ------------------------------------------

    def __enter__(self) -> "LlamaIndexAdapter":
        self._patch()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._unpatch()

    async def __aenter__(self) -> "LlamaIndexAdapter":
        self._patch()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._unpatch()

    # -- patching -----------------------------------------------------------

    def _patch(self) -> None:
        if self._patched:
            return

        # Lazy imports — only when the adapter is actually entered.
        try:
            from llama_index.core.callbacks import (  # type: ignore[import]
                CallbackManager,
                CBEventType,
                EventPayload,
            )
            from llama_index.core.callbacks.base_handler import (  # type: ignore[import]
                BaseCallbackHandler,
            )
        except ImportError as exc:
            raise ImportError(
                "The 'llama-index-core' package is required for LlamaIndexAdapter. "
                "Install it with: pip install 'evalcraft[llamaindex]'"
            ) from exc

        HandlerClass = _build_handler_class(CBEventType, EventPayload, BaseCallbackHandler)
        self._handler = HandlerClass()

        if self._explicit_callback_manager is not None:
            self._actual_callback_manager = self._explicit_callback_manager
        else:
            try:
                from llama_index.core import Settings  # type: ignore[import]
                if Settings.callback_manager is None:
                    Settings.callback_manager = CallbackManager()
                self._actual_callback_manager = Settings.callback_manager
            except (ImportError, AttributeError) as exc:
                raise ImportError(
                    "Could not access llama_index.core.Settings. "
                    "Pass a CallbackManager explicitly or upgrade llama-index-core."
                ) from exc

        self._actual_callback_manager.add_handler(self._handler)
        self._patched = True

    def _unpatch(self) -> None:
        if not self._patched or self._handler is None:
            return
        try:
            self._actual_callback_manager.remove_handler(self._handler)
        except Exception:
            pass
        self._handler = None
        self._actual_callback_manager = None
        self._patched = False
