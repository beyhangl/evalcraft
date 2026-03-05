"""CrewAI adapter — captures crew runs into evalcraft spans.

Instruments a CrewAI ``Crew`` by:

1. Patching ``kickoff()`` and ``kickoff_async()`` on the *crew instance* to
   record overall execution duration and final output.
2. Injecting a ``step_callback`` to capture each agent action (tool calls,
   delegation steps, and finish events).
3. Injecting a ``task_callback`` to capture task completions, including
   the responsible agent — enabling tracing of inter-agent delegation.

Usage::

    from evalcraft.adapters import CrewAIAdapter
    from evalcraft import CaptureContext

    # crew is a crewai.Crew instance
    with CaptureContext(name="crew_run") as ctx:
        with CrewAIAdapter(crew):
            result = crew.kickoff(inputs={"topic": "AI safety"})

    cassette = ctx.cassette
    print(cassette.get_tool_sequence())
    print(cassette.total_tokens)

    # Async usage
    async with CaptureContext(name="crew_run_async") as ctx:
        async with CrewAIAdapter(crew):
            result = await crew.kickoff_async(inputs={"topic": "AI safety"})

The adapter is safe to use when no :class:`CaptureContext` is active — spans
are simply dropped.

Requirements:
    ``crewai>=0.28`` must be installed.

Notes:
    - The adapter patches the *instance* (not the class), so multiple crews
      can be wrapped independently.
    - Existing ``step_callback`` and ``task_callback`` values on the crew are
      preserved and called after the adapter's own recording.
    - Nested ``CrewAIAdapter`` contexts on the *same* crew are not supported.
    - To capture LLM token usage, combine with :class:`OpenAIAdapter` (or the
      appropriate LLM-level adapter) inside the same :class:`CaptureContext`.
"""

from __future__ import annotations

import time
from typing import Any

from evalcraft.capture.recorder import get_active_context
from evalcraft.core.models import Span, SpanKind


# ---------------------------------------------------------------------------
# Step / task extraction helpers
# ---------------------------------------------------------------------------

def _safe_str(obj: Any, max_len: int = 2000) -> str:
    """Convert *obj* to string, truncated to *max_len* characters."""
    try:
        text = str(obj)
    except Exception:
        return "<unserializable>"
    return text[:max_len] if len(text) > max_len else text


def _extract_step_info(
    step: Any,
) -> tuple[str | None, dict[str, Any] | None, str | None]:
    """Return ``(tool_name, tool_args, output)`` from a CrewAI step.

    CrewAI's ``step_callback`` receives values that vary by version:

    * **Tuple ``(AgentAction, observation)``** — LangChain/older-CrewAI
      format.  ``AgentAction`` has ``.tool``, ``.tool_input``, ``.log``.
    * **``AgentAction``** — a single action object, without the observation.
    * **``AgentFinish``** — has ``.return_values`` (dict) and ``.log``.
    * **Any other object** — serialised with ``str()``.

    Returns ``(None, None, output)`` when no tool name is present (e.g.
    for ``AgentFinish`` steps).
    """
    # Tuple format: (AgentAction, observation_str)
    if isinstance(step, tuple) and len(step) == 2:
        action, observation = step
        tool = getattr(action, "tool", None)
        if tool:
            tool_input = getattr(action, "tool_input", None)
            if isinstance(tool_input, str):
                tool_input = {"input": tool_input}
            elif not isinstance(tool_input, dict):
                tool_input = {"input": _safe_str(tool_input)}
            return str(tool), tool_input, _safe_str(observation)
        # Tuple but no tool — treat both elements as output.
        return None, None, _safe_str(step)

    # AgentAction (tool call without separate observation)
    tool = getattr(step, "tool", None)
    if tool:
        tool_input = getattr(step, "tool_input", None)
        if isinstance(tool_input, str):
            tool_input = {"input": tool_input}
        elif tool_input is not None and not isinstance(tool_input, dict):
            tool_input = {"input": _safe_str(tool_input)}
        log = getattr(step, "log", None)
        return str(tool), tool_input, _safe_str(log) if log is not None else None

    # AgentFinish — no tool, just a final answer
    return_values = getattr(step, "return_values", None)
    if return_values is not None:
        if isinstance(return_values, dict):
            output = return_values.get("output") or _safe_str(return_values)
        else:
            output = _safe_str(return_values)
        return None, None, str(output)

    # Unknown step type
    return None, None, _safe_str(step)


def _extract_task_info(task_output: Any) -> tuple[str, str, str]:
    """Return ``(description, raw_output, agent_role)`` from a ``TaskOutput``.

    ``TaskOutput`` (crewai>=0.28) has:

    * ``.description`` — the original task description.
    * ``.raw``         — the raw string output produced by the agent.
    * ``.agent``       — role of the agent that completed the task.
    * ``.summary``     — optional short summary.
    """
    description = _safe_str(getattr(task_output, "description", "") or "")
    raw = _safe_str(getattr(task_output, "raw", "") or str(task_output))
    agent_role = _safe_str(getattr(task_output, "agent", "") or "")
    return description, raw, agent_role


# ---------------------------------------------------------------------------
# Module-level helpers used inside patched kickoff closures
# ---------------------------------------------------------------------------

def _record_kickoff_success(ctx: Any, result: Any, duration_ms: float) -> None:
    """Record a successful ``crew.kickoff()`` call as a span + output."""
    if ctx is None:
        return
    output_str = _safe_str(result)
    span = Span(
        kind=SpanKind.AGENT_STEP,
        name="crew:kickoff",
        output=output_str,
        duration_ms=duration_ms,
    )
    ctx.record_span(span)
    ctx.record_output(output_str)


def _record_kickoff_error(ctx: Any, duration_ms: float, exc: Exception) -> None:
    """Record a failed ``crew.kickoff()`` call as an error span."""
    if ctx is None:
        return
    span = Span(
        kind=SpanKind.AGENT_STEP,
        name="crew:kickoff:error",
        duration_ms=duration_ms,
        error=str(exc),
    )
    ctx.record_span(span)


# ---------------------------------------------------------------------------
# Public adapter
# ---------------------------------------------------------------------------

class CrewAIAdapter:
    """Instruments a CrewAI ``Crew`` to record all events as evalcraft spans.

    Patches ``kickoff()`` and ``kickoff_async()`` on the *crew instance* and
    injects ``step_callback`` / ``task_callback`` hooks so that tool calls,
    delegation events, and task completions are captured automatically.

    .. code-block:: python

        with CrewAIAdapter(crew):
            result = crew.kickoff(inputs={"topic": "AI"})

        async with CrewAIAdapter(crew):
            result = await crew.kickoff_async(inputs={"topic": "AI"})

    The adapter restores all patched attributes on exit, even if an exception
    is raised inside the ``with`` block.

    Args:
        crew: A :class:`crewai.Crew` instance.

    Raises:
        ImportError: if ``crewai`` is not installed.
    """

    def __init__(self, crew: Any) -> None:
        self.crew = crew
        self._patched: bool = False
        self._originals: dict[str, Any] = {}
        self._original_step_callback: Any = None
        self._original_task_callback: Any = None

    # -- context manager protocol ------------------------------------------

    def __enter__(self) -> "CrewAIAdapter":
        self._patch()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._unpatch()

    async def __aenter__(self) -> "CrewAIAdapter":
        self._patch()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._unpatch()

    # -- patching -----------------------------------------------------------

    def _patch(self) -> None:
        if self._patched:
            return

        # Lazy import — validate crewai is available before patching anything.
        try:
            import crewai  # noqa: F401  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "The 'crewai' package is required for CrewAIAdapter. "
                "Install it with: pip install 'evalcraft[crewai]'"
            ) from exc

        crew = self.crew
        adapter = self

        # --- Save and inject step / task callbacks ---------------------------
        self._original_step_callback = getattr(crew, "step_callback", None)
        self._original_task_callback = getattr(crew, "task_callback", None)

        original_step_cb = self._original_step_callback
        original_task_cb = self._original_task_callback

        def _step_callback(step: Any) -> None:
            adapter._record_step(step)
            if original_step_cb is not None:
                original_step_cb(step)

        def _task_callback(task_output: Any) -> None:
            adapter._record_task(task_output)
            if original_task_cb is not None:
                original_task_cb(task_output)

        crew.step_callback = _step_callback
        crew.task_callback = _task_callback

        # --- Patch kickoff / kickoff_async on the instance -------------------
        for method_name in ("kickoff", "kickoff_async"):
            original = getattr(crew, method_name, None)
            if original is not None:
                self._originals[method_name] = original

        if "kickoff" in self._originals:
            original_kickoff = self._originals["kickoff"]

            def patched_kickoff(inputs: Any = None, **kwargs: Any) -> Any:
                start = time.monotonic()
                ctx = get_active_context()
                try:
                    result = original_kickoff(inputs=inputs, **kwargs)
                except Exception as exc:
                    duration_ms = (time.monotonic() - start) * 1000
                    _record_kickoff_error(ctx, duration_ms, exc)
                    raise
                duration_ms = (time.monotonic() - start) * 1000
                _record_kickoff_success(ctx, result, duration_ms)
                return result

            crew.kickoff = patched_kickoff

        if "kickoff_async" in self._originals:
            original_kickoff_async = self._originals["kickoff_async"]

            async def patched_kickoff_async(inputs: Any = None, **kwargs: Any) -> Any:
                start = time.monotonic()
                ctx = get_active_context()
                try:
                    result = await original_kickoff_async(inputs=inputs, **kwargs)
                except Exception as exc:
                    duration_ms = (time.monotonic() - start) * 1000
                    _record_kickoff_error(ctx, duration_ms, exc)
                    raise
                duration_ms = (time.monotonic() - start) * 1000
                _record_kickoff_success(ctx, result, duration_ms)
                return result

            crew.kickoff_async = patched_kickoff_async

        self._patched = True

    def _unpatch(self) -> None:
        if not self._patched:
            return
        crew = self.crew
        # Restore original callbacks (may be None).
        crew.step_callback = self._original_step_callback
        crew.task_callback = self._original_task_callback
        # Restore kickoff methods.
        for method_name, original in self._originals.items():
            setattr(crew, method_name, original)
        self._originals.clear()
        self._patched = False

    # -- recording helpers --------------------------------------------------

    def _record_step(self, step: Any) -> None:
        """Record a single agent step received from ``step_callback``."""
        ctx = get_active_context()
        if ctx is None:
            return

        tool_name, tool_args, output = _extract_step_info(step)

        if tool_name:
            # Delegation is surfaced as "Delegate work to coworker" tool calls;
            # no special handling needed — they appear naturally in the sequence.
            ctx.record_tool_call(
                tool_name=tool_name,
                args=tool_args,
                result=output,
            )
        else:
            # AgentFinish or unrecognised step type.
            span = Span(
                kind=SpanKind.AGENT_STEP,
                name="agent:finish",
                output=output,
            )
            ctx.record_span(span)

    def _record_task(self, task_output: Any) -> None:
        """Record a completed task received from ``task_callback``."""
        ctx = get_active_context()
        if ctx is None:
            return

        description, raw, agent_role = _extract_task_info(task_output)
        # Truncate long descriptions to keep span names readable.
        name = f"task:{description[:60]}" if description else "task:complete"
        span = Span(
            kind=SpanKind.AGENT_STEP,
            name=name,
            input=description or None,
            output=raw,
            metadata={"agent": agent_role} if agent_role else {},
        )
        ctx.record_span(span)
