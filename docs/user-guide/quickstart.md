# Quickstart

Get Evalcraft running in 5 minutes.

## Install

```bash
pip install "evalcraft[pytest]"
```

## Step 1 — Capture a run

Create a file `record_run.py`:

```python
from evalcraft import CaptureContext

with CaptureContext(
    name="weather_agent_test",
    agent_name="weather_agent",
    save_path="tests/cassettes/weather.json",
) as ctx:
    # Record what the user asked
    ctx.record_input("What's the weather in Paris?")

    # Record a tool call your agent made
    ctx.record_tool_call(
        tool_name="get_weather",
        args={"city": "Paris"},
        result={"temp": 18, "condition": "cloudy"},
        duration_ms=120.0,
    )

    # Record the LLM call
    ctx.record_llm_call(
        model="gpt-4o",
        input="User asked about weather. Tool returned: cloudy 18°C",
        output="It's 18°C and cloudy in Paris right now.",
        prompt_tokens=120,
        completion_tokens=15,
        cost_usd=0.0008,
    )

    # Record the final answer
    ctx.record_output("It's 18°C and cloudy in Paris right now.")

cassette = ctx.cassette
print(f"Captured {cassette.tool_call_count} tool calls")
print(f"Total cost: ${cassette.total_cost_usd:.4f}")
print(f"Fingerprint: {cassette.fingerprint}")
# Captured 1 tool calls
# Total cost: $0.0008
# Fingerprint: a3f1c2d4e5b6a7c8
```

Run it once:

```bash
python record_run.py
```

This creates `tests/cassettes/weather.json`. Commit it to git.

## Step 2 — Replay in tests

Create `tests/test_weather.py`:

```python
from evalcraft import replay, assert_tool_called, assert_tool_order, assert_cost_under

def test_agent_calls_weather_tool():
    run = replay("tests/cassettes/weather.json")
    result = assert_tool_called(run, "get_weather")
    assert result.passed, result.message

def test_agent_passes_city_arg():
    run = replay("tests/cassettes/weather.json")
    result = assert_tool_called(run, "get_weather", with_args={"city": "Paris"})
    assert result.passed, result.message

def test_agent_within_cost_budget():
    run = replay("tests/cassettes/weather.json")
    result = assert_cost_under(run, max_usd=0.01)
    assert result.passed, result.message

def test_agent_output_mentions_paris():
    run = replay("tests/cassettes/weather.json")
    from evalcraft import assert_output_contains
    result = assert_output_contains(run, "Paris")
    assert result.passed, result.message
```

Run the tests:

```bash
pytest tests/test_weather.py -v
# test_agent_calls_weather_tool  PASSED  (12ms, $0.00)
# test_agent_passes_city_arg     PASSED  (8ms,  $0.00)
# test_agent_within_cost_budget  PASSED  (5ms,  $0.00)
# test_agent_output_mentions_paris PASSED (6ms, $0.00)
```

Zero API calls. Zero cost.

## Step 3 — Use mocks for unit tests

Instead of capturing from a live agent, use `MockLLM` and `MockTool` to write fully self-contained tests:

```python
from evalcraft import CaptureContext, MockLLM, MockTool
from evalcraft import assert_tool_called, assert_cost_under

def test_weather_agent_with_mocks():
    # Set up mocks
    llm = MockLLM()
    llm.add_response("*", "It's 22°C and sunny in Paris.")

    weather_tool = MockTool("get_weather")
    weather_tool.returns({"temp": 22, "condition": "sunny"})

    # Run with capture
    with CaptureContext(name="mock_test") as ctx:
        ctx.record_input("Weather in Paris?")
        result = weather_tool.call(city="Paris")
        response = llm.complete(f"Data: {result}")
        ctx.record_output(response.content)

    # Assert
    cassette = ctx.cassette
    assert assert_tool_called(cassette, "get_weather").passed
    weather_tool.assert_called(times=1)
    weather_tool.assert_called_with(city="Paris")
    llm.assert_called(times=1)
```

## Step 4 — Use the pytest plugin

Install and use native pytest fixtures:

```python
# tests/test_with_fixtures.py
import pytest
from evalcraft import assert_tool_called

@pytest.mark.evalcraft_cassette("tests/cassettes/weather.json")
def test_replay_with_fixture(cassette):
    assert cassette.tool_call_count == 1
    result = assert_tool_called(cassette, "get_weather")
    assert result.passed

@pytest.mark.evalcraft_capture(name="capture_test")
def test_with_capture(capture_context, mock_llm, mock_tool):
    search = mock_tool("get_weather")
    search.returns({"temp": 20, "condition": "windy"})
    mock_llm.add_response("*", "It's windy today.")

    result = search.call(city="London")
    response = mock_llm.complete(f"Data: {result}")
    capture_context.record_output(response.content)

    assert capture_context.cassette.tool_call_count == 1
```

## Next steps

- [Concepts](concepts.md) — understand cassettes, spans, and fingerprints
- [Capture API](capture.md) — full `CaptureContext` reference
- [Replay Engine](replay.md) — overrides and diffs
- [Adapters](adapters/openai.md) — auto-capture for OpenAI, Anthropic, LangGraph, CrewAI
- [CLI Reference](cli.md) — capture and diff from the terminal
