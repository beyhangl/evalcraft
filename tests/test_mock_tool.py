"""Tests for evalcraft.mock.tool."""

import pytest
from evalcraft.mock.tool import MockTool, ToolError
from evalcraft.capture.recorder import CaptureContext
from evalcraft.core.models import SpanKind


# ──────────────────────────────────────────────
# MockTool construction
# ──────────────────────────────────────────────

class TestMockToolConstruction:
    def test_name_and_description(self):
        tool = MockTool("search", "Search the web")
        assert tool.name == "search"
        assert tool.description == "Search the web"

    def test_initial_call_count_zero(self):
        tool = MockTool("test")
        assert tool.call_count == 0

    def test_initial_call_history_empty(self):
        tool = MockTool("test")
        assert tool.call_history == []

    def test_last_call_initially_none(self):
        tool = MockTool("test")
        assert tool.last_call is None


# ──────────────────────────────────────────────
# returns()
# ──────────────────────────────────────────────

class TestReturns:
    def test_static_return_value(self):
        tool = MockTool("search")
        tool.returns({"results": ["a", "b"]})
        assert tool.call() == {"results": ["a", "b"]}

    def test_returns_none_by_default(self):
        tool = MockTool("noop")
        assert tool.call() is None

    def test_returns_chaining(self):
        tool = MockTool("t")
        result = tool.returns(42)
        assert result is tool

    def test_returns_complex_value(self):
        tool = MockTool("t")
        tool.returns({"nested": {"key": [1, 2, 3]}})
        assert tool.call()["nested"]["key"] == [1, 2, 3]


# ──────────────────────────────────────────────
# returns_fn()
# ──────────────────────────────────────────────

class TestReturnsFn:
    def test_fn_receives_kwargs(self):
        tool = MockTool("calculator")
        tool.returns_fn(lambda a, b: a + b)
        assert tool.call(a=3, b=4) == 7

    def test_fn_overrides_returns(self):
        tool = MockTool("t")
        tool.returns("static")
        tool.returns_fn(lambda: "dynamic")
        assert tool.call() == "dynamic"

    def test_returns_fn_chaining(self):
        tool = MockTool("t")
        result = tool.returns_fn(lambda: None)
        assert result is tool


# ──────────────────────────────────────────────
# returns_sequence()
# ──────────────────────────────────────────────

class TestReturnsSequence:
    def test_sequential_values(self):
        tool = MockTool("t")
        tool.returns_sequence([10, 20, 30])
        assert tool.call() == 10
        assert tool.call() == 20
        assert tool.call() == 30

    def test_stays_at_last_when_exhausted(self):
        tool = MockTool("t")
        tool.returns_sequence(["a", "b"])
        tool.call()
        tool.call()
        assert tool.call() == "b"

    def test_returns_sequence_chaining(self):
        tool = MockTool("t")
        result = tool.returns_sequence([1])
        assert result is tool


# ──────────────────────────────────────────────
# raises() and raises_after()
# ──────────────────────────────────────────────

class TestRaises:
    def test_raises_on_call(self):
        tool = MockTool("broken")
        tool.raises("Something went wrong")
        with pytest.raises(ToolError, match="Something went wrong"):
            tool.call()

    def test_raises_chaining(self):
        tool = MockTool("t")
        result = tool.raises("err")
        assert result is tool

    def test_raises_after_n_calls(self):
        tool = MockTool("flaky")
        tool.returns("ok")
        tool.raises_after(2, "Flaky error")
        assert tool.call() == "ok"  # call 0 succeeds
        assert tool.call() == "ok"  # call 1 succeeds
        with pytest.raises(ToolError, match="Flaky error"):
            tool.call()  # call 2 fails

    def test_raises_after_chaining(self):
        tool = MockTool("t")
        result = tool.raises_after(1, "err")
        assert result is tool

    def test_call_history_includes_error(self):
        tool = MockTool("broken")
        tool.raises("error msg")
        with pytest.raises(ToolError):
            tool.call(key="val")
        assert tool.call_history[0]["error"] == "error msg"
        assert tool.call_history[0]["args"] == {"key": "val"}


# ──────────────────────────────────────────────
# with_latency()
# ──────────────────────────────────────────────

class TestWithLatency:
    def test_with_latency_chaining(self):
        tool = MockTool("t")
        result = tool.with_latency(0.0)
        assert result is tool

    def test_latency_is_stored(self):
        tool = MockTool("t")
        tool.with_latency(100.0)
        assert tool._latency_ms == 100.0


# ──────────────────────────────────────────────
# call() and __call__()
# ──────────────────────────────────────────────

class TestCall:
    def test_call_increments_count(self):
        tool = MockTool("t")
        tool.call()
        tool.call()
        assert tool.call_count == 2

    def test_call_records_args(self):
        tool = MockTool("search")
        tool.returns({"results": []})
        tool.call(query="test", limit=5)
        assert tool.call_history[0]["args"] == {"query": "test", "limit": 5}

    def test_call_records_result(self):
        tool = MockTool("t")
        tool.returns(42)
        tool.call()
        assert tool.call_history[0]["result"] == 42

    def test_dunder_call(self):
        tool = MockTool("t")
        tool.returns("result")
        assert tool(key="value") == "result"

    def test_last_call_reflects_most_recent(self):
        tool = MockTool("t")
        tool.returns("x")
        tool.call(a=1)
        tool.call(a=2)
        assert tool.last_call["args"] == {"a": 2}


# ──────────────────────────────────────────────
# reset()
# ──────────────────────────────────────────────

class TestReset:
    def test_reset_clears_count(self):
        tool = MockTool("t")
        tool.call()
        tool.reset()
        assert tool.call_count == 0

    def test_reset_clears_history(self):
        tool = MockTool("t")
        tool.call()
        tool.reset()
        assert tool.call_history == []

    def test_last_call_none_after_reset(self):
        tool = MockTool("t")
        tool.call()
        tool.reset()
        assert tool.last_call is None


# ──────────────────────────────────────────────
# Assertions
# ──────────────────────────────────────────────

class TestMockToolAssertions:
    def test_assert_called_passes(self):
        tool = MockTool("t")
        tool.call()
        tool.assert_called()

    def test_assert_called_raises_if_never_called(self):
        tool = MockTool("t")
        with pytest.raises(AssertionError, match="never called"):
            tool.assert_called()

    def test_assert_called_times(self):
        tool = MockTool("t")
        tool.call()
        tool.call()
        tool.assert_called(times=2)

    def test_assert_called_times_fails(self):
        tool = MockTool("t")
        tool.call()
        with pytest.raises(AssertionError):
            tool.assert_called(times=5)

    def test_assert_called_with_passes(self):
        tool = MockTool("search")
        tool.returns({})
        tool.call(query="python", limit=10)
        tool.assert_called_with(query="python")

    def test_assert_called_with_partial_args(self):
        tool = MockTool("t")
        tool.call(a=1, b=2, c=3)
        tool.assert_called_with(b=2)  # only check b

    def test_assert_called_with_fails(self):
        tool = MockTool("t")
        tool.call(a=1)
        with pytest.raises(AssertionError, match="never called with"):
            tool.assert_called_with(a=99)

    def test_assert_not_called_passes(self):
        tool = MockTool("t")
        tool.assert_not_called()

    def test_assert_not_called_fails(self):
        tool = MockTool("t")
        tool.call()
        with pytest.raises(AssertionError):
            tool.assert_not_called()


# ──────────────────────────────────────────────
# Integration with capture context
# ──────────────────────────────────────────────

class TestMockToolWithCapture:
    def test_records_to_capture_context(self):
        tool = MockTool("search")
        tool.returns({"results": ["a"]})
        with CaptureContext() as ctx:
            tool.call(query="test")
        assert len(ctx.cassette.spans) == 1
        span = ctx.cassette.spans[0]
        assert span.kind == SpanKind.TOOL_CALL
        assert span.tool_name == "search"
        assert span.tool_args == {"query": "test"}
        assert span.tool_result == {"results": ["a"]}

    def test_error_span_recorded(self):
        tool = MockTool("broken")
        tool.raises("oops")
        with CaptureContext() as ctx:
            with pytest.raises(ToolError):
                tool.call()
        span = ctx.cassette.spans[0]
        assert span.error == "oops"

    def test_no_error_outside_context(self):
        tool = MockTool("t")
        tool.returns(42)
        result = tool.call()
        assert result == 42


# ──────────────────────────────────────────────
# ToolError
# ──────────────────────────────────────────────

class TestToolError:
    def test_is_exception(self):
        assert issubclass(ToolError, Exception)

    def test_has_message(self):
        err = ToolError("something failed")
        assert str(err) == "something failed"
