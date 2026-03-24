"""Tests for evalcraft.adapters.gemini_adapter."""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from evalcraft.adapters.gemini_adapter import (
    GeminiAdapter,
    _contents_to_str,
    _estimate_cost,
    _extract_model_name,
    _response_to_str,
)
from evalcraft.capture.recorder import CaptureContext
from evalcraft.core.models import SpanKind


# ──────────────────────────────────────────────
# Pricing
# ──────────────────────────────────────────────

class TestEstimateCost:
    def test_known_model(self):
        # gemini-2.0-flash: input=0.10, output=0.40 per 1M
        cost = _estimate_cost("gemini-2.0-flash", 1000, 500)
        expected = (1000 * 0.10 + 500 * 0.40) / 1_000_000
        assert cost == pytest.approx(expected)

    def test_prefix_match(self):
        # "gemini-1.5-pro-001" should match "gemini-1.5-pro"
        cost = _estimate_cost("gemini-1.5-pro-001", 1000, 500)
        assert cost is not None
        assert cost > 0

    def test_unknown_model(self):
        cost = _estimate_cost("nonexistent-model", 1000, 500)
        assert cost is None

    def test_zero_tokens(self):
        cost = _estimate_cost("gemini-2.0-flash", 0, 0)
        assert cost == 0.0


# ──────────────────────────────────────────────
# Content helpers
# ──────────────────────────────────────────────

class TestContentsToStr:
    def test_plain_string(self):
        assert _contents_to_str("Hello world") == "Hello world"

    def test_list_of_strings(self):
        result = _contents_to_str(["Hello", "World"])
        assert "Hello" in result
        assert "World" in result

    def test_list_of_dicts(self):
        contents = [
            {"role": "user", "parts": ["What is the weather?"]},
        ]
        result = _contents_to_str(contents)
        assert "user" in result
        assert "weather" in result

    def test_object_with_parts(self):
        part = MagicMock()
        part.text = "Hello from part"
        contents = MagicMock()
        contents.parts = [part]
        # Not a list, not a string
        delattr(contents, "__iter__")

        result = _contents_to_str(contents)
        assert "Hello from part" in result


class TestResponseToStr:
    def test_response_text_property(self):
        response = MagicMock()
        response.text = "The weather is sunny"
        assert _response_to_str(response) == "The weather is sunny"

    def test_fallback_to_candidates(self):
        part = MagicMock()
        part.text = "Answer from candidate"
        part.function_call = None
        del part.function_call

        content = MagicMock()
        content.parts = [part]

        candidate = MagicMock()
        candidate.content = content

        response = MagicMock()
        response.text = property(lambda self: (_ for _ in ()).throw(ValueError))
        type(response).text = property(lambda self: (_ for _ in ()).throw(ValueError))
        response.candidates = [candidate]

        result = _response_to_str(response)
        assert "Answer from candidate" in result

    def test_function_call_in_response(self):
        fc = MagicMock()
        fc.name = "get_weather"
        fc.args = {"city": "Paris"}

        part = MagicMock()
        part.text = ""
        part.function_call = fc

        content = MagicMock()
        content.parts = [part]

        candidate = MagicMock()
        candidate.content = content

        response = MagicMock()
        type(response).text = property(lambda self: (_ for _ in ()).throw(ValueError))
        response.candidates = [candidate]

        result = _response_to_str(response)
        assert "function_call" in result
        assert "get_weather" in result


class TestExtractModelName:
    def test_model_name_attribute(self):
        model = MagicMock()
        model.model_name = "gemini-2.0-flash"
        assert _extract_model_name(model) == "gemini-2.0-flash"

    def test_strips_models_prefix(self):
        model = MagicMock()
        model.model_name = "models/gemini-2.0-flash"
        assert _extract_model_name(model) == "gemini-2.0-flash"

    def test_no_model_name(self):
        model = MagicMock(spec=[])
        assert _extract_model_name(model) == "unknown"


# ──────────────────────────────────────────────
# Adapter patching
# ──────────────────────────────────────────────

class TestGeminiAdapter:
    def _make_fake_genai_module(self):
        """Build a minimal fake google.generativeai module for testing."""
        class FakeGenerativeModel:
            def __init__(self, model_name="gemini-2.0-flash"):
                self.model_name = model_name

            def generate_content(self, contents, **kwargs):
                # Build a response-like object
                usage = MagicMock()
                usage.prompt_token_count = 10
                usage.candidates_token_count = 20

                finish = MagicMock()
                finish.name = "STOP"

                candidate = MagicMock()
                candidate.finish_reason = finish

                resp = MagicMock()
                resp.text = "Mock response"
                resp.usage_metadata = usage
                resp.candidates = [candidate]
                return resp

            async def generate_content_async(self, contents, **kwargs):
                return self.generate_content(contents, **kwargs)

        module = ModuleType("google.generativeai")
        module.GenerativeModel = FakeGenerativeModel
        return module, FakeGenerativeModel

    def test_import_error_when_missing(self):
        adapter = GeminiAdapter()
        with patch.dict(sys.modules, {"google.generativeai": None, "google": None}):
            with pytest.raises(ImportError, match="google-generativeai"):
                adapter._patch()

    def test_patch_and_unpatch(self):
        module, FakeModel = self._make_fake_genai_module()

        with patch.dict(sys.modules, {"google.generativeai": module, "google": MagicMock()}):
            original_generate = FakeModel.generate_content

            adapter = GeminiAdapter()
            adapter._patch()

            # Method should be patched
            assert FakeModel.generate_content is not original_generate

            adapter._unpatch()

            # Method should be restored
            assert FakeModel.generate_content is original_generate

    def test_records_llm_call(self):
        module, FakeModel = self._make_fake_genai_module()

        with patch.dict(sys.modules, {"google.generativeai": module, "google": MagicMock()}):
            with CaptureContext(name="gemini_test") as ctx:
                adapter = GeminiAdapter()
                adapter._patch()
                try:
                    model = FakeModel("gemini-2.0-flash")
                    response = model.generate_content("What is the weather?")
                finally:
                    adapter._unpatch()

            cassette = ctx.cassette
            llm_calls = cassette.get_llm_calls()
            assert len(llm_calls) >= 1

            span = llm_calls[0]
            assert span.model == "gemini-2.0-flash"
            assert span.output == "Mock response"
            assert span.token_usage is not None
            assert span.token_usage.prompt_tokens == 10
            assert span.token_usage.completion_tokens == 20

    def test_context_manager(self):
        module, FakeModel = self._make_fake_genai_module()

        with patch.dict(sys.modules, {"google.generativeai": module, "google": MagicMock()}):
            with CaptureContext(name="ctx_test") as ctx:
                with GeminiAdapter():
                    model = FakeModel("gemini-1.5-flash")
                    model.generate_content("Hello")

            assert len(ctx.cassette.get_llm_calls()) >= 1

    def test_records_error(self):
        module, FakeModel = self._make_fake_genai_module()

        # Make generate_content raise
        def failing_generate(self, contents, **kwargs):
            raise RuntimeError("API quota exceeded")

        FakeModel.generate_content = failing_generate

        with patch.dict(sys.modules, {"google.generativeai": module, "google": MagicMock()}):
            with CaptureContext(name="error_test") as ctx:
                with GeminiAdapter():
                    model = FakeModel("gemini-2.0-flash")
                    with pytest.raises(RuntimeError, match="quota exceeded"):
                        model.generate_content("test")

            # Error span should be recorded
            error_spans = [s for s in ctx.cassette.spans if s.error]
            assert len(error_spans) == 1
            assert "quota exceeded" in error_spans[0].error

    def test_no_capture_context_silent(self):
        """Adapter should silently drop spans when no CaptureContext is active."""
        module, FakeModel = self._make_fake_genai_module()

        with patch.dict(sys.modules, {"google.generativeai": module, "google": MagicMock()}):
            with GeminiAdapter():
                model = FakeModel("gemini-2.0-flash")
                response = model.generate_content("test")
                # Should not raise, just silently skip recording
                assert response.text == "Mock response"
