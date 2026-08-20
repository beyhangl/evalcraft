"""Tests for opaque-reasoning capture and integrity checking.

Reasoning models return content the caller must send back verbatim (Anthropic
thinking blocks carry a cryptographic ``signature``; OpenAI Responses returns
``reasoning.encrypted_content``). Dropping it makes replay *invalid*, not merely
lossy — the provider rejects or degrades the turn. These tests pin both halves:
capture when present, and a loud CRITICAL when a reasoning cassette lacks it.
"""

from unittest.mock import MagicMock

import pytest

from evalcraft.core.models import Cassette, Span, SpanKind
from evalcraft.core.reasoning import (
    REASONING_METADATA_KEY,
    find_degraded_reasoning_spans,
    is_reasoning_model,
    span_has_reasoning_state,
)
from evalcraft.staleness import StalenessChecker

THINKING = [{"type": "thinking", "thinking": "step 1...", "signature": "sig-abc"}]


def _llm_span(model, metadata=None):
    return Span(
        kind=SpanKind.LLM_RESPONSE, model=model, output="answer",
        metadata=metadata or {},
    )


def _cassette(*spans):
    c = Cassette(name="t", agent_name="a")
    for s in spans:
        c.add_span(s)
    return c


# ── model identification ─────────────────────────────────────────────────────

class TestIsReasoningModel:
    @pytest.mark.parametrize("model", [
        "o1-preview", "o3-mini", "o4-mini", "gpt-5.4",
        "claude-sonnet-4-thinking", "deepseek-reasoner",
    ])
    def test_recognised(self, model):
        assert is_reasoning_model(model)

    @pytest.mark.parametrize("model", [
        "gpt-4o-mini", "claude-3-haiku-20240307", "gemini-2.0-flash", "", None,
    ])
    def test_not_flagged(self, model):
        # Conservative by design: ordinary models must never be false-flagged.
        assert not is_reasoning_model(model)

    def test_case_insensitive(self):
        assert is_reasoning_model("O3-Mini")


# ── span-level state ─────────────────────────────────────────────────────────

class TestSpanReasoningState:
    def test_detects_present_state(self):
        assert span_has_reasoning_state(_llm_span("o3", {REASONING_METADATA_KEY: THINKING}))

    def test_detects_absent_state(self):
        assert not span_has_reasoning_state(_llm_span("o3"))

    def test_empty_list_counts_as_absent(self):
        assert not span_has_reasoning_state(_llm_span("o3", {REASONING_METADATA_KEY: []}))


# ── degraded-cassette detection ──────────────────────────────────────────────

class TestFindDegraded:
    def test_flags_reasoning_span_without_state(self):
        assert len(find_degraded_reasoning_spans(_cassette(_llm_span("o3-mini")))) == 1

    def test_ignores_reasoning_span_with_state(self):
        c = _cassette(_llm_span("o3-mini", {REASONING_METADATA_KEY: THINKING}))
        assert find_degraded_reasoning_spans(c) == []

    def test_ignores_non_reasoning_models(self):
        assert find_degraded_reasoning_spans(_cassette(_llm_span("gpt-4o"))) == []

    def test_ignores_tool_spans(self):
        c = _cassette(Span(kind=SpanKind.TOOL_CALL, tool_name="t", model="o3"))
        assert find_degraded_reasoning_spans(c) == []

    def test_reports_each_degraded_span(self):
        c = _cassette(_llm_span("o3-mini"), _llm_span("o3-mini"), _llm_span("gpt-4o"))
        assert len(find_degraded_reasoning_spans(c)) == 2


# ── surfaced through check-stale ─────────────────────────────────────────────

class TestStalenessIntegration:
    def test_degraded_cassette_is_critical(self):
        report = StalenessChecker().check(_cassette(_llm_span("o3-mini")))
        assert report.has_critical
        finding = next(f for f in report.findings if f.category == "reasoning_state_missing")
        assert "invalid" in finding.message
        assert finding.recorded_value == ["o3-mini"]

    def test_captured_state_is_not_flagged(self):
        c = _cassette(_llm_span("o3-mini", {REASONING_METADATA_KEY: THINKING}))
        report = StalenessChecker().check(c)
        assert not report.has_critical

    def test_ordinary_cassette_unaffected(self):
        report = StalenessChecker().check(_cassette(_llm_span("gpt-4o")))
        assert not report.has_critical
        assert "reasoning_state_missing" not in [f.category for f in report.findings]

    def test_runs_without_provenance(self):
        # A legacy cassette can be degraded too — the check must not be gated
        # behind provenance.
        report = StalenessChecker().check(_cassette(_llm_span("o3-mini")))
        cats = [f.category for f in report.findings]
        assert "reasoning_state_missing" in cats and "no_provenance" in cats


# ── adapter capture ──────────────────────────────────────────────────────────

class TestAnthropicCapture:
    def _response(self, *blocks):
        r = MagicMock()
        r.content = list(blocks)
        return r

    def _block(self, **attrs):
        b = MagicMock()
        for k, v in attrs.items():
            setattr(b, k, v)
        return b

    def test_captures_thinking_block_with_signature(self):
        from evalcraft.adapters.anthropic_adapter import _extract_reasoning_blocks

        resp = self._response(
            self._block(type="thinking", thinking="reasoning...", signature="sig-1"),
            self._block(type="text", text="final answer"),
        )
        blocks = _extract_reasoning_blocks(resp)
        assert blocks == [
            {"type": "thinking", "thinking": "reasoning...", "signature": "sig-1"}
        ]

    def test_captures_redacted_thinking(self):
        from evalcraft.adapters.anthropic_adapter import _extract_reasoning_blocks

        resp = self._response(self._block(type="redacted_thinking", data="opaque"))
        assert _extract_reasoning_blocks(resp) == [
            {"type": "redacted_thinking", "data": "opaque"}
        ]

    def test_no_reasoning_blocks_returns_empty(self):
        from evalcraft.adapters.anthropic_adapter import _extract_reasoning_blocks

        resp = self._response(self._block(type="text", text="hi"))
        assert _extract_reasoning_blocks(resp) == []

    def test_mocked_fields_are_rejected(self):
        # A bare MagicMock block must not leak MagicMocks into the cassette.
        from evalcraft.adapters.anthropic_adapter import _extract_reasoning_blocks

        resp = self._response(self._block(type="thinking"))
        assert _extract_reasoning_blocks(resp) == []

    def test_malformed_response_is_safe(self):
        from evalcraft.adapters.anthropic_adapter import _extract_reasoning_blocks

        bad = MagicMock()
        bad.content = None
        assert _extract_reasoning_blocks(bad) == []
