"""Replay Engine — replays cassettes deterministically without API calls.

The replay engine takes a recorded cassette and feeds the recorded
responses back, allowing you to test agent logic without making
real LLM calls.

Usage:
    from evalcraft import replay

    # Replay from file
    run = replay("tests/cassettes/weather_agent.json")
    assert run.cassette.output_text == "It's sunny"

    # Replay with modifications
    engine = ReplayEngine("tests/cassettes/weather_agent.json")
    engine.override_tool_result("get_weather", {"temp": 72, "condition": "rainy"})
    run = engine.run()
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Callable, Collection

from evalcraft.core.models import (
    Cassette,
    Span,
    SpanKind,
    AgentRun,
)
from evalcraft.replay.network_guard import NetworkGuard


class ReplayEngine:
    """Replays a recorded cassette with optional modifications.

    Supports:
    - Exact replay (default)
    - Tool result overrides
    - LLM response overrides
    - Step-by-step iteration
    - Span filtering
    """

    def __init__(
        self,
        cassette: Cassette | str | Path,
        *,
        block_network: bool = True,
        network_allowlist: Collection[str] | None = None,
    ):
        if isinstance(cassette, (str, Path)):
            self.cassette = Cassette.load(cassette)
        else:
            self.cassette = copy.deepcopy(cassette)

        self._tool_overrides: dict[str, Any] = {}
        self._llm_overrides: dict[int, Any] = {}
        self._span_filter: Callable[[Span], bool] | None = None
        self._current_index: int = 0
        self._block_network: bool = block_network
        self._network_allowlist: Collection[str] = network_allowlist or []

    @property
    def spans(self) -> list[Span]:
        """Get the spans, optionally filtered."""
        if self._span_filter:
            return [s for s in self.cassette.spans if self._span_filter(s)]
        return self.cassette.spans

    def override_tool_result(self, tool_name: str, result: Any) -> ReplayEngine:
        """Override the result of a specific tool during replay.

        Args:
            tool_name: Name of the tool to override
            result: New result to return for this tool

        Returns:
            self for chaining
        """
        self._tool_overrides[tool_name] = result
        return self

    def override_llm_response(self, call_index: int, response: Any) -> ReplayEngine:
        """Override a specific LLM response by index.

        Args:
            call_index: 0-based index of the LLM call to override
            response: New response content

        Returns:
            self for chaining
        """
        self._llm_overrides[call_index] = response
        return self

    def filter_spans(self, predicate: Callable[[Span], bool]) -> ReplayEngine:
        """Filter spans during replay.

        Args:
            predicate: Function that returns True for spans to include

        Returns:
            self for chaining
        """
        self._span_filter = predicate
        return self

    def run(self) -> AgentRun:
        """Execute the full replay and return the result.

        If ``block_network`` is True (the default), all outgoing socket
        connections are blocked for the duration of the replay via a
        :class:`~evalcraft.replay.network_guard.NetworkGuard`.  Any
        attempt to open a real network connection will raise
        :class:`~evalcraft.replay.network_guard.ReplayNetworkViolation`.
        """
        guard: NetworkGuard | None = None
        if self._block_network:
            guard = NetworkGuard(allowlist=self._network_allowlist)
            guard.__enter__()

        try:
            return self._run_spans()
        finally:
            if guard is not None:
                guard.__exit__(None, None, None)

    def _run_spans(self) -> AgentRun:
        """Internal helper: iterate spans, apply overrides, and return AgentRun."""
        replayed_cassette = copy.deepcopy(self.cassette)
        replayed_spans = []
        llm_call_index = 0

        for span in self.spans:
            replayed_span = copy.deepcopy(span)

            # Apply tool overrides
            if (
                span.kind == SpanKind.TOOL_CALL
                and span.tool_name in self._tool_overrides
            ):
                replayed_span.tool_result = self._tool_overrides[span.tool_name]
                replayed_span.output = self._tool_overrides[span.tool_name]

            # Apply LLM overrides
            if span.kind in (SpanKind.LLM_REQUEST, SpanKind.LLM_RESPONSE):
                if llm_call_index in self._llm_overrides:
                    replayed_span.output = self._llm_overrides[llm_call_index]
                llm_call_index += 1

            replayed_spans.append(replayed_span)

        replayed_cassette.spans = replayed_spans
        replayed_cassette.compute_metrics()
        replayed_cassette.compute_fingerprint()

        return AgentRun(
            cassette=replayed_cassette,
            success=True,
            replayed=True,
        )

    def step(self) -> Span | None:
        """Step through the replay one span at a time.

        Returns the next span, or None if replay is complete.
        """
        spans = self.spans
        if self._current_index >= len(spans):
            return None

        span = copy.deepcopy(spans[self._current_index])

        # Apply overrides
        if span.kind == SpanKind.TOOL_CALL and span.tool_name in self._tool_overrides:
            span.tool_result = self._tool_overrides[span.tool_name]
            span.output = self._tool_overrides[span.tool_name]

        self._current_index += 1
        return span

    def reset(self) -> None:
        """Reset the step-by-step iterator."""
        self._current_index = 0

    def get_tool_calls(self) -> list[Span]:
        """Get all tool call spans from the cassette."""
        return [s for s in self.spans if s.kind == SpanKind.TOOL_CALL]

    def get_llm_calls(self) -> list[Span]:
        """Get all LLM call spans."""
        return [
            s for s in self.spans
            if s.kind in (SpanKind.LLM_REQUEST, SpanKind.LLM_RESPONSE)
        ]

    def get_tool_sequence(self) -> list[str]:
        """Get the ordered list of tool names called."""
        return [s.tool_name for s in self.get_tool_calls() if s.tool_name]

    def diff(self, other: Cassette | str | Path) -> ReplayDiff:
        """Compare this cassette with another and return differences."""
        if isinstance(other, (str, Path)):
            other = Cassette.load(other)

        return ReplayDiff.compute(self.cassette, other)


class ReplayDiff:
    """Differences between two cassette replays."""

    def __init__(self):
        self.tool_sequence_changed: bool = False
        self.output_changed: bool = False
        self.token_count_changed: bool = False
        self.cost_changed: bool = False
        self.span_count_changed: bool = False

        self.old_tool_sequence: list[str] = []
        self.new_tool_sequence: list[str] = []
        self.old_output: str = ""
        self.new_output: str = ""
        self.old_tokens: int = 0
        self.new_tokens: int = 0
        self.old_cost: float = 0.0
        self.new_cost: float = 0.0
        self.old_span_count: int = 0
        self.new_span_count: int = 0

    @property
    def has_changes(self) -> bool:
        return any([
            self.tool_sequence_changed,
            self.output_changed,
            self.token_count_changed,
            self.cost_changed,
            self.span_count_changed,
        ])

    @classmethod
    def compute(cls, old: Cassette, new: Cassette) -> ReplayDiff:
        diff = cls()

        diff.old_tool_sequence = old.get_tool_sequence()
        diff.new_tool_sequence = new.get_tool_sequence()
        diff.tool_sequence_changed = diff.old_tool_sequence != diff.new_tool_sequence

        diff.old_output = old.output_text
        diff.new_output = new.output_text
        diff.output_changed = diff.old_output != diff.new_output

        diff.old_tokens = old.total_tokens
        diff.new_tokens = new.total_tokens
        diff.token_count_changed = diff.old_tokens != diff.new_tokens

        diff.old_cost = old.total_cost_usd
        diff.new_cost = new.total_cost_usd
        diff.cost_changed = diff.old_cost != diff.new_cost

        diff.old_span_count = len(old.spans)
        diff.new_span_count = len(new.spans)
        diff.span_count_changed = diff.old_span_count != diff.new_span_count

        return diff

    def to_dict(self) -> dict:
        return {
            "has_changes": self.has_changes,
            "tool_sequence_changed": self.tool_sequence_changed,
            "output_changed": self.output_changed,
            "token_count_changed": self.token_count_changed,
            "cost_changed": self.cost_changed,
            "span_count_changed": self.span_count_changed,
            "old_tool_sequence": self.old_tool_sequence,
            "new_tool_sequence": self.new_tool_sequence,
            "old_output": self.old_output,
            "new_output": self.new_output,
            "old_tokens": self.old_tokens,
            "new_tokens": self.new_tokens,
            "old_cost": self.old_cost,
            "new_cost": self.new_cost,
        }

    def summary(self) -> str:
        """Human-readable summary of changes."""
        if not self.has_changes:
            return "No changes detected."

        parts = []
        if self.tool_sequence_changed:
            parts.append(
                f"Tool sequence: {self.old_tool_sequence} → {self.new_tool_sequence}"
            )
        if self.output_changed:
            parts.append("Output text changed")
        if self.token_count_changed:
            parts.append(f"Tokens: {self.old_tokens} → {self.new_tokens}")
        if self.cost_changed:
            parts.append(f"Cost: ${self.old_cost:.4f} → ${self.new_cost:.4f}")
        if self.span_count_changed:
            parts.append(f"Spans: {self.old_span_count} → {self.new_span_count}")

        return "\n".join(parts)


def replay(
    cassette_path: str | Path,
    tool_overrides: dict[str, Any] | None = None,
    *,
    block_network: bool = True,
    network_allowlist: Collection[str] | None = None,
) -> AgentRun:
    """Convenience function to replay a cassette file.

    Args:
        cassette_path: Path to the cassette JSON file
        tool_overrides: Optional dict of tool_name → new_result
        block_network: If True (default), block all outgoing network
            connections during replay via :class:`NetworkGuard`.
        network_allowlist: Hostnames/IPs that are still allowed to
            connect even when ``block_network`` is True.

    Returns:
        AgentRun with the replayed cassette
    """
    engine = ReplayEngine(
        cassette_path,
        block_network=block_network,
        network_allowlist=network_allowlist,
    )
    if tool_overrides:
        for tool_name, result in tool_overrides.items():
            engine.override_tool_result(tool_name, result)
    return engine.run()
