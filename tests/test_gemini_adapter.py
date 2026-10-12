"""Google GenAI capture tests; all SDK requests use fakes or mocked HTTP."""

from __future__ import annotations

import json
import sys
from types import ModuleType, SimpleNamespace
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


def response(*, prompt=10, cached=0, completion=20, thoughts=0, parts=None):
    return SimpleNamespace(
        text="Mock response",
        usage_metadata=SimpleNamespace(
            prompt_token_count=prompt,
            cached_content_token_count=cached,
            candidates_token_count=completion,
            thoughts_token_count=thoughts,
        ),
        candidates=[
            SimpleNamespace(
                finish_reason=SimpleNamespace(name="STOP"),
                content=SimpleNamespace(parts=parts or [SimpleNamespace(text="Mock response")]),
            )
        ],
    )


@pytest.fixture
def fake_sdk(monkeypatch):
    """Match the SDK's independent keyword-only Models/AsyncModels methods."""
    calls = []

    class Models:
        reply = response()
        error = None

        def generate_content(self, *, model, contents, config=None):
            calls.append((model, contents, config))
            if self.error:
                raise self.error
            return self.reply

    class AsyncModels:
        reply = response()
        error = None

        async def generate_content(self, *, model, contents, config=None):
            calls.append((model, contents, config))
            if self.error:
                raise self.error
            return self.reply

    google = ModuleType("google")
    google.__path__ = []
    genai = ModuleType("google.genai")
    genai.__path__ = []
    models = ModuleType("google.genai.models")
    models.Models = Models
    models.AsyncModels = AsyncModels
    for name, module in (
        ("google", google),
        ("google.genai", genai),
        ("google.genai.models", models),
    ):
        monkeypatch.setitem(sys.modules, name, module)
    return SimpleNamespace(Models=Models, AsyncModels=AsyncModels, calls=calls)


class TestEstimateCost:
    def test_known_model(self):
        assert _estimate_cost("gemini-2.0-flash", 1000, 500) == pytest.approx(
            (1000 * 0.10 + 500 * 0.40) / 1_000_000
        )

    def test_snapshot_match(self):
        assert _estimate_cost("gemini-1.5-pro-001", 1000, 500) is not None

    def test_unknown_model(self):
        assert _estimate_cost("nonexistent-model", 1000, 500) is None

    def test_zero_tokens(self):
        assert _estimate_cost("gemini-2.0-flash", 0, 0) == 0.0

    def test_cache_segmentation_preserves_estimate(self):
        # Built-in estimates conservatively bill cached reads at ordinary input
        # rates; segmentation must not drop that input from the estimate.
        assert _estimate_cost("gemini-2.0-flash", 200, 500, 800) == pytest.approx(
            _estimate_cost("gemini-2.0-flash", 1000, 500)
        )


class TestContentsToStr:
    @pytest.mark.parametrize(
        ("contents", "expected"),
        [
            ("Hello", "Hello"),
            (["Hello", "World"], "Hello\nWorld"),
            ([{"role": "user", "parts": [{"text": "Weather?"}]}], "user: Weather?"),
            (SimpleNamespace(parts=[SimpleNamespace(text="Hello")]), "Hello"),
            ({"text": "Part text"}, "Part text"),
            (None, ""),
        ],
    )
    def test_text_forms(self, contents, expected):
        assert _contents_to_str(contents) == expected

    def test_function_result_content(self):
        assert "function_response:get_weather" in _contents_to_str(
            {
                "role": "user",
                "parts": [
                    {
                        "function_response": {
                            "name": "get_weather",
                            "response": {"weather": "sunny"},
                        }
                    }
                ],
            }
        )


class TestResponseToStr:
    def test_response_text_property(self):
        assert _response_to_str(SimpleNamespace(text="Sunny")) == "Sunny"

    def test_text_and_function_call(self):
        reply = response(
            parts=[
                SimpleNamespace(text="Checking weather", function_call=None),
                SimpleNamespace(
                    text=None,
                    function_call=SimpleNamespace(
                        name="get_weather",
                        args={"city": "Paris"},
                    ),
                ),
            ]
        )
        text = _response_to_str(reply)
        assert "Checking weather" in text
        assert "function_call:get_weather({'city': 'Paris'})" in text

    def test_thought_text_is_not_visible_output(self):
        assert (
            _response_to_str(
                response(
                    parts=[
                        SimpleNamespace(text="Internal thought", thought=True),
                        SimpleNamespace(text="Visible answer", thought=False),
                    ]
                )
            )
            == "Visible answer"
        )

    def test_none_text(self):
        assert _response_to_str(SimpleNamespace(text=None)) == ""


class TestExtractModelName:
    @pytest.mark.parametrize(
        ("model", "expected"),
        [
            ("gemini-2.5-flash", "gemini-2.5-flash"),
            ("models/gemini-2.5-flash", "gemini-2.5-flash"),
            (None, "unknown"),
            (MagicMock(), "unknown"),
        ],
    )
    def test_model_name(self, model, expected):
        assert _extract_model_name(model) == expected


class TestGeminiAdapter:
    def test_import_error_when_missing(self):
        with patch.dict(sys.modules, {"google.genai.models": None}):
            with pytest.raises(ImportError, match="google-genai"):
                GeminiAdapter()._patch()

    def test_patch_and_restore_both_methods(self, fake_sdk):
        sync = fake_sdk.Models.generate_content
        asynchronous = fake_sdk.AsyncModels.generate_content
        with GeminiAdapter():
            assert fake_sdk.Models.generate_content is not sync
            assert fake_sdk.AsyncModels.generate_content is not asynchronous
        assert fake_sdk.Models.generate_content is sync
        assert fake_sdk.AsyncModels.generate_content is asynchronous

    def test_records_sync_call_and_forwards_config(self, fake_sdk):
        client_models = fake_sdk.Models()  # Existing clients must also be captured.
        config = {"temperature": 0}
        with CaptureContext(name="gemini_test") as ctx, GeminiAdapter():
            reply = client_models.generate_content(
                model="models/gemini-2.5-flash",
                contents="Weather?",
                config=config,
            )
        assert reply is client_models.reply
        assert fake_sdk.calls == [("models/gemini-2.5-flash", "Weather?", config)]
        [span] = ctx.cassette.get_llm_calls()
        assert span.model == "gemini-2.5-flash"
        assert span.input == "Weather?"
        assert span.output == "Mock response"
        assert span.token_usage.prompt_tokens == 10
        assert span.token_usage.completion_tokens == 20
        assert span.token_usage.total_tokens == 30
        assert span.metadata["finish_reason"] == "STOP"

    async def test_records_async_once(self, fake_sdk):
        with CaptureContext(name="async_test") as ctx:
            async with GeminiAdapter():
                await fake_sdk.AsyncModels().generate_content(
                    model="gemini-2.5-flash",
                    contents="Hello",
                )
        [span] = ctx.cassette.get_llm_calls()
        assert span.output == "Mock response"
        assert len(fake_sdk.calls) == 1

    @pytest.mark.parametrize("asynchronous", [False, True])
    async def test_cached_input_and_thinking_tokens(self, fake_sdk, asynchronous):
        resource = fake_sdk.AsyncModels() if asynchronous else fake_sdk.Models()
        resource.reply = response(prompt=100, cached=80, completion=20, thoughts=5)
        with CaptureContext(name="token_test") as ctx, GeminiAdapter():
            kwargs = {"model": "gemini-2.5-flash", "contents": "Hello"}
            if asynchronous:
                await resource.generate_content(**kwargs)
            else:
                resource.generate_content(**kwargs)
        [span] = ctx.cassette.get_llm_calls()
        assert span.token_usage.prompt_tokens == 20
        assert span.token_usage.cache_read_tokens == 80
        assert span.token_usage.cache_write_tokens == 0
        assert span.token_usage.completion_tokens == 25
        assert span.token_usage.total_tokens == 125
        assert span.metadata["thoughts_token_count"] == 5
        assert span.cost_usd == pytest.approx(_estimate_cost("gemini-2.5-flash", 20, 25, 80))

    @pytest.mark.parametrize("value", [MagicMock(), None, True, "42", 1.5, -20])
    def test_invalid_usage_does_not_enter_cassette(self, fake_sdk, value):
        resource = fake_sdk.Models()
        resource.reply = response(prompt=value, cached=value, completion=value, thoughts=value)
        with CaptureContext(name="mock_usage") as ctx, GeminiAdapter():
            resource.generate_content(model="gemini-2.5-flash", contents="Hello")
        [span] = ctx.cassette.get_llm_calls()
        assert span.token_usage.to_dict() == {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
        }
        json.dumps(ctx.cassette.to_dict())  # No mock may leak into serialized usage.

    def test_cache_count_cannot_exceed_total_input(self, fake_sdk):
        resource = fake_sdk.Models()
        resource.reply = response(prompt=10, cached=20)
        with CaptureContext(name="inconsistent_usage") as ctx, GeminiAdapter():
            resource.generate_content(model="gemini-2.5-flash", contents="Hello")
        [span] = ctx.cassette.get_llm_calls()
        assert span.token_usage.prompt_tokens == 0
        assert span.token_usage.cache_read_tokens == 10

    @pytest.mark.parametrize("asynchronous", [False, True])
    async def test_function_requests_are_not_executed_tool_spans(self, fake_sdk, asynchronous):
        resource = fake_sdk.AsyncModels() if asynchronous else fake_sdk.Models()
        resource.reply = response(
            parts=[
                SimpleNamespace(
                    text=None,
                    function_call=SimpleNamespace(name="get_weather", args={"city": "Paris"}),
                )
            ]
        )
        with CaptureContext(name="function_test") as ctx, GeminiAdapter():
            if asynchronous:
                await resource.generate_content(model="gemini-2.5-flash", contents="Weather?")
            else:
                resource.generate_content(model="gemini-2.5-flash", contents="Weather?")
        [span] = ctx.cassette.get_llm_calls()
        assert "function_call:get_weather" in span.output
        assert span.metadata["function_calls"] == [
            {"name": "get_weather", "args": {"city": "Paris"}}
        ]
        assert ctx.cassette.get_tool_calls() == []

    @pytest.mark.parametrize("asynchronous", [False, True])
    async def test_records_error_and_restores_methods(self, fake_sdk, asynchronous):
        resource = fake_sdk.AsyncModels() if asynchronous else fake_sdk.Models()
        resource.error = RuntimeError("quota exceeded")
        sync, asynchronous_method = (
            fake_sdk.Models.generate_content,
            fake_sdk.AsyncModels.generate_content,
        )
        with CaptureContext(name="error_test") as ctx:
            with pytest.raises(RuntimeError, match="quota exceeded"), GeminiAdapter():
                if asynchronous:
                    await resource.generate_content(model="gemini-2.5-flash", contents="Hello")
                else:
                    resource.generate_content(model="gemini-2.5-flash", contents="Hello")
        [span] = ctx.cassette.get_llm_calls()
        assert span.error == "quota exceeded"
        assert span.input == "Hello"
        assert fake_sdk.Models.generate_content is sync
        assert fake_sdk.AsyncModels.generate_content is asynchronous_method

    def test_no_context_leaves_response_unchanged(self, fake_sdk):
        resource = fake_sdk.Models()
        with GeminiAdapter():
            assert (
                resource.generate_content(model="gemini-2.5-flash", contents="Hello")
                is resource.reply
            )

    def test_nested_adapter_refused_without_losing_outer_capture(self, fake_sdk):
        with CaptureContext(name="nested_test") as ctx, GeminiAdapter():
            with pytest.raises(RuntimeError, match="must not be nested"), GeminiAdapter():
                pass
            fake_sdk.Models().generate_content(model="gemini-2.5-flash", contents="Hello")
        assert len(ctx.cassette.get_llm_calls()) == 1


@pytest.mark.parametrize("asynchronous", [False, True])
async def test_real_sdk_with_mock_http_transport(asynchronous):
    """Exercise real SDK resource classes without API credentials or network."""
    genai = pytest.importorskip("google.genai")
    httpx = pytest.importorskip("httpx")
    from google.genai import types

    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [
                                {"text": "Local HTTP result"},
                                {
                                    "functionCall": {
                                        "name": "get_weather",
                                        "args": {"city": "Paris"},
                                    }
                                },
                            ],
                        },
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 100,
                    "cachedContentTokenCount": 80,
                    "candidatesTokenCount": 20,
                    "thoughtsTokenCount": 5,
                },
            },
        )

    transport = httpx.MockTransport(respond)
    client = genai.Client(
        api_key="not-a-real-key",
        http_options=types.HttpOptions(
            client_args={"transport": transport},
            async_client_args={"transport": transport},
        ),
    )
    try:
        with CaptureContext(name="real_sdk_mock") as ctx, GeminiAdapter():
            kwargs = {
                "model": "gemini-2.5-flash",
                "contents": types.Content(
                    role="user",
                    parts=[types.Part.from_text(text="Weather?")],
                ),
            }
            if asynchronous:
                await client.aio.models.generate_content(**kwargs)
            else:
                client.models.generate_content(**kwargs)
        [span] = ctx.cassette.get_llm_calls()
        assert span.input == "user: Weather?"
        assert span.output == "Local HTTP result [function_call:get_weather({'city': 'Paris'})]"
        assert span.token_usage.prompt_tokens == 20
        assert span.token_usage.cache_read_tokens == 80
        assert span.token_usage.completion_tokens == 25
        assert span.token_usage.total_tokens == 125
        assert len(requests) == 1
    finally:
        client.close()
        await client.aio.aclose()
