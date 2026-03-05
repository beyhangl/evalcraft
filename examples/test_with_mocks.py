"""test_with_mocks.py — pytest test suite using MockLLM and MockTool.

Demonstrates how to test agent logic with zero API calls.
Every test runs in <5ms and costs $0.

Run:
    pytest examples/test_with_mocks.py -v
"""

import pytest
from evalcraft import (
    CaptureContext,
    MockLLM,
    MockTool,
    assert_tool_called,
    assert_tool_order,
    assert_no_tool_called,
    assert_output_contains,
    assert_cost_under,
    assert_token_count_under,
)


# ---------------------------------------------------------------------------
# A toy agent for testing
# ---------------------------------------------------------------------------

def run_research_agent(query: str, llm: MockLLM, search: MockTool, ctx: CaptureContext) -> str:
    """Research agent: search → synthesize → respond."""
    ctx.record_input(query)

    search_result = search.call(query=query)
    synthesis_prompt = f"Query: {query}\nSearch results: {search_result}\nSynthesize an answer."
    response = llm.complete(synthesis_prompt)

    ctx.record_output(response.content)
    return response.content


def run_calculator_agent(expression: str, llm: MockLLM, calc: MockTool, ctx: CaptureContext) -> str:
    """Calculator agent: compute → format → respond."""
    ctx.record_input(expression)

    result = calc.call(expression=expression)
    format_prompt = f"Result of {expression} is {result}. State this clearly."
    response = llm.complete(format_prompt)

    ctx.record_output(response.content)
    return response.content


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_search():
    tool = MockTool("web_search", description="Search the web")
    tool.returns({"results": [{"title": "Python docs", "url": "https://docs.python.org"}]})
    return tool


@pytest.fixture
def mock_llm():
    llm = MockLLM(model="mock-gpt-4o")
    llm.add_response("*", "Here is a synthesized answer based on the search results.")
    return llm


@pytest.fixture
def mock_calc():
    tool = MockTool("calculator")
    tool.returns_fn(lambda expression: eval(expression))  # safe for testing
    return tool


# ---------------------------------------------------------------------------
# Tests: tool call assertions
# ---------------------------------------------------------------------------

class TestToolBehavior:
    def test_search_is_called(self, mock_llm, mock_search):
        with CaptureContext(name="search_called") as ctx:
            run_research_agent("What is Python?", mock_llm, mock_search, ctx)

        result = assert_tool_called(ctx.cassette, "web_search")
        assert result.passed, result.message

    def test_search_called_with_correct_query(self, mock_llm, mock_search):
        query = "What is Python?"
        with CaptureContext(name="search_args") as ctx:
            run_research_agent(query, mock_llm, mock_search, ctx)

        result = assert_tool_called(ctx.cassette, "web_search", with_args={"query": query})
        assert result.passed, result.message

    def test_search_called_exactly_once(self, mock_llm, mock_search):
        with CaptureContext(name="search_once") as ctx:
            run_research_agent("What is Python?", mock_llm, mock_search, ctx)

        result = assert_tool_called(ctx.cassette, "web_search", times=1)
        assert result.passed, result.message

    def test_no_calculator_in_research_agent(self, mock_llm, mock_search):
        with CaptureContext(name="no_calc") as ctx:
            run_research_agent("What is Python?", mock_llm, mock_search, ctx)

        result = assert_no_tool_called(ctx.cassette, "calculator")
        assert result.passed, result.message

    def test_tool_sequence(self, mock_llm, mock_search):
        with CaptureContext(name="tool_order") as ctx:
            run_research_agent("What is Python?", mock_llm, mock_search, ctx)

        result = assert_tool_order(ctx.cassette, ["web_search"])
        assert result.passed, result.message


# ---------------------------------------------------------------------------
# Tests: output assertions
# ---------------------------------------------------------------------------

class TestOutputBehavior:
    def test_output_contains_expected_text(self, mock_llm, mock_search):
        mock_llm.add_response("*", "Python is a high-level programming language.")

        with CaptureContext(name="output_check") as ctx:
            run_research_agent("What is Python?", mock_llm, mock_search, ctx)

        result = assert_output_contains(ctx.cassette, "Python")
        assert result.passed, result.message

    def test_output_case_insensitive(self, mock_llm, mock_search):
        mock_llm.add_response("*", "PYTHON is popular for data science.")

        with CaptureContext(name="case_insensitive") as ctx:
            run_research_agent("What is Python?", mock_llm, mock_search, ctx)

        result = assert_output_contains(ctx.cassette, "python", case_sensitive=False)
        assert result.passed, result.message


# ---------------------------------------------------------------------------
# Tests: cost and performance budgets
# ---------------------------------------------------------------------------

class TestBudgets:
    def test_cost_under_budget(self, mock_llm, mock_search):
        with CaptureContext(name="cost_check") as ctx:
            run_research_agent("What is Python?", mock_llm, mock_search, ctx)

        # MockLLM doesn't accumulate real cost — cassette cost stays $0
        result = assert_cost_under(ctx.cassette, max_usd=0.10)
        assert result.passed, result.message

    def test_token_count_under_budget(self, mock_llm, mock_search):
        with CaptureContext(name="token_check") as ctx:
            run_research_agent("What is Python?", mock_llm, mock_search, ctx)

        result = assert_token_count_under(ctx.cassette, max_tokens=500)
        assert result.passed, result.message


# ---------------------------------------------------------------------------
# Tests: MockLLM features
# ---------------------------------------------------------------------------

class TestMockLLMFeatures:
    def test_exact_match_response(self):
        llm = MockLLM()
        llm.add_response("hello", "world")

        response = llm.complete("hello")
        assert response.content == "world"

    def test_wildcard_fallback(self):
        llm = MockLLM()
        llm.add_response("*", "default answer")

        assert llm.complete("anything here").content == "default answer"
        assert llm.complete("something else").content == "default answer"

    def test_sequential_responses(self):
        llm = MockLLM()
        llm.add_sequential_responses("retry?", ["first", "second", "third"])

        assert llm.complete("retry?").content == "first"
        assert llm.complete("retry?").content == "second"
        assert llm.complete("retry?").content == "third"

    def test_pattern_match_response(self):
        llm = MockLLM()
        llm.add_pattern_response(r"weather in (\w+)", "It's sunny!")

        assert llm.complete("What's the weather in Paris?").content == "It's sunny!"
        assert llm.complete("weather in Tokyo please").content == "It's sunny!"

    def test_call_count_tracking(self):
        llm = MockLLM()
        llm.add_response("*", "ok")

        llm.complete("one")
        llm.complete("two")
        llm.complete("three")

        assert llm.call_count == 3
        llm.assert_called(times=3)

    def test_assert_called_with(self):
        llm = MockLLM()
        llm.add_response("*", "ok")

        llm.complete("specific prompt here")

        llm.assert_called_with("specific prompt here")

    def test_custom_response_function(self):
        from evalcraft.mock.llm import MockResponse

        llm = MockLLM()
        llm.set_response_fn(lambda prompt: MockResponse(
            content=f"Echo: {prompt}",
            prompt_tokens=len(prompt.split()),
            completion_tokens=3,
        ))

        response = llm.complete("hello world")
        assert response.content == "Echo: hello world"
        assert response.prompt_tokens == 2


# ---------------------------------------------------------------------------
# Tests: MockTool features
# ---------------------------------------------------------------------------

class TestMockToolFeatures:
    def test_static_return(self):
        tool = MockTool("file_reader")
        tool.returns({"content": "Hello, world!"})

        result = tool.call(path="test.txt")
        assert result == {"content": "Hello, world!"}

    def test_dynamic_return(self):
        tool = MockTool("upper_case")
        tool.returns_fn(lambda text: text.upper())

        assert tool.call(text="hello") == "HELLO"
        assert tool.call(text="world") == "WORLD"

    def test_sequential_returns(self):
        tool = MockTool("paginated_api")
        tool.returns_sequence([
            {"page": 1, "data": ["a", "b"]},
            {"page": 2, "data": ["c", "d"]},
            {"page": 3, "data": []},
        ])

        assert tool.call()["page"] == 1
        assert tool.call()["page"] == 2
        assert tool.call()["page"] == 3

    def test_error_simulation(self):
        from evalcraft.mock.tool import ToolError

        tool = MockTool("flaky_api")
        tool.raises("Service unavailable")

        with pytest.raises(ToolError, match="Service unavailable"):
            tool.call()

    def test_error_after_n_calls(self):
        from evalcraft.mock.tool import ToolError

        tool = MockTool("rate_limited_api")
        tool.returns({"data": "ok"})
        tool.raises_after(2, "Rate limit exceeded")

        assert tool.call()["data"] == "ok"  # call 1: ok
        assert tool.call()["data"] == "ok"  # call 2: ok
        with pytest.raises(ToolError, match="Rate limit exceeded"):
            tool.call()  # call 3: error

    def test_assert_called_with_args(self):
        tool = MockTool("search")
        tool.returns([])

        tool.call(query="Python", limit=10)

        tool.assert_called_with(query="Python")
        tool.assert_called_with(query="Python", limit=10)

    def test_assert_not_called(self):
        tool = MockTool("unused_tool")
        tool.assert_not_called()

    def test_callable_syntax(self):
        """MockTool supports direct __call__ syntax."""
        tool = MockTool("db_query")
        tool.returns([{"id": 1, "name": "Alice"}])

        result = tool(table="users", limit=1)
        assert result[0]["name"] == "Alice"
