"""Tests for evalcraft.core.models."""

import json
import time
import pytest
from pathlib import Path

from evalcraft.core.models import (
    SpanKind, TokenUsage, Span, Cassette, AgentRun, EvalResult, AssertionResult
)


# ──────────────────────────────────────────────
# SpanKind
# ──────────────────────────────────────────────

class TestSpanKind:
    def test_string_values(self):
        assert SpanKind.LLM_REQUEST == "llm_request"
        assert SpanKind.LLM_RESPONSE == "llm_response"
        assert SpanKind.TOOL_CALL == "tool_call"
        assert SpanKind.TOOL_RESULT == "tool_result"
        assert SpanKind.AGENT_STEP == "agent_step"
        assert SpanKind.USER_INPUT == "user_input"
        assert SpanKind.AGENT_OUTPUT == "agent_output"

    def test_from_string(self):
        assert SpanKind("tool_call") == SpanKind.TOOL_CALL
        assert SpanKind("llm_response") == SpanKind.LLM_RESPONSE


# ──────────────────────────────────────────────
# TokenUsage
# ──────────────────────────────────────────────

class TestTokenUsage:
    def test_defaults(self):
        usage = TokenUsage()
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0
        assert usage.total_tokens == 0

    def test_to_dict(self):
        usage = TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30)
        d = usage.to_dict()
        assert d == {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}

    def test_from_dict(self):
        d = {"prompt_tokens": 5, "completion_tokens": 15, "total_tokens": 20}
        usage = TokenUsage.from_dict(d)
        assert usage.prompt_tokens == 5
        assert usage.completion_tokens == 15
        assert usage.total_tokens == 20

    def test_from_dict_defaults(self):
        usage = TokenUsage.from_dict({})
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0
        assert usage.total_tokens == 0

    def test_roundtrip(self):
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        assert TokenUsage.from_dict(usage.to_dict()) == usage


# ──────────────────────────────────────────────
# Span
# ──────────────────────────────────────────────

class TestSpan:
    def test_default_id_generated(self):
        s1 = Span()
        s2 = Span()
        assert s1.id != s2.id
        assert len(s1.id) > 0

    def test_default_kind(self):
        span = Span()
        assert span.kind == SpanKind.LLM_REQUEST

    def test_default_timestamp(self):
        before = time.time()
        span = Span()
        after = time.time()
        assert before <= span.timestamp <= after

    def test_to_dict_basic(self):
        span = Span(kind=SpanKind.TOOL_CALL, name="tool:search")
        d = span.to_dict()
        assert d["kind"] == "tool_call"
        assert d["name"] == "tool:search"
        assert "id" in d
        assert "timestamp" in d

    def test_to_dict_with_token_usage(self):
        usage = TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        span = Span(kind=SpanKind.LLM_RESPONSE, token_usage=usage)
        d = span.to_dict()
        assert d["token_usage"] == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}

    def test_to_dict_no_token_usage(self):
        span = Span()
        assert span.to_dict()["token_usage"] is None

    def test_from_dict_basic(self):
        import uuid
        span_id = str(uuid.uuid4())
        ts = time.time()
        d = {
            "id": span_id,
            "kind": "tool_call",
            "name": "tool:search",
            "timestamp": ts,
            "duration_ms": 100.0,
            "parent_id": None,
            "input": "query",
            "output": "results",
            "error": None,
            "model": None,
            "token_usage": None,
            "cost_usd": None,
            "tool_name": "search",
            "tool_args": {"q": "test"},
            "tool_result": {"results": []},
            "metadata": {},
        }
        span = Span.from_dict(d)
        assert span.id == span_id
        assert span.kind == SpanKind.TOOL_CALL
        assert span.name == "tool:search"
        assert span.tool_name == "search"

    def test_from_dict_with_token_usage(self):
        import uuid
        d = {
            "id": str(uuid.uuid4()),
            "kind": "llm_response",
            "name": "",
            "timestamp": time.time(),
            "duration_ms": 0.0,
            "parent_id": None,
            "input": None,
            "output": None,
            "error": None,
            "model": "gpt-4",
            "token_usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            "cost_usd": 0.001,
            "tool_name": None,
            "tool_args": None,
            "tool_result": None,
            "metadata": {},
        }
        span = Span.from_dict(d)
        assert span.token_usage is not None
        assert span.token_usage.prompt_tokens == 10
        assert span.model == "gpt-4"

    def test_roundtrip(self):
        span = Span(
            kind=SpanKind.TOOL_CALL,
            name="tool:search",
            tool_name="search",
            tool_args={"q": "test"},
            tool_result={"results": ["a", "b"]},
            duration_ms=50.0,
            metadata={"source": "test"},
        )
        roundtripped = Span.from_dict(span.to_dict())
        assert roundtripped.kind == span.kind
        assert roundtripped.name == span.name
        assert roundtripped.tool_name == span.tool_name
        assert roundtripped.tool_args == span.tool_args
        assert roundtripped.metadata == span.metadata


# ──────────────────────────────────────────────
# Cassette
# ──────────────────────────────────────────────

class TestCassette:
    def test_defaults(self):
        c = Cassette()
        assert c.spans == []
        assert c.total_tokens == 0
        assert c.total_cost_usd == 0.0
        assert c.llm_call_count == 0
        assert c.tool_call_count == 0

    def test_add_span(self):
        c = Cassette()
        span = Span(kind=SpanKind.TOOL_CALL)
        c.add_span(span)
        assert len(c.spans) == 1
        assert c.spans[0] is span

    def test_get_tool_calls(self, simple_cassette):
        tool_calls = simple_cassette.get_tool_calls()
        assert len(tool_calls) == 1
        assert tool_calls[0].tool_name == "get_weather"

    def test_get_llm_calls(self, simple_cassette):
        llm_calls = simple_cassette.get_llm_calls()
        assert len(llm_calls) == 1
        assert llm_calls[0].kind == SpanKind.LLM_RESPONSE

    def test_get_tool_sequence(self, multi_tool_cassette):
        seq = multi_tool_cassette.get_tool_sequence()
        assert seq == ["web_search", "summarize", "send_email"]

    def test_compute_metrics(self, simple_cassette):
        simple_cassette.compute_metrics()
        assert simple_cassette.total_tokens == 30
        assert simple_cassette.total_cost_usd == 0.001
        assert simple_cassette.tool_call_count == 1
        assert simple_cassette.llm_call_count == 1

    def test_compute_metrics_empty(self):
        c = Cassette()
        c.compute_metrics()
        assert c.total_tokens == 0
        assert c.total_cost_usd == 0.0
        assert c.llm_call_count == 0
        assert c.tool_call_count == 0

    def test_compute_fingerprint(self, simple_cassette):
        fp1 = simple_cassette.compute_fingerprint()
        assert len(fp1) == 16
        fp2 = simple_cassette.compute_fingerprint()
        assert fp1 == fp2

    def test_fingerprint_changes_with_spans(self):
        c = Cassette()
        fp1 = c.compute_fingerprint()
        c.add_span(Span(kind=SpanKind.TOOL_CALL, name="tool:search"))
        fp2 = c.compute_fingerprint()
        assert fp1 != fp2

    def test_to_dict_structure(self, simple_cassette):
        d = simple_cassette.to_dict()
        assert "evalcraft_version" in d
        assert "cassette" in d
        assert "spans" in d
        assert d["cassette"]["name"] == "test_cassette"
        assert isinstance(d["spans"], list)

    def test_from_dict(self, simple_cassette):
        d = simple_cassette.to_dict()
        restored = Cassette.from_dict(d)
        assert restored.name == simple_cassette.name
        assert restored.agent_name == simple_cassette.agent_name
        assert len(restored.spans) == len(simple_cassette.spans)

    def test_save_and_load(self, simple_cassette, tmp_path):
        path = tmp_path / "test_cassette.json"
        simple_cassette.save(path)
        assert path.exists()
        loaded = Cassette.load(path)
        assert loaded.name == simple_cassette.name
        assert len(loaded.spans) == len(simple_cassette.spans)

    def test_save_creates_parent_dirs(self, simple_cassette, tmp_path):
        path = tmp_path / "deep" / "nested" / "cassette.json"
        simple_cassette.save(path)
        assert path.exists()

    def test_load_from_string_path(self, simple_cassette, tmp_path):
        path = tmp_path / "cassette.json"
        simple_cassette.save(path)
        loaded = Cassette.load(str(path))
        assert loaded.name == simple_cassette.name


# ──────────────────────────────────────────────
# AgentRun
# ──────────────────────────────────────────────

class TestAgentRun:
    def test_defaults(self):
        c = Cassette()
        run = AgentRun(cassette=c)
        assert run.success is True
        assert run.error is None
        assert run.replayed is False

    def test_to_dict(self, simple_cassette):
        run = AgentRun(cassette=simple_cassette, success=True, replayed=True)
        d = run.to_dict()
        assert d["success"] is True
        assert d["replayed"] is True
        assert "cassette" in d


# ──────────────────────────────────────────────
# EvalResult / AssertionResult
# ──────────────────────────────────────────────

class TestEvalResult:
    def test_defaults(self):
        result = EvalResult()
        assert result.passed is True
        assert result.score == 1.0
        assert result.assertions == []

    def test_failed_assertions(self):
        a1 = AssertionResult(name="a1", passed=True)
        a2 = AssertionResult(name="a2", passed=False)
        a3 = AssertionResult(name="a3", passed=False)
        result = EvalResult(passed=False, score=0.33, assertions=[a1, a2, a3])
        failed = result.failed_assertions
        assert len(failed) == 2
        assert all(not a.passed for a in failed)

    def test_to_dict(self):
        result = EvalResult(passed=True, score=0.8)
        d = result.to_dict()
        assert d["passed"] is True
        assert d["score"] == 0.8
        assert "assertions" in d


class TestAssertionResult:
    def test_defaults(self):
        r = AssertionResult()
        assert r.name == ""
        assert r.passed is True

    def test_to_dict(self):
        r = AssertionResult(name="test", passed=False, expected="a", actual="b", message="mismatch")
        d = r.to_dict()
        assert d["name"] == "test"
        assert d["passed"] is False
        assert d["expected"] == "a"
        assert d["actual"] == "b"
        assert d["message"] == "mismatch"
