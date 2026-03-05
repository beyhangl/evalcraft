"""Capture SDK — records agent runs into cassettes.

Usage:
    from evalcraft import capture

    # As decorator
    @capture(name="my_agent_test")
    async def test_my_agent():
        agent.run("What's the weather?")

    # As context manager
    async with CaptureContext(name="my_test") as ctx:
        agent.run("What's the weather?")
        cassette = ctx.cassette
"""

from __future__ import annotations

import asyncio
import contextvars
import functools
import time
from contextlib import contextmanager, asynccontextmanager
from pathlib import Path
from typing import Any, Callable

from evalcraft.core.models import Cassette, Span, SpanKind, TokenUsage


# Context variable to track the active capture session
_active_context: contextvars.ContextVar[CaptureContext | None] = contextvars.ContextVar(
    "_active_context", default=None
)


def get_active_context() -> CaptureContext | None:
    """Get the currently active capture context, if any."""
    return _active_context.get()


class CaptureContext:
    """Manages a capture session that records spans into a cassette.

    Can be used as both sync and async context manager.

    Args:
        name: Cassette name.
        agent_name: Agent tag.
        framework: Framework tag.
        save_path: If set, save cassette to this path on exit.
        metadata: Extra metadata to attach to the cassette.
        cloud: If ``True``, auto-upload the cassette to the Evalcraft
            dashboard on exit.  Requires ``EVALCRAFT_API_KEY`` env var or
            ``~/.evalcraft/config.json``.  Can also be an
            ``EvalcraftCloud`` instance for custom config.
        redact: If ``True``, automatically redact PII/secrets from the
            cassette using the default :class:`~evalcraft.sanitize.redactor.CassetteRedactor`
            (MASK mode, all built-in patterns) before saving or uploading.
            Can also be a :class:`~evalcraft.sanitize.redactor.CassetteRedactor`
            instance for custom redaction configuration.
    """

    def __init__(
        self,
        name: str = "",
        agent_name: str = "",
        framework: str = "",
        save_path: str | Path | None = None,
        metadata: dict | None = None,
        cloud: bool | Any = False,
        redact: bool | Any = False,
    ):
        self.cassette = Cassette(
            name=name,
            agent_name=agent_name,
            framework=framework,
            metadata=metadata or {},
        )
        self.save_path = Path(save_path) if save_path else None
        self._cloud = cloud
        self._redact = redact
        self._token: contextvars.Token | None = None
        self._start_time: float = 0.0

    def __enter__(self) -> CaptureContext:
        self._start_time = time.time()
        self._token = _active_context.set(self)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self._finalize()
        if self._token is not None:
            _active_context.reset(self._token)
        return None

    async def __aenter__(self) -> CaptureContext:
        self._start_time = time.time()
        self._token = _active_context.set(self)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self._finalize()
        if self._token is not None:
            _active_context.reset(self._token)
        return None

    def _finalize(self) -> None:
        """Finalize the cassette — compute metrics, optionally redact, save, or upload."""
        self.cassette.total_duration_ms = (time.time() - self._start_time) * 1000
        self.cassette.compute_metrics()
        self.cassette.compute_fingerprint()
        if self._redact is not False and self._redact is not None:
            self._auto_redact()
        if self.save_path:
            self.cassette.save(self.save_path)
        if self._cloud is not False and self._cloud is not None:
            self._auto_upload()

    def _auto_redact(self) -> None:
        """Redact PII/secrets from the cassette in-place (best-effort, never raises)."""
        import logging
        log = logging.getLogger(__name__)
        try:
            from evalcraft.sanitize.redactor import CassetteRedactor
            redactor: CassetteRedactor
            if hasattr(self._redact, "redact"):
                redactor = self._redact
            else:
                redactor = CassetteRedactor()
            self.cassette = redactor.redact(self.cassette)
            log.debug("Auto-redacted cassette %s", self.cassette.id)
        except Exception as exc:
            log.warning("Auto-redact failed: %s", exc)

    def _auto_upload(self) -> None:
        """Upload the cassette to the cloud dashboard (best-effort, never raises)."""
        import logging
        log = logging.getLogger(__name__)
        try:
            from evalcraft.cloud.client import EvalcraftCloud, CloudUploadError
            client: EvalcraftCloud
            if hasattr(self._cloud, "upload"):
                client = self._cloud
            else:
                client = EvalcraftCloud()
            client.upload(self.cassette)
            log.debug("Auto-uploaded cassette %s to cloud", self.cassette.id)
        except Exception as exc:
            log.warning("Cloud auto-upload failed (cassette queued if possible): %s", exc)

    def record_span(self, span: Span) -> Span:
        """Record a span in the current cassette."""
        self.cassette.add_span(span)
        return span

    def record_llm_call(
        self,
        model: str,
        input: Any,
        output: Any,
        duration_ms: float = 0.0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost_usd: float | None = None,
        metadata: dict | None = None,
    ) -> Span:
        """Convenience method to record an LLM call."""
        span = Span(
            kind=SpanKind.LLM_RESPONSE,
            name=f"llm:{model}",
            duration_ms=duration_ms,
            input=input,
            output=output,
            model=model,
            token_usage=TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
            cost_usd=cost_usd,
            metadata=metadata or {},
        )
        return self.record_span(span)

    def record_tool_call(
        self,
        tool_name: str,
        args: dict | None = None,
        result: Any = None,
        duration_ms: float = 0.0,
        error: str | None = None,
        metadata: dict | None = None,
    ) -> Span:
        """Convenience method to record a tool call."""
        span = Span(
            kind=SpanKind.TOOL_CALL,
            name=f"tool:{tool_name}",
            duration_ms=duration_ms,
            tool_name=tool_name,
            tool_args=args,
            tool_result=result,
            error=error,
            metadata=metadata or {},
        )
        return self.record_span(span)

    def record_input(self, text: str) -> Span:
        """Record the user input to the agent."""
        self.cassette.input_text = text
        span = Span(
            kind=SpanKind.USER_INPUT,
            name="user_input",
            input=text,
        )
        return self.record_span(span)

    def record_output(self, text: str) -> Span:
        """Record the agent's final output."""
        self.cassette.output_text = text
        span = Span(
            kind=SpanKind.AGENT_OUTPUT,
            name="agent_output",
            output=text,
        )
        return self.record_span(span)


def capture(
    name: str = "",
    agent_name: str = "",
    framework: str = "",
    save_path: str | Path | None = None,
    metadata: dict | None = None,
    cloud: bool | Any = False,
    redact: bool | Any = False,
) -> Callable:
    """Decorator to capture an agent run into a cassette.

    Usage:
        @capture(name="weather_agent_test")
        def test_agent():
            result = my_agent.run("What's the weather?")
            return result

        # Auto-upload to cloud dashboard on exit:
        @capture(name="weather_agent_test", cloud=True)
        def test_agent():
            ...

        # Auto-redact PII/secrets on exit:
        @capture(name="weather_agent_test", redact=True)
        def test_agent():
            ...

        # The cassette is available via get_active_context()
    """
    def decorator(func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                ctx = CaptureContext(
                    name=name or func.__name__,
                    agent_name=agent_name,
                    framework=framework,
                    save_path=save_path,
                    metadata=metadata,
                    cloud=cloud,
                    redact=redact,
                )
                async with ctx:
                    result = await func(*args, **kwargs)
                return result
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                ctx = CaptureContext(
                    name=name or func.__name__,
                    agent_name=agent_name,
                    framework=framework,
                    save_path=save_path,
                    metadata=metadata,
                    cloud=cloud,
                    redact=redact,
                )
                with ctx:
                    result = func(*args, **kwargs)
                return result
            return sync_wrapper
    return decorator


def record_span(span: Span) -> Span | None:
    """Record a span in the currently active capture context.

    Returns the span if a context is active, None otherwise.
    This is the low-level API used by framework adapters.
    """
    ctx = get_active_context()
    if ctx is not None:
        return ctx.record_span(span)
    return None


def record_llm_call(**kwargs) -> Span | None:
    """Record an LLM call in the active context. See CaptureContext.record_llm_call."""
    ctx = get_active_context()
    if ctx is not None:
        return ctx.record_llm_call(**kwargs)
    return None


def record_tool_call(**kwargs) -> Span | None:
    """Record a tool call in the active context. See CaptureContext.record_tool_call."""
    ctx = get_active_context()
    if ctx is not None:
        return ctx.record_tool_call(**kwargs)
    return None
