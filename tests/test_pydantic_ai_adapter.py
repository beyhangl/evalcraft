"""Tests for evalcraft.adapters.pydantic_ai_adapter."""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from evalcraft.adapters.pydantic_ai_adapter import (
    PydanticAIAdapter,
    _estimate_cost,
    _extract_model_name,
    _extract_output,
    _normalize_model_name,
)
from evalcraft.capture.recorder import CaptureContext
from evalcraft.core.models import SpanKind


# ──────────────────────────────────────────────
# Pricing / helpers
# ──────────────────────────────────────────────

class TestNormalizeModelName:
    def test_strips_openai_prefix(self):
        assert _normalize_model_name("openai:gpt-4o-mini") == "gpt-4o-mini"

    def test_strips_anthropic_prefix(self):
        assert _normalize_model_name("anthropic:claude-sonnet-4-6") == "claude-sonnet-4-6"

    def test_no_prefix(self):
        assert _normalize_model_name("gpt-4o") == "gpt-4o"

    def test_groq_prefix(self):
        assert _normalize_model_name("groq:llama-3.3-70b-versatile") == "llama-3.3-70b-versatile"


class TestEstimateCost:
    def test_known_model(self):
        cost = _estimate_cost("gpt-4o-mini", 1000, 500)
        expected = (1000 * 0.15 + 500 * 0.60) / 1_000_000
        assert cost == pytest.approx(expected)

    def test_anthropic_model(self):
        cost = _estimate_cost("claude-sonnet-4-6", 1000, 500)
        assert cost is not None
        assert cost > 0

    def test_unknown_model(self):
        assert _estimate_cost("nonexistent-model", 1000, 500) is None

    def test_prefix_match(self):
        cost = _estimate_cost("gpt-4o-2024-11-20", 1000, 500)
        assert cost is not None


class TestExtractModelName:
    def test_string_model(self):
        agent = MagicMock()
        agent.model = "openai:gpt-4o-mini"
        assert _extract_model_name(agent) == "gpt-4o-mini"

    def test_model_object_with_model_name(self):
        model_obj = MagicMock()
        model_obj.model_name = "gpt-4o"
        agent = MagicMock()
        agent.model = model_obj
        assert _extract_model_name(agent) == "gpt-4o"

    def test_none_model(self):
        agent = MagicMock()
        agent.model = None
        assert _extract_model_name(agent) == "unknown"


class TestExtractOutput:
    def test_string_data(self):
        result = MagicMock()
        result.data = "Hello world"
        assert _extract_output(result) == "Hello world"

    def test_structured_data(self):
        result = MagicMock()
        result.data = {"answer": "Hello"}
        assert "answer" in _extract_output(result)


# ──────────────────────────────────────────────
# Adapter
# ──────────────────────────────────────────────

class TestPydanticAIAdapter:
    def _make_fake_pydantic_ai(self):
        """Build a minimal fake pydantic_ai module for testing."""

        class FakeUsage:
            request_tokens = 50
            response_tokens = 25
            total_tokens = 75

        class FakeResult:
            data = "Mock response from pydantic-ai agent"

            def usage(self):
                return FakeUsage()

            def all_messages(self):
                return []

        class FakeAgent:
            def __init__(self, model="openai:gpt-4o-mini", **kwargs):
                self.model = model
                self.name = kwargs.get("name", "")

            async def run(self, user_prompt, **kwargs):
                return FakeResult()

            def run_sync(self, user_prompt, **kwargs):
                return FakeResult()

        module = ModuleType("pydantic_ai")
        module.Agent = FakeAgent
        return module, FakeAgent

    def test_import_error_when_missing(self):
        adapter = PydanticAIAdapter()
        with patch.dict(sys.modules, {"pydantic_ai": None}):
            with pytest.raises(ImportError, match="pydantic-ai"):
                adapter._patch()

    def test_patch_and_unpatch(self):
        module, FakeAgent = self._make_fake_pydantic_ai()

        with patch.dict(sys.modules, {"pydantic_ai": module}):
            original_run_sync = FakeAgent.run_sync

            adapter = PydanticAIAdapter()
            adapter._patch()
            assert FakeAgent.run_sync is not original_run_sync

            adapter._unpatch()
            assert FakeAgent.run_sync is original_run_sync

    def test_records_llm_call_sync(self):
        module, FakeAgent = self._make_fake_pydantic_ai()

        with patch.dict(sys.modules, {"pydantic_ai": module}):
            with CaptureContext(name="pydantic_test") as ctx:
                adapter = PydanticAIAdapter()
                adapter._patch()
                try:
                    agent = FakeAgent("openai:gpt-4o-mini")
                    result = agent.run_sync("What is the weather?")
                finally:
                    adapter._unpatch()

            cassette = ctx.cassette
            llm_calls = cassette.get_llm_calls()
            assert len(llm_calls) >= 1

            span = llm_calls[0]
            assert span.model == "gpt-4o-mini"
            assert span.output == "Mock response from pydantic-ai agent"
            assert span.token_usage is not None
            assert span.token_usage.prompt_tokens == 50
            assert span.token_usage.completion_tokens == 25
            assert span.metadata.get("framework") == "pydantic-ai"

    def test_context_manager(self):
        module, FakeAgent = self._make_fake_pydantic_ai()

        with patch.dict(sys.modules, {"pydantic_ai": module}):
            with CaptureContext(name="ctx_test") as ctx:
                with PydanticAIAdapter():
                    agent = FakeAgent("anthropic:claude-sonnet-4-6")
                    agent.run_sync("Hello")

            assert len(ctx.cassette.get_llm_calls()) >= 1
            assert ctx.cassette.get_llm_calls()[0].model == "claude-sonnet-4-6"

    def test_records_error(self):
        module, FakeAgent = self._make_fake_pydantic_ai()

        def failing_run_sync(self, user_prompt, **kwargs):
            raise RuntimeError("Model unavailable")

        FakeAgent.run_sync = failing_run_sync

        with patch.dict(sys.modules, {"pydantic_ai": module}):
            with CaptureContext(name="error_test") as ctx:
                with PydanticAIAdapter():
                    agent = FakeAgent("openai:gpt-4o")
                    with pytest.raises(RuntimeError, match="unavailable"):
                        agent.run_sync("test")

            error_spans = [s for s in ctx.cassette.spans if s.error]
            assert len(error_spans) == 1
            assert "unavailable" in error_spans[0].error

    def test_no_capture_context_silent(self):
        module, FakeAgent = self._make_fake_pydantic_ai()

        with patch.dict(sys.modules, {"pydantic_ai": module}):
            with PydanticAIAdapter():
                agent = FakeAgent("openai:gpt-4o-mini")
                result = agent.run_sync("test")
                assert result.data == "Mock response from pydantic-ai agent"

    def test_cost_estimation(self):
        module, FakeAgent = self._make_fake_pydantic_ai()

        with patch.dict(sys.modules, {"pydantic_ai": module}):
            with CaptureContext(name="cost_test") as ctx:
                with PydanticAIAdapter():
                    agent = FakeAgent("openai:gpt-4o-mini")
                    agent.run_sync("test")

            span = ctx.cassette.get_llm_calls()[0]
            assert span.cost_usd is not None
            assert span.cost_usd > 0
