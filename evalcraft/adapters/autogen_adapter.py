"""AutoGen adapter — captures agent conversations into evalcraft spans.

Patches ``ConversableAgent`` class-level methods to automatically capture:

- Messages exchanged between agents (via ``receive``).
- LLM responses (via ``generate_oai_reply``).
- Function / tool call executions (via ``execute_function``).

Usage::

    from evalcraft.adapters import AutoGenAdapter
    from evalcraft import CaptureContext
    import autogen  # or: import pyautogen as autogen

    user_proxy = autogen.UserProxyAgent("user", ...)
    assistant = autogen.AssistantAgent("assistant", ...)

    with CaptureContext(name="autogen_run") as ctx:
        with AutoGenAdapter():
            user_proxy.initiate_chat(
                assistant,
                message="What is the capital of France?",
            )

    cassette = ctx.cassette
    print(cassette.get_tool_sequence())
    print(cassette.total_tokens)

The adapter patches the ``ConversableAgent`` *class* (not individual
instances) so all agents in the conversation are captured automatically,
including agents created before the adapter is entered.  Pass an optional
``agents`` list to the constructor to restrict patching to specific
instances instead.

The adapter is safe to use when no :class:`CaptureContext` is active — spans
are simply dropped.

Requirements:
    ``autogen`` (>= 0.2) or ``pyautogen`` (>= 0.2) must be installed.
"""

from __future__ import annotations

import json
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


def _extract_message_content(message: Any) -> str:
    """Extract readable text from an AutoGen message (str or dict)."""
    if isinstance(message, str):
        return message[:2000]
    if isinstance(message, dict):
        content = message.get("content")
        if content:
            return _safe_str(content)
        # Function / tool calls — produce a compact summary.
        tool_calls = message.get("tool_calls")
        if tool_calls:
            summaries = []
            for tc in tool_calls:
                fn = tc.get("function", {}) if isinstance(tc, dict) else {}
                name = fn.get("name", "unknown")
                args = fn.get("arguments", "")
                summaries.append(f"[call:{name}({args})]")
            return " ".join(summaries)
        # Function call (older OpenAI format).
        func = message.get("function_call")
        if func:
            name = func.get("name", "unknown") if isinstance(func, dict) else str(func)
            args = func.get("arguments", "") if isinstance(func, dict) else ""
            return f"[call:{name}({args})]"
    return _safe_str(message)


def _parse_func_args(arguments: Any) -> dict[str, Any] | None:
    """Parse a JSON-encoded arguments string into a dict."""
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
            if isinstance(parsed, dict):
                return parsed
            return {"input": _safe_str(parsed)}
        except (json.JSONDecodeError, ValueError):
            return {"input": arguments}
    return None


def _get_agent_model(agent: Any) -> str:
    """Best-effort extraction of the model name from an AutoGen agent config."""
    try:
        llm_config = getattr(agent, "llm_config", None)
        if isinstance(llm_config, dict):
            # Standard: {"model": "gpt-4o", ...}
            model = llm_config.get("model")
            if model:
                return str(model)
            # config_list: [{"model": "gpt-4o", ...}, ...]
            config_list = llm_config.get("config_list")
            if config_list and isinstance(config_list, list) and config_list:
                first = config_list[0]
                if isinstance(first, dict) and first.get("model"):
                    return str(first["model"])
    except Exception:
        pass
    return "unknown"


# ---------------------------------------------------------------------------
# Public adapter
# ---------------------------------------------------------------------------

class AutoGenAdapter:
    """Patches AutoGen's ``ConversableAgent`` to record all events as evalcraft spans.

    Patches three class-level methods on ``ConversableAgent`` so that every
    agent in the conversation is automatically instrumented:

    * ``receive`` — records each inter-agent message as an
      :attr:`~evalcraft.core.models.SpanKind.AGENT_STEP` span.
    * ``generate_oai_reply`` — records LLM responses as
      :attr:`~evalcraft.core.models.SpanKind.LLM_RESPONSE` spans.
    * ``execute_function`` — records function / tool calls as
      :attr:`~evalcraft.core.models.SpanKind.TOOL_CALL` spans.

    .. code-block:: python

        with AutoGenAdapter():
            user_proxy.initiate_chat(assistant, message="What's 2+2?")

        async with AutoGenAdapter():
            await user_proxy.a_initiate_chat(assistant, message="What's 2+2?")

    The adapter restores all patched methods on exit, even if an exception is
    raised inside the ``with`` block.

    Args:
        agents: Unused — kept for API symmetry with other adapters.  The
            adapter always patches the *class*, ensuring full coverage of
            multi-agent conversations regardless of how many agents are
            created.

    Raises:
        ImportError: if neither ``autogen`` nor ``pyautogen`` is installed.
    """

    def __init__(self, agents: list[Any] | None = None) -> None:
        # ``agents`` is accepted for interface symmetry but not required;
        # class-level patching captures all agents automatically.
        self._ConversableAgent: Any = None
        self._originals: dict[str, Any] = {}
        self._patched: bool = False

    # -- context manager protocol ------------------------------------------

    def __enter__(self) -> "AutoGenAdapter":
        self._patch()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._unpatch()

    async def __aenter__(self) -> "AutoGenAdapter":
        self._patch()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._unpatch()

    # -- patching -----------------------------------------------------------

    def _patch(self) -> None:
        if self._patched:
            return

        # Lazy import — support both package names.
        try:
            try:
                from autogen import ConversableAgent  # type: ignore[import]
            except ImportError:
                from pyautogen import ConversableAgent  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "The 'autogen' or 'pyautogen' package is required for AutoGenAdapter. "
                "Install it with: pip install 'evalcraft[autogen]'"
            ) from exc

        self._ConversableAgent = ConversableAgent
        adapter = self

        # ---- receive: captures all inter-agent messages -------------------
        original_receive = ConversableAgent.receive
        self._originals["receive"] = original_receive

        def patched_receive(
            self_agent: Any,
            message: Any,
            sender: Any,
            request_reply: Any = None,
            silent: bool = False,
            **kwargs: Any,
        ) -> Any:
            ctx = get_active_context()
            if ctx is not None:
                content = _extract_message_content(message)
                sender_name = getattr(sender, "name", _safe_str(sender))
                receiver_name = getattr(self_agent, "name", "agent")
                span = Span(
                    kind=SpanKind.AGENT_STEP,
                    name=f"message:{sender_name}->{receiver_name}",
                    input=content,
                    metadata={
                        "sender": sender_name,
                        "receiver": receiver_name,
                        "silent": silent,
                    },
                )
                ctx.record_span(span)
            return original_receive(
                self_agent,
                message,
                sender,
                request_reply=request_reply,
                silent=silent,
                **kwargs,
            )

        ConversableAgent.receive = patched_receive  # type: ignore[method-assign]

        # ---- generate_oai_reply: captures LLM responses ------------------
        original_generate_oai_reply = getattr(ConversableAgent, "generate_oai_reply", None)
        if original_generate_oai_reply is not None:
            self._originals["generate_oai_reply"] = original_generate_oai_reply

            def patched_generate_oai_reply(
                self_agent: Any,
                messages: Any = None,
                sender: Any = None,
                config: Any = None,
                **kwargs: Any,
            ) -> Any:
                start = time.monotonic()
                try:
                    result = original_generate_oai_reply(
                        self_agent, messages, sender=sender, config=config, **kwargs
                    )
                except Exception as exc:
                    duration_ms = (time.monotonic() - start) * 1000
                    ctx = get_active_context()
                    if ctx is not None:
                        span = Span(
                            kind=SpanKind.LLM_RESPONSE,
                            name="llm:autogen",
                            duration_ms=duration_ms,
                            error=str(exc),
                        )
                        ctx.record_span(span)
                    raise
                duration_ms = (time.monotonic() - start) * 1000
                ctx = get_active_context()
                if ctx is not None:
                    # result is (True, reply_content) or (False, None)
                    replied = isinstance(result, tuple) and result[0]
                    reply = result[1] if isinstance(result, tuple) else None
                    if replied and reply is not None:
                        model = _get_agent_model(self_agent)
                        input_str = ""
                        if isinstance(messages, list) and messages:
                            input_str = _extract_message_content(messages[-1])
                        ctx.record_llm_call(
                            model=model,
                            input=input_str,
                            output=_safe_str(reply),
                            duration_ms=duration_ms,
                        )
                return result

            ConversableAgent.generate_oai_reply = patched_generate_oai_reply  # type: ignore[method-assign]

        # ---- execute_function: captures tool / function calls ------------
        original_execute_function = getattr(ConversableAgent, "execute_function", None)
        if original_execute_function is not None:
            self._originals["execute_function"] = original_execute_function

            def patched_execute_function(
                self_agent: Any,
                func_call: Any,
                verbose: bool = False,
                **kwargs: Any,
            ) -> Any:
                start = time.monotonic()
                # Extract function name / args before calling.
                if isinstance(func_call, dict):
                    func_name = _safe_str(func_call.get("name", "unknown"))
                    func_args = _parse_func_args(func_call.get("arguments"))
                else:
                    func_name = _safe_str(getattr(func_call, "name", "unknown"))
                    func_args = None

                try:
                    result = original_execute_function(
                        self_agent, func_call, verbose=verbose, **kwargs
                    )
                except Exception as exc:
                    duration_ms = (time.monotonic() - start) * 1000
                    ctx = get_active_context()
                    if ctx is not None:
                        ctx.record_tool_call(
                            tool_name=func_name,
                            args=func_args,
                            result=None,
                            duration_ms=duration_ms,
                            error=str(exc),
                        )
                    raise
                duration_ms = (time.monotonic() - start) * 1000
                ctx = get_active_context()
                if ctx is not None:
                    # result is (is_success: bool, output_dict: dict)
                    output_dict = result[1] if isinstance(result, tuple) else result
                    output_str = (
                        _safe_str(output_dict.get("content", output_dict))
                        if isinstance(output_dict, dict)
                        else _safe_str(output_dict)
                    )
                    ctx.record_tool_call(
                        tool_name=func_name,
                        args=func_args,
                        result=output_str,
                        duration_ms=duration_ms,
                    )
                return result

            ConversableAgent.execute_function = patched_execute_function  # type: ignore[method-assign]

        self._patched = True

    def _unpatch(self) -> None:
        if not self._patched or self._ConversableAgent is None:
            return
        for method_name, original in self._originals.items():
            setattr(self._ConversableAgent, method_name, original)
        self._originals.clear()
        self._patched = False
