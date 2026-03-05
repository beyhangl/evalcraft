"""Tests for evalcraft.mock.llm."""

import pytest
from evalcraft.mock.llm import MockLLM, MockResponse
from evalcraft.capture.recorder import CaptureContext
from evalcraft.core.models import SpanKind


# ──────────────────────────────────────────────
# MockResponse
# ──────────────────────────────────────────────

class TestMockResponse:
    def test_total_tokens_property(self):
        r = MockResponse(prompt_tokens=10, completion_tokens=5)
        assert r.total_tokens == 15

    def test_defaults(self):
        r = MockResponse()
        assert r.content == ""
        assert r.model == "mock-llm"
        assert r.finish_reason == "stop"
        assert r.tool_calls is None


# ──────────────────────────────────────────────
# MockLLM construction
# ──────────────────────────────────────────────

class TestMockLLMConstruction:
    def test_default_model(self):
        llm = MockLLM()
        assert llm.model == "mock-llm"

    def test_custom_model(self):
        llm = MockLLM(model="gpt-4-turbo")
        assert llm.model == "gpt-4-turbo"

    def test_initial_call_count_zero(self):
        llm = MockLLM()
        assert llm.call_count == 0

    def test_initial_call_history_empty(self):
        llm = MockLLM()
        assert llm.call_history == []


# ──────────────────────────────────────────────
# add_response — exact match
# ──────────────────────────────────────────────

class TestExactMatchResponse:
    def test_exact_prompt_match(self):
        llm = MockLLM()
        llm.add_response("hello", "world")
        response = llm.complete("hello")
        assert response.content == "world"

    def test_no_match_returns_default(self):
        llm = MockLLM(default_response="fallback")
        response = llm.complete("unknown prompt")
        assert response.content == "fallback"

    def test_token_counts_in_response(self):
        llm = MockLLM()
        llm.add_response("prompt", "answer", prompt_tokens=100, completion_tokens=50)
        r = llm.complete("prompt")
        assert r.prompt_tokens == 100
        assert r.completion_tokens == 50

    def test_tool_calls_in_response(self):
        llm = MockLLM()
        tool_calls = [{"name": "search", "args": {"q": "test"}}]
        llm.add_response("search for me", "ok", tool_calls=tool_calls)
        r = llm.complete("search for me")
        assert r.tool_calls == tool_calls

    def test_add_response_returns_self_for_chaining(self):
        llm = MockLLM()
        result = llm.add_response("a", "b")
        assert result is llm


# ──────────────────────────────────────────────
# Wildcard responses
# ──────────────────────────────────────────────

class TestWildcardResponse:
    def test_wildcard_matches_any_prompt(self):
        llm = MockLLM()
        llm.add_response("*", "I don't know")
        assert llm.complete("anything").content == "I don't know"
        assert llm.complete("something else").content == "I don't know"

    def test_exact_match_preferred_over_wildcard(self):
        llm = MockLLM()
        llm.add_response("*", "wildcard response")
        llm.add_response("specific", "specific response")
        assert llm.complete("specific").content == "specific response"
        assert llm.complete("other").content == "wildcard response"


# ──────────────────────────────────────────────
# Pattern responses
# ──────────────────────────────────────────────

class TestPatternResponse:
    def test_pattern_match(self):
        llm = MockLLM()
        llm.add_pattern_response(r"weather.*city", "It's sunny")
        assert llm.complete("weather in the city").content == "It's sunny"

    def test_pattern_case_insensitive(self):
        llm = MockLLM()
        llm.add_pattern_response(r"hello", "hi there")
        assert llm.complete("HELLO world").content == "hi there"

    def test_no_pattern_match_uses_default(self):
        llm = MockLLM(default_response="default")
        llm.add_pattern_response(r"foo", "bar")
        assert llm.complete("baz").content == "default"

    def test_add_pattern_response_returns_self(self):
        llm = MockLLM()
        result = llm.add_pattern_response(r".*", "anything")
        assert result is llm


# ──────────────────────────────────────────────
# Sequential responses
# ──────────────────────────────────────────────

class TestSequentialResponses:
    def test_sequential_returns_in_order(self):
        llm = MockLLM()
        llm.add_sequential_responses("q", ["first", "second", "third"])
        assert llm.complete("q").content == "first"
        assert llm.complete("q").content == "second"
        assert llm.complete("q").content == "third"

    def test_sequential_stays_at_last_when_exhausted(self):
        llm = MockLLM()
        llm.add_sequential_responses("q", ["a", "b"])
        llm.complete("q")
        llm.complete("q")
        # Third call should still return "b" (last item)
        assert llm.complete("q").content == "b"

    def test_sequential_wildcard(self):
        llm = MockLLM()
        llm.add_sequential_responses("*", ["one", "two"])
        assert llm.complete("anything").content == "one"
        assert llm.complete("other").content == "two"

    def test_add_sequential_returns_self(self):
        llm = MockLLM()
        result = llm.add_sequential_responses("q", ["a"])
        assert result is llm


# ──────────────────────────────────────────────
# Custom response function
# ──────────────────────────────────────────────

class TestResponseFunction:
    def test_custom_fn_called_with_prompt(self):
        llm = MockLLM()
        received = []

        def my_fn(prompt):
            received.append(prompt)
            return MockResponse(content=f"echo: {prompt}")

        llm.set_response_fn(my_fn)
        r = llm.complete("test prompt")
        assert r.content == "echo: test prompt"
        assert received == ["test prompt"]

    def test_fn_takes_priority_over_exact(self):
        llm = MockLLM()
        llm.add_response("hi", "exact response")
        llm.set_response_fn(lambda p: MockResponse(content="fn response"))
        assert llm.complete("hi").content == "fn response"

    def test_set_response_fn_returns_self(self):
        llm = MockLLM()
        result = llm.set_response_fn(lambda p: MockResponse())
        assert result is llm


# ──────────────────────────────────────────────
# Call tracking
# ──────────────────────────────────────────────

class TestCallTracking:
    def test_call_count_increments(self):
        llm = MockLLM()
        llm.add_response("*", "ok")
        llm.complete("a")
        llm.complete("b")
        assert llm.call_count == 2

    def test_call_history_records_all(self):
        llm = MockLLM()
        llm.add_response("*", "ok")
        llm.complete("prompt1")
        llm.complete("prompt2")
        assert len(llm.call_history) == 2
        assert llm.call_history[0]["prompt"] == "prompt1"
        assert llm.call_history[1]["prompt"] == "prompt2"

    def test_reset_clears_history_and_count(self):
        llm = MockLLM()
        llm.add_response("*", "ok")
        llm.complete("test")
        llm.reset()
        assert llm.call_count == 0
        assert llm.call_history == []


# ──────────────────────────────────────────────
# Assertions
# ──────────────────────────────────────────────

class TestMockLLMAssertions:
    def test_assert_called_passes(self):
        llm = MockLLM()
        llm.add_response("*", "ok")
        llm.complete("test")
        llm.assert_called()

    def test_assert_called_raises_if_never_called(self):
        llm = MockLLM()
        with pytest.raises(AssertionError, match="never called"):
            llm.assert_called()

    def test_assert_called_times(self):
        llm = MockLLM()
        llm.add_response("*", "ok")
        llm.complete("a")
        llm.complete("b")
        llm.assert_called(times=2)

    def test_assert_called_times_fails(self):
        llm = MockLLM()
        llm.add_response("*", "ok")
        llm.complete("a")
        with pytest.raises(AssertionError):
            llm.assert_called(times=3)

    def test_assert_called_with_passes(self):
        llm = MockLLM()
        llm.add_response("*", "ok")
        llm.complete("specific prompt")
        llm.assert_called_with("specific prompt")

    def test_assert_called_with_fails(self):
        llm = MockLLM()
        llm.add_response("*", "ok")
        llm.complete("actual prompt")
        with pytest.raises(AssertionError, match="never called with"):
            llm.assert_called_with("different prompt")


# ──────────────────────────────────────────────
# Integration with capture context
# ──────────────────────────────────────────────

class TestMockLLMWithCapture:
    def test_records_to_capture_context(self):
        llm = MockLLM()
        llm.add_response("hello", "world", prompt_tokens=5, completion_tokens=3)
        with CaptureContext() as ctx:
            llm.complete("hello")
        assert len(ctx.cassette.spans) == 1
        span = ctx.cassette.spans[0]
        assert span.kind == SpanKind.LLM_RESPONSE
        assert span.model == "mock-llm"

    def test_no_error_outside_context(self):
        llm = MockLLM()
        llm.add_response("*", "ok")
        # Should not raise even without active context
        result = llm.complete("test")
        assert result.content == "ok"
