"""MockTool — deterministic tool responses for testing.

Usage:
    from evalcraft import MockTool

    search = MockTool("web_search")
    search.returns({"results": [{"title": "Python", "url": "..."}]})

    result = search.call(query="Python tutorial")
    assert result["results"][0]["title"] == "Python"
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from evalcraft.capture.recorder import get_active_context
from evalcraft.core.models import Span, SpanKind


class MockTool:
    """A deterministic mock tool for testing agent tool interactions.

    Supports:
    - Static return values
    - Dynamic return based on args
    - Error simulation
    - Call tracking
    - Sequential returns
    """

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self._return_value: Any = None
        self._return_fn: Callable[..., Any] | None = None
        self._sequential_returns: list[Any] = []
        self._error: str | None = None
        self._error_after: int | None = None
        self._call_history: list[dict] = []
        self._call_count: int = 0
        self._latency_ms: float = 0.0

    def returns(self, value: Any) -> MockTool:
        """Set a static return value.

        Args:
            value: The value to return when called

        Returns:
            self for chaining
        """
        self._return_value = value
        return self

    def returns_fn(self, fn: Callable[..., Any]) -> MockTool:
        """Set a dynamic return function.

        Args:
            fn: Function that receives the tool args and returns a result
        """
        self._return_fn = fn
        return self

    def returns_sequence(self, values: list[Any]) -> MockTool:
        """Set sequential return values.

        Args:
            values: List of values, returned in order on successive calls
        """
        self._sequential_returns = values
        return self

    def raises(self, error: str) -> MockTool:
        """Simulate a tool error.

        Args:
            error: Error message
        """
        self._error = error
        return self

    def raises_after(self, n_calls: int, error: str) -> MockTool:
        """Simulate a tool error after N successful calls.

        Args:
            n_calls: Number of successful calls before error
            error: Error message
        """
        self._error_after = n_calls
        self._error = error
        return self

    def with_latency(self, ms: float) -> MockTool:
        """Simulate tool latency.

        Args:
            ms: Latency in milliseconds
        """
        self._latency_ms = ms
        return self

    def call(self, **kwargs) -> Any:
        """Execute the mock tool.

        Records the call to the active capture context if one exists.
        """
        start = time.time()

        # Simulate latency
        if self._latency_ms > 0:
            time.sleep(self._latency_ms / 1000)

        # Check for error conditions
        error = None
        if self._error_after is not None and self._call_count >= self._error_after:
            error = self._error
        elif self._error and self._error_after is None:
            error = self._error

        # Resolve result
        result = None
        if error:
            result = None
        elif self._return_fn:
            result = self._return_fn(**kwargs)
        elif self._sequential_returns:
            idx = min(self._call_count, len(self._sequential_returns) - 1)
            result = self._sequential_returns[idx]
        else:
            result = self._return_value

        duration_ms = (time.time() - start) * 1000

        # Track call
        self._call_history.append({
            "args": kwargs,
            "result": result,
            "error": error,
        })
        self._call_count += 1

        # Record to active capture context
        ctx = get_active_context()
        if ctx:
            ctx.record_tool_call(
                tool_name=self.name,
                args=kwargs,
                result=result,
                duration_ms=duration_ms,
                error=error,
            )

        if error:
            raise ToolError(error)

        return result

    def __call__(self, **kwargs) -> Any:
        """Allow calling the mock tool directly."""
        return self.call(**kwargs)

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def call_history(self) -> list[dict]:
        return self._call_history

    @property
    def last_call(self) -> dict | None:
        return self._call_history[-1] if self._call_history else None

    def reset(self) -> None:
        """Reset call history and count."""
        self._call_history.clear()
        self._call_count = 0

    def assert_called(self, times: int | None = None) -> None:
        """Assert the tool was called, optionally a specific number of times."""
        if self._call_count == 0:
            raise AssertionError(f"MockTool '{self.name}' was never called")
        if times is not None and self._call_count != times:
            raise AssertionError(
                f"MockTool '{self.name}' was called {self._call_count} times, expected {times}"
            )

    def assert_called_with(self, **expected_kwargs) -> None:
        """Assert the tool was called with specific arguments."""
        for call in self._call_history:
            if all(
                call["args"].get(k) == v for k, v in expected_kwargs.items()
            ):
                return
        raise AssertionError(
            f"MockTool '{self.name}' was never called with args: {expected_kwargs}\n"
            f"Actual calls: {[c['args'] for c in self._call_history]}"
        )

    def assert_not_called(self) -> None:
        """Assert the tool was never called."""
        if self._call_count > 0:
            raise AssertionError(
                f"MockTool '{self.name}' was called {self._call_count} times, expected 0"
            )


class ToolError(Exception):
    """Raised when a mock tool simulates an error."""
    pass
