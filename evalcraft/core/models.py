"""Core data models for Evalcraft.

Defines the cassette format — the fundamental recording unit that captures
every LLM call, tool use, and decision an agent makes.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any


class SpanKind(str, Enum):
    """Type of recorded span."""
    LLM_REQUEST = "llm_request"
    LLM_RESPONSE = "llm_response"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    AGENT_STEP = "agent_step"
    USER_INPUT = "user_input"
    AGENT_OUTPUT = "agent_output"


@dataclass
class TokenUsage:
    """Token usage for an LLM call."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def to_dict(self) -> dict:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }

    @classmethod
    def from_dict(cls, data: dict) -> TokenUsage:
        return cls(
            prompt_tokens=data.get("prompt_tokens", 0),
            completion_tokens=data.get("completion_tokens", 0),
            total_tokens=data.get("total_tokens", 0),
        )


@dataclass
class Span:
    """A single recorded event in an agent run.

    Spans are the atomic unit of capture. Each LLM call, tool invocation,
    or agent decision is recorded as a span with timing, input/output,
    and metadata.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    kind: SpanKind = SpanKind.LLM_REQUEST
    name: str = ""
    timestamp: float = field(default_factory=time.time)
    duration_ms: float = 0.0
    parent_id: str | None = None

    # Content
    input: Any = None
    output: Any = None
    error: str | None = None

    # LLM-specific
    model: str | None = None
    token_usage: TokenUsage | None = None
    cost_usd: float | None = None

    # Tool-specific
    tool_name: str | None = None
    tool_args: dict | None = None
    tool_result: Any = None

    # Metadata
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "kind": self.kind.value,
            "name": self.name,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
            "parent_id": self.parent_id,
            "input": self.input,
            "output": self.output,
            "error": self.error,
            "model": self.model,
            "token_usage": self.token_usage.to_dict() if self.token_usage else None,
            "cost_usd": self.cost_usd,
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "tool_result": self.tool_result,
            "metadata": self.metadata,
        }
        return d

    @classmethod
    def from_dict(cls, data: dict) -> Span:
        token_usage = None
        if data.get("token_usage"):
            token_usage = TokenUsage.from_dict(data["token_usage"])
        return cls(
            id=data["id"],
            kind=SpanKind(data["kind"]),
            name=data.get("name", ""),
            timestamp=data["timestamp"],
            duration_ms=data.get("duration_ms", 0.0),
            parent_id=data.get("parent_id"),
            input=data.get("input"),
            output=data.get("output"),
            error=data.get("error"),
            model=data.get("model"),
            token_usage=token_usage,
            cost_usd=data.get("cost_usd"),
            tool_name=data.get("tool_name"),
            tool_args=data.get("tool_args"),
            tool_result=data.get("tool_result"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class Cassette:
    """A recorded agent run — the fundamental unit of Evalcraft.

    Named after VCR cassettes. Contains all spans from a single agent
    execution, plus metadata for identification and replay.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    version: str = "1.0"
    created_at: float = field(default_factory=time.time)
    agent_name: str = ""
    framework: str = ""

    # The recorded spans
    spans: list[Span] = field(default_factory=list)

    # Input/output summary
    input_text: str = ""
    output_text: str = ""

    # Aggregate metrics
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    total_duration_ms: float = 0.0
    llm_call_count: int = 0
    tool_call_count: int = 0

    # Fingerprint for change detection
    fingerprint: str = ""

    metadata: dict = field(default_factory=dict)

    def compute_fingerprint(self) -> str:
        """Compute a content-based fingerprint for change detection."""
        content = json.dumps(
            [s.to_dict() for s in self.spans],
            sort_keys=True,
            default=str,
        )
        self.fingerprint = hashlib.sha256(content.encode()).hexdigest()[:16]
        return self.fingerprint

    def compute_metrics(self) -> None:
        """Recompute aggregate metrics from spans."""
        self.total_tokens = 0
        self.total_cost_usd = 0.0
        self.total_duration_ms = 0.0
        self.llm_call_count = 0
        self.tool_call_count = 0

        for span in self.spans:
            self.total_duration_ms += span.duration_ms
            if span.token_usage:
                self.total_tokens += span.token_usage.total_tokens
            if span.cost_usd:
                self.total_cost_usd += span.cost_usd
            if span.kind in (SpanKind.LLM_REQUEST, SpanKind.LLM_RESPONSE):
                self.llm_call_count += 1
            if span.kind == SpanKind.TOOL_CALL:
                self.tool_call_count += 1

    def add_span(self, span: Span) -> None:
        """Add a span and recompute metrics."""
        self.spans.append(span)

    def get_tool_calls(self) -> list[Span]:
        """Get all tool call spans."""
        return [s for s in self.spans if s.kind == SpanKind.TOOL_CALL]

    def get_llm_calls(self) -> list[Span]:
        """Get all LLM call spans."""
        return [s for s in self.spans if s.kind in (SpanKind.LLM_REQUEST, SpanKind.LLM_RESPONSE)]

    def get_tool_sequence(self) -> list[str]:
        """Get the ordered list of tool names called."""
        return [s.tool_name for s in self.get_tool_calls() if s.tool_name]

    def to_dict(self) -> dict:
        self.compute_metrics()
        self.compute_fingerprint()
        return {
            "evalcraft_version": "0.1.0",
            "cassette": {
                "id": self.id,
                "name": self.name,
                "version": self.version,
                "created_at": self.created_at,
                "agent_name": self.agent_name,
                "framework": self.framework,
                "input_text": self.input_text,
                "output_text": self.output_text,
                "total_tokens": self.total_tokens,
                "total_cost_usd": self.total_cost_usd,
                "total_duration_ms": self.total_duration_ms,
                "llm_call_count": self.llm_call_count,
                "tool_call_count": self.tool_call_count,
                "fingerprint": self.fingerprint,
                "metadata": self.metadata,
            },
            "spans": [s.to_dict() for s in self.spans],
        }

    @classmethod
    def from_dict(cls, data: dict) -> Cassette:
        cassette_data = data.get("cassette", data)
        spans_data = data.get("spans", [])
        c = cls(
            id=cassette_data.get("id", str(uuid.uuid4())),
            name=cassette_data.get("name", ""),
            version=cassette_data.get("version", "1.0"),
            created_at=cassette_data.get("created_at", time.time()),
            agent_name=cassette_data.get("agent_name", ""),
            framework=cassette_data.get("framework", ""),
            input_text=cassette_data.get("input_text", ""),
            output_text=cassette_data.get("output_text", ""),
            total_tokens=cassette_data.get("total_tokens", 0),
            total_cost_usd=cassette_data.get("total_cost_usd", 0.0),
            total_duration_ms=cassette_data.get("total_duration_ms", 0.0),
            llm_call_count=cassette_data.get("llm_call_count", 0),
            tool_call_count=cassette_data.get("tool_call_count", 0),
            fingerprint=cassette_data.get("fingerprint", ""),
            metadata=cassette_data.get("metadata", {}),
        )
        c.spans = [Span.from_dict(s) for s in spans_data]
        return c

    def save(self, path: str | Path) -> Path:
        """Save cassette to a JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)
        return path

    @classmethod
    def load(cls, path: str | Path) -> Cassette:
        """Load cassette from a JSON file."""
        with open(path) as f:
            data = json.load(f)
        return cls.from_dict(data)


@dataclass
class AgentRun:
    """Result of running an agent — either live or replayed."""
    cassette: Cassette
    success: bool = True
    error: str | None = None
    replayed: bool = False

    def to_dict(self) -> dict:
        return {
            "cassette": self.cassette.to_dict(),
            "success": self.success,
            "error": self.error,
            "replayed": self.replayed,
        }


@dataclass
class EvalResult:
    """Result of evaluating an agent run against assertions."""
    passed: bool = True
    score: float = 1.0
    assertions: list[AssertionResult] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def failed_assertions(self) -> list[AssertionResult]:
        return [a for a in self.assertions if not a.passed]

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "score": self.score,
            "assertions": [a.to_dict() for a in self.assertions],
            "metadata": self.metadata,
        }


@dataclass
class AssertionResult:
    """Result of a single assertion check."""
    name: str = ""
    passed: bool = True
    expected: Any = None
    actual: Any = None
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "expected": self.expected,
            "actual": self.actual,
            "message": self.message,
        }
