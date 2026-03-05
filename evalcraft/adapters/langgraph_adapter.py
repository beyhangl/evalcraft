"""LangGraph adapter — captures agent node execution into evalcraft spans.

Patches a compiled LangGraph graph's ``invoke``, ``ainvoke``, ``stream``, and
``astream`` methods to inject a LangChain callback handler.  The handler
records every LLM call, tool call, and node (chain) execution as an evalcraft
:class:`~evalcraft.core.models.Span`.

Usage::

    from evalcraft.adapters import LangGraphAdapter
    from evalcraft import CaptureContext

    # graph is a compiled LangGraph StateGraph
    with CaptureContext(name="agent_run") as ctx:
        with LangGraphAdapter(graph):
            result = graph.invoke({"messages": [HumanMessage("What's 2+2?")]})

    cassette = ctx.cassette
    print(cassette.get_tool_sequence())
    print(cassette.total_tokens)

The adapter is safe to use when no :class:`CaptureContext` is active — spans
are simply dropped.

Requirements:
    ``langchain-core>=0.2`` must be installed.  LangGraph depends on it
    automatically, so no extra install step is needed if you already have
    ``langgraph`` installed.

Notes:
    - The adapter patches the *instance* (not the class), so multiple graphs
      can be wrapped independently.
    - Nested ``LangGraphAdapter`` contexts on the *same* graph object are not
      supported.
    - ``stream`` / ``astream`` patch the generator wrapper; individual yielded
      events are not intercepted — only the callback-level events are recorded.
"""

from __future__ import annotations

import time
from typing import Any
from uuid import UUID

from evalcraft.capture.recorder import get_active_context
from evalcraft.core.models import Span, SpanKind, TokenUsage


# ---------------------------------------------------------------------------
# Internal names that indicate a LangChain/LangGraph housekeeping chain rather
# than a user-defined graph node.  Spans for these are skipped to reduce noise.
# ---------------------------------------------------------------------------
_INTERNAL_CHAIN_NAMES: frozenset[str] = frozenset(
    {
        "RunnableLambda",
        "RunnableSequence",
        "RunnableParallel",
        "RunnableAssign",
        "RunnableMap",
        "RunnablePick",
        "RunnablePassthrough",
        "ChannelWrite",
        "ChannelRead",
        "StateGraph",
        "CompiledStateGraph",
        "CompiledGraph",
        "Branch",
        "PregelNode",
    }
)


# ---------------------------------------------------------------------------
# Callback handler factory (lazy import to avoid hard-dep at module level)
# ---------------------------------------------------------------------------

def _build_handler_class() -> type:
    """Import ``BaseCallbackHandler`` and build a concrete subclass.

    The class is built dynamically so that ``langchain_core`` is only imported
    when the adapter is actually entered — keeping import time zero when the
    package is not installed.
    """
    try:
        from langchain_core.callbacks import BaseCallbackHandler  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "langchain_core is required for LangGraphAdapter. "
            "Install it with: pip install 'evalcraft[langchain]' or 'pip install langgraph'."
        ) from exc

    class _EvalcraftHandler(BaseCallbackHandler):  # type: ignore[misc]
        """Records LangGraph events as evalcraft spans.

        The handler maintains a ``_pending`` dict keyed by ``run_id`` to
        track when each event started so that ``duration_ms`` can be computed
        when the corresponding ``*_end`` or ``*_error`` callback fires.
        """

        def __init__(self) -> None:
            super().__init__()
            self._pending: dict[str, float] = {}

        # -- timing helpers ------------------------------------------------

        def _mark_start(self, run_id: UUID) -> None:
            self._pending[str(run_id)] = time.monotonic()

        def _pop_duration(self, run_id: UUID) -> float:
            start = self._pending.pop(str(run_id), time.monotonic())
            return (time.monotonic() - start) * 1000

        # -- LLM -----------------------------------------------------------

        def on_llm_start(
            self,
            serialized: dict[str, Any],
            prompts: list[str],
            *,
            run_id: UUID,
            **kwargs: Any,
        ) -> None:
            self._mark_start(run_id)

        def on_chat_model_start(
            self,
            serialized: dict[str, Any],
            messages: list[list[Any]],
            *,
            run_id: UUID,
            **kwargs: Any,
        ) -> None:
            self._mark_start(run_id)

        def on_llm_end(
            self,
            response: Any,
            *,
            run_id: UUID,
            **kwargs: Any,
        ) -> None:
            ctx = get_active_context()
            if ctx is None:
                self._pop_duration(run_id)
                return

            duration_ms = self._pop_duration(run_id)
            model = _extract_llm_model(response)
            prompt_tokens, completion_tokens = _extract_token_usage(response)
            output_text = _extract_llm_output(response)

            ctx.record_llm_call(
                model=model,
                input=kwargs.get("prompts") or kwargs.get("messages"),
                output=output_text,
                duration_ms=duration_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                metadata={"serialized_name": serialized.get("name", "")},
            )

        def on_llm_error(
            self,
            error: Exception,
            *,
            run_id: UUID,
            **kwargs: Any,
        ) -> None:
            ctx = get_active_context()
            if ctx is None:
                self._pop_duration(run_id)
                return

            duration_ms = self._pop_duration(run_id)
            span = Span(
                kind=SpanKind.LLM_RESPONSE,
                name="llm:error",
                duration_ms=duration_ms,
                error=str(error),
            )
            ctx.record_span(span)

        # -- Tools ---------------------------------------------------------

        def on_tool_start(
            self,
            serialized: dict[str, Any],
            input_str: str,
            *,
            run_id: UUID,
            **kwargs: Any,
        ) -> None:
            self._mark_start(run_id)

        def on_tool_end(
            self,
            output: Any,
            *,
            run_id: UUID,
            **kwargs: Any,
        ) -> None:
            ctx = get_active_context()
            if ctx is None:
                self._pop_duration(run_id)
                return

            duration_ms = self._pop_duration(run_id)
            tool_name: str = kwargs.get("name", "") or "unknown_tool"
            tool_args = kwargs.get("inputs")
            if isinstance(tool_args, str):
                tool_args = {"input": tool_args}

            ctx.record_tool_call(
                tool_name=tool_name,
                args=tool_args,
                result=output,
                duration_ms=duration_ms,
            )

        def on_tool_error(
            self,
            error: Exception,
            *,
            run_id: UUID,
            **kwargs: Any,
        ) -> None:
            ctx = get_active_context()
            if ctx is None:
                self._pop_duration(run_id)
                return

            duration_ms = self._pop_duration(run_id)
            tool_name: str = kwargs.get("name", "") or "unknown_tool"

            ctx.record_tool_call(
                tool_name=tool_name,
                args=None,
                result=None,
                duration_ms=duration_ms,
                error=str(error),
            )

        # -- Chains (graph nodes) ------------------------------------------

        def on_chain_start(
            self,
            serialized: dict[str, Any],
            inputs: dict[str, Any],
            *,
            run_id: UUID,
            **kwargs: Any,
        ) -> None:
            self._mark_start(run_id)

        def on_chain_end(
            self,
            outputs: dict[str, Any],
            *,
            run_id: UUID,
            **kwargs: Any,
        ) -> None:
            ctx = get_active_context()
            if ctx is None:
                self._pop_duration(run_id)
                return

            duration_ms = self._pop_duration(run_id)
            node_name = _extract_node_name(kwargs)
            if node_name in _INTERNAL_CHAIN_NAMES:
                return

            span = Span(
                kind=SpanKind.AGENT_STEP,
                name=f"node:{node_name}" if node_name else "node:unknown",
                duration_ms=duration_ms,
                input=_safe_serialise(inputs),
                output=_safe_serialise(outputs),
                metadata={"tags": kwargs.get("tags") or []},
            )
            ctx.record_span(span)

        def on_chain_error(
            self,
            error: Exception,
            *,
            run_id: UUID,
            **kwargs: Any,
        ) -> None:
            ctx = get_active_context()
            if ctx is None:
                self._pop_duration(run_id)
                return

            duration_ms = self._pop_duration(run_id)
            node_name = _extract_node_name(kwargs)

            span = Span(
                kind=SpanKind.AGENT_STEP,
                name=f"node:{node_name}:error" if node_name else "node:error",
                duration_ms=duration_ms,
                error=str(error),
                metadata={"tags": kwargs.get("tags") or []},
            )
            ctx.record_span(span)

    return _EvalcraftHandler


# ---------------------------------------------------------------------------
# Helper extractors
# ---------------------------------------------------------------------------

def _extract_node_name(kwargs: dict[str, Any]) -> str:
    """Derive a human-readable node name from LangGraph callback kwargs."""
    # LangGraph >=0.1 sets the node name in tags as a bare string or
    # sometimes "langgraph:node_name".
    tags: list[str] = kwargs.get("tags") or []
    for tag in tags:
        if tag and tag not in _INTERNAL_CHAIN_NAMES and ":" not in tag:
            return tag
        if tag.startswith("langgraph:"):
            return tag[len("langgraph:"):]

    # Fall back to metadata dict (varies by LangGraph version).
    meta: dict[str, Any] = kwargs.get("metadata") or {}
    node = meta.get("node") or meta.get("langgraph_node") or meta.get("step_name")
    if node:
        return str(node)

    return ""


def _extract_llm_model(response: Any) -> str:
    """Extract model name from an LLMResult."""
    try:
        llm_output: dict[str, Any] = response.llm_output or {}
        model = (
            llm_output.get("model_name")
            or llm_output.get("model")
            or llm_output.get("engine")
        )
        if model:
            return str(model)
        # Some providers embed it in generation_info.
        gens = response.generations
        if gens and gens[0]:
            info = getattr(gens[0][0], "generation_info", None) or {}
            if info.get("model"):
                return str(info["model"])
    except (AttributeError, IndexError, TypeError):
        pass
    return "unknown"


def _extract_token_usage(response: Any) -> tuple[int, int]:
    """Return (prompt_tokens, completion_tokens) from an LLMResult."""
    try:
        llm_output: dict[str, Any] = response.llm_output or {}
        usage = llm_output.get("token_usage") or llm_output.get("usage") or {}
        prompt = int(usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0))
        completion = int(
            usage.get("completion_tokens", 0) or usage.get("output_tokens", 0)
        )
        return prompt, completion
    except (AttributeError, TypeError, ValueError):
        return 0, 0


def _extract_llm_output(response: Any) -> str:
    """Extract the assistant message text from an LLMResult."""
    try:
        gens = response.generations
        if not gens or not gens[0]:
            return ""
        gen = gens[0][0]
        # ChatGeneration has a .message attribute.
        if hasattr(gen, "message"):
            return str(getattr(gen.message, "content", ""))
        return str(getattr(gen, "text", ""))
    except (AttributeError, IndexError, TypeError):
        return ""


def _safe_serialise(obj: Any) -> Any:
    """Return a JSON-safe representation of *obj*."""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, dict):
        return {k: _safe_serialise(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_safe_serialise(i) for i in obj]
    # For LangChain message objects and other pydantic-ish models.
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump()
        except Exception:
            pass
    if hasattr(obj, "dict"):
        try:
            return obj.dict()
        except Exception:
            pass
    return str(obj)


def _inject_callbacks(config: Any, handler: Any) -> dict[str, Any]:
    """Return a copy of *config* with *handler* appended to its callbacks list."""
    if config is None:
        return {"callbacks": [handler]}
    if isinstance(config, dict):
        existing = list(config.get("callbacks") or [])
        existing.append(handler)
        return {**config, "callbacks": existing}
    # RunnableConfig (TypedDict) or similar mapping.
    try:
        base: dict[str, Any] = dict(config)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        base = {}
    existing = list(base.get("callbacks") or [])
    existing.append(handler)
    base["callbacks"] = existing
    return base


# ---------------------------------------------------------------------------
# Public adapter
# ---------------------------------------------------------------------------

class LangGraphAdapter:
    """Instruments a compiled LangGraph graph to record all events as spans.

    Patches ``invoke``, ``ainvoke``, ``stream``, and ``astream`` on the
    *instance* (not the class) so that each call automatically injects an
    evalcraft callback handler.

    .. code-block:: python

        with LangGraphAdapter(graph):
            result = graph.invoke(state)

        async with LangGraphAdapter(graph):
            result = await graph.ainvoke(state)

    The adapter restores the original methods on exit, even if an exception
    is raised inside the ``with`` block.

    Args:
        graph: A compiled LangGraph graph (``CompiledStateGraph`` or
               ``CompiledGraph``).  The graph must expose the standard
               LangGraph/LangChain ``Runnable`` interface.

    Raises:
        ImportError: if ``langchain_core`` is not installed.
    """

    def __init__(self, graph: Any) -> None:
        self.graph = graph
        self._handler: Any = None
        self._originals: dict[str, Any] = {}
        self._patched: bool = False

    # -- context manager protocol ------------------------------------------

    def __enter__(self) -> "LangGraphAdapter":
        self._patch()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._unpatch()

    async def __aenter__(self) -> "LangGraphAdapter":
        self._patch()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._unpatch()

    # -- patching -----------------------------------------------------------

    def _patch(self) -> None:
        if self._patched:
            return

        HandlerClass = _build_handler_class()
        self._handler = HandlerClass()
        handler = self._handler
        graph = self.graph

        # Collect original methods (only patch those that exist on the graph).
        for method_name in ("invoke", "ainvoke", "stream", "astream"):
            original = getattr(graph, method_name, None)
            if original is not None:
                self._originals[method_name] = original

        # Patch sync invoke.
        if "invoke" in self._originals:
            original_invoke = self._originals["invoke"]

            def patched_invoke(input: Any, config: Any = None, **kwargs: Any) -> Any:
                return original_invoke(input, config=_inject_callbacks(config, handler), **kwargs)

            graph.invoke = patched_invoke

        # Patch async invoke.
        if "ainvoke" in self._originals:
            original_ainvoke = self._originals["ainvoke"]

            async def patched_ainvoke(input: Any, config: Any = None, **kwargs: Any) -> Any:
                return await original_ainvoke(
                    input, config=_inject_callbacks(config, handler), **kwargs
                )

            graph.ainvoke = patched_ainvoke

        # Patch sync stream.
        if "stream" in self._originals:
            original_stream = self._originals["stream"]

            def patched_stream(input: Any, config: Any = None, **kwargs: Any) -> Any:
                return original_stream(
                    input, config=_inject_callbacks(config, handler), **kwargs
                )

            graph.stream = patched_stream

        # Patch async stream.
        if "astream" in self._originals:
            original_astream = self._originals["astream"]

            async def patched_astream(input: Any, config: Any = None, **kwargs: Any) -> Any:
                async for chunk in original_astream(
                    input, config=_inject_callbacks(config, handler), **kwargs
                ):
                    yield chunk

            graph.astream = patched_astream

        self._patched = True

    def _unpatch(self) -> None:
        if not self._patched:
            return
        for method_name, original in self._originals.items():
            setattr(self.graph, method_name, original)
        self._originals.clear()
        self._patched = False
