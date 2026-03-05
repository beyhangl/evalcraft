# pytest Plugin

Evalcraft ships a native pytest plugin that provides fixtures, markers, and terminal reporting for agent evaluation.

## Installation

```bash
pip install "evalcraft[pytest]"
```

The plugin registers automatically via the `pytest11` entry point — no configuration needed.

---

## Fixtures

### `capture_context`

Provides an active `CaptureContext` for the duration of the test. All `MockLLM` and `MockTool` calls inside the test are automatically recorded.

```python
def test_agent(capture_context, mock_llm):
    mock_llm.add_response("*", "4")
    mock_llm.complete("What is 2+2?")
    assert capture_context.cassette.llm_call_count == 1
```

When combined with `@pytest.mark.evalcraft_capture(save=True)` (the default), the cassette is written to disk in `evalcraft_cassette_dir` after the test finishes — even on failure.

```python
@pytest.mark.evalcraft_capture(name="math_agent_test")
def test_math(capture_context, mock_llm):
    mock_llm.add_response("*", "4")
    mock_llm.complete("What is 2+2?")
    assert capture_context.cassette.llm_call_count == 1
    # Cassette saved to tests/cassettes/math_agent_test.json
```

### `mock_llm`

Returns a fresh `MockLLM` instance. Automatically records calls into the active capture context.

```python
def test_agent(mock_llm):
    mock_llm.add_response("What is 2+2?", "4")
    result = mock_llm.complete("What is 2+2?")
    assert result.content == "4"
```

### `mock_tool`

Factory fixture for creating `MockTool` instances. Call it with the tool name.

```python
def test_agent(mock_tool):
    search = mock_tool("web_search")
    search.returns({"results": [{"title": "Python", "url": "https://python.org"}]})

    result = search(query="Python tutorial")
    assert result["results"][0]["title"] == "Python"
    search.assert_called_with(query="Python tutorial")
```

Multiple tools in one test:

```python
def test_multi_tool(mock_tool, capture_context):
    weather = mock_tool("get_weather")
    weather.returns({"temp": 20, "condition": "clear"})

    email = mock_tool("send_email")
    email.returns({"sent": True})

    capture_context.record_input("Check weather and email me")
    weather_data = weather.call(city="Paris")
    email.call(to="user@example.com", body=str(weather_data))
    capture_context.record_output("Weather checked and email sent.")

    assert capture_context.cassette.tool_call_count == 2
    weather.assert_called(times=1)
    email.assert_called_with(to="user@example.com")
```

### `cassette`

Load a `Cassette` from the path given in `@pytest.mark.evalcraft_cassette`. Skips the test if the cassette file is not found (in `none` record mode).

```python
@pytest.mark.evalcraft_cassette("tests/cassettes/search_agent.json")
def test_replay(cassette):
    assert cassette.output_text == "Here are the results."
    assert cassette.tool_call_count == 1
```

### `replay_engine`

Load a `ReplayEngine` from the path given in `@pytest.mark.evalcraft_cassette`.

```python
@pytest.mark.evalcraft_cassette("tests/cassettes/search_agent.json")
def test_override_tool(replay_engine):
    replay_engine.override_tool_result("web_search", {"results": []})
    run = replay_engine.run()
    assert run.cassette.tool_call_count == 1
```

### `evalcraft_cassette_dir`

Session-scoped fixture returning the `Path` to the cassette directory. Created automatically if it doesn't exist.

```python
def test_custom_dir(evalcraft_cassette_dir):
    print(evalcraft_cassette_dir)  # Path("tests/cassettes")
```

Override with `--cassette-dir`:

```bash
pytest --cassette-dir my_cassettes/
```

---

## Markers

### `@pytest.mark.evalcraft_cassette(path)`

Provide the path to a cassette file for replay-based tests.

```python
@pytest.mark.evalcraft_cassette("tests/cassettes/weather.json")
def test_weather_agent(cassette):
    assert cassette.tool_call_count == 1
    assert "Paris" in cassette.output_text
```

```python
@pytest.mark.evalcraft_cassette("tests/cassettes/weather.json")
def test_with_replay_engine(replay_engine):
    engine = replay_engine
    engine.override_tool_result("get_weather", {"temp": -10, "condition": "blizzard"})
    run = engine.run()
    assert run.cassette.tool_call_count == 1
```

### `@pytest.mark.evalcraft_capture(name=None, save=True)`

Auto-capture the test's agent run and optionally save the cassette.

```python
@pytest.mark.evalcraft_capture(name="research_agent")
def test_research(capture_context, mock_llm, mock_tool):
    search = mock_tool("web_search")
    search.returns({"results": ["result 1", "result 2"]})
    mock_llm.add_response("*", "Here's my summary.")

    capture_context.record_input("Research AI trends")
    search.call(query="AI trends 2026")
    response = mock_llm.complete("Summarize: " + str(search.last_call))
    capture_context.record_output(response.content)

    assert capture_context.cassette.tool_call_count == 1
    # Cassette saved to tests/cassettes/research_agent.json
```

Disable saving:

```python
@pytest.mark.evalcraft_capture(name="temp_test", save=False)
def test_no_save(capture_context, mock_llm):
    mock_llm.add_response("*", "ok")
    mock_llm.complete("ping")
    assert capture_context.cassette.llm_call_count == 1
```

### `@pytest.mark.evalcraft_agent`

Informational marker — tags tests as agent evaluation tests for filtering.

```python
@pytest.mark.evalcraft_agent
def test_weather_agent():
    run = replay("tests/cassettes/weather.json")
    assert run.cassette.tool_call_count == 1
```

Run only agent tests:

```bash
pytest -m evalcraft_agent
```

---

## CLI options

### `--cassette-dir DIR`

Override the cassette storage directory (default: `tests/cassettes`).

```bash
pytest --cassette-dir ci_cassettes/
```

### `--evalcraft-record MODE`

Control cassette recording behavior:

| Mode | Behavior |
|------|----------|
| `none` (default) | Replay-only. Skip test if cassette is missing. |
| `new` | Record cassettes that don't exist yet. |
| `all` | Always re-record (overwrite existing cassettes). |

```bash
# Record new cassettes for tests that don't have one yet
pytest --evalcraft-record=new

# Re-record all cassettes
pytest --evalcraft-record=all
```

---

## Terminal summary

After each test run, Evalcraft appends a compact agent-run metrics table to the terminal output:

```
============================= evalcraft agent run summary =============================
  tests/test_weather.py::test_agent: tokens=135, cost=$0.0008, tools=1, llm_calls=1, latency=450ms, fingerprint=a3f1c2d4
  tests/test_search.py::test_research: tokens=820, cost=$0.0041, tools=3, llm_calls=2, latency=1200ms, fingerprint=b7e2f1a3

  TOTAL: 2 test(s) — 955 tokens, $0.0049 cost, 4 tool call(s)
```

This summary only appears when `capture_context` is used.

---

## conftest.py patterns

### Shared cassette directory

```python
# conftest.py
import pytest

@pytest.fixture(scope="session")
def cassette_base():
    return "tests/cassettes"
```

### Shared agent fixture

```python
# conftest.py
import pytest
from evalcraft import CaptureContext, MockLLM, MockTool

@pytest.fixture
def weather_agent_mocks(mock_llm, mock_tool):
    weather = mock_tool("get_weather")
    weather.returns({"temp": 18, "condition": "cloudy"})
    mock_llm.add_response("*", "It's 18°C and cloudy.")
    return {"llm": mock_llm, "weather": weather}


# In your test file:
def test_agent(capture_context, weather_agent_mocks):
    mocks = weather_agent_mocks
    capture_context.record_input("Weather in Paris?")
    result = mocks["weather"].call(city="Paris")
    response = mocks["llm"].complete(f"Data: {result}")
    capture_context.record_output(response.content)
    assert capture_context.cassette.tool_call_count == 1
```

### Parametrized cassette tests

```python
import pytest
from evalcraft import assert_tool_called, assert_cost_under

@pytest.mark.parametrize("cassette_file", [
    "tests/cassettes/weather.json",
    "tests/cassettes/search.json",
    "tests/cassettes/planner.json",
])
def test_all_agents_within_budget(cassette_file):
    from evalcraft import replay
    run = replay(cassette_file)
    result = assert_cost_under(run, max_usd=0.10)
    assert result.passed, f"{cassette_file}: {result.message}"
```
