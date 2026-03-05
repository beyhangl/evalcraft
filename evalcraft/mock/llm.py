"""MockLLM — deterministic LLM responses for testing.

Usage:
    from evalcraft import MockLLM

    mock = MockLLM()
    mock.add_response("What's 2+2?", "4")
    mock.add_response("*", "I don't know")  # wildcard

    result = mock.complete("What's 2+2?")
    assert result.content == "4"
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from evalcraft.capture.recorder import get_active_context
from evalcraft.core.models import Span, SpanKind, TokenUsage


@dataclass
class MockResponse:
    """A mock LLM response."""
    content: str = ""
    model: str = "mock-llm"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    finish_reason: str = "stop"
    tool_calls: list[dict] | None = None
    metadata: dict = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class MockLLM:
    """A deterministic mock LLM for testing agent logic without API calls.

    Supports:
    - Exact match responses
    - Pattern/regex match responses
    - Wildcard fallback
    - Sequential responses (different answer each call)
    - Tool call simulation
    - Custom response functions
    - Automatic recording to active capture context
    """

    def __init__(self, model: str = "mock-llm", default_response: str = ""):
        self.model = model
        self.default_response = default_response
        self._exact_responses: dict[str, list[MockResponse]] = {}
        self._pattern_responses: list[tuple[re.Pattern, list[MockResponse]]] = []
        self._wildcard_responses: list[MockResponse] = []
        self._response_fn: Callable[[str], MockResponse] | None = None
        self._call_history: list[dict] = []
        self._call_count: int = 0

    def add_response(
        self,
        prompt: str,
        content: str,
        prompt_tokens: int = 10,
        completion_tokens: int = 20,
        tool_calls: list[dict] | None = None,
    ) -> MockLLM:
        """Add a response for a specific prompt.

        Args:
            prompt: Exact prompt to match, or "*" for wildcard
            content: Response content
            prompt_tokens: Simulated prompt tokens
            completion_tokens: Simulated completion tokens
            tool_calls: Optional tool calls in the response

        Returns:
            self for chaining
        """
        response = MockResponse(
            content=content,
            model=self.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            tool_calls=tool_calls,
        )

        if prompt == "*":
            self._wildcard_responses.append(response)
        else:
            if prompt not in self._exact_responses:
                self._exact_responses[prompt] = []
            self._exact_responses[prompt].append(response)

        return self

    def add_pattern_response(
        self,
        pattern: str,
        content: str,
        prompt_tokens: int = 10,
        completion_tokens: int = 20,
    ) -> MockLLM:
        """Add a response matched by regex pattern.

        Args:
            pattern: Regex pattern to match
            content: Response content
        """
        response = MockResponse(
            content=content,
            model=self.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        self._pattern_responses.append((re.compile(pattern, re.IGNORECASE), [response]))
        return self

    def add_sequential_responses(
        self, prompt: str, contents: list[str]
    ) -> MockLLM:
        """Add multiple responses that are returned sequentially.

        Args:
            prompt: Prompt to match
            contents: List of response contents, returned in order
        """
        responses = [
            MockResponse(content=c, model=self.model, prompt_tokens=10, completion_tokens=20)
            for c in contents
        ]
        if prompt == "*":
            self._wildcard_responses.extend(responses)
        else:
            self._exact_responses[prompt] = responses
        return self

    def set_response_fn(self, fn: Callable[[str], MockResponse]) -> MockLLM:
        """Set a custom function to generate responses.

        Args:
            fn: Function that takes a prompt string and returns MockResponse
        """
        self._response_fn = fn
        return self

    def complete(self, prompt: str, **kwargs) -> MockResponse:
        """Get a mock completion for the given prompt.

        Records the call to the active capture context if one exists.
        """
        start = time.time()
        response = self._resolve_response(prompt)
        duration_ms = (time.time() - start) * 1000

        # Record in call history
        self._call_history.append({
            "prompt": prompt,
            "response": response.content,
            "kwargs": kwargs,
        })
        self._call_count += 1

        # Record to active capture context
        ctx = get_active_context()
        if ctx:
            ctx.record_llm_call(
                model=self.model,
                input=prompt,
                output=response.content,
                duration_ms=duration_ms,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
            )

        return response

    def _resolve_response(self, prompt: str) -> MockResponse:
        """Find the best matching response for a prompt."""
        # Custom function takes priority
        if self._response_fn:
            return self._response_fn(prompt)

        # Exact match
        if prompt in self._exact_responses:
            responses = self._exact_responses[prompt]
            # Sequential: use next available, or last if exhausted
            idx = min(self._call_count, len(responses) - 1)
            return responses[idx]

        # Pattern match
        for pattern, responses in self._pattern_responses:
            if pattern.search(prompt):
                idx = min(self._call_count, len(responses) - 1)
                return responses[idx]

        # Wildcard
        if self._wildcard_responses:
            idx = min(self._call_count, len(self._wildcard_responses) - 1)
            return self._wildcard_responses[idx]

        # Default
        return MockResponse(
            content=self.default_response,
            model=self.model,
            prompt_tokens=10,
            completion_tokens=5,
        )

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def call_history(self) -> list[dict]:
        return self._call_history

    def reset(self) -> None:
        """Reset call history and count."""
        self._call_history.clear()
        self._call_count = 0

    def assert_called(self, times: int | None = None) -> None:
        """Assert the mock was called, optionally a specific number of times."""
        if self._call_count == 0:
            raise AssertionError("MockLLM was never called")
        if times is not None and self._call_count != times:
            raise AssertionError(
                f"MockLLM was called {self._call_count} times, expected {times}"
            )

    def assert_called_with(self, prompt: str) -> None:
        """Assert the mock was called with a specific prompt."""
        prompts = [c["prompt"] for c in self._call_history]
        if prompt not in prompts:
            raise AssertionError(
                f"MockLLM was never called with prompt: {prompt!r}\n"
                f"Actual prompts: {prompts}"
            )
