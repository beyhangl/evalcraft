# Mock LLM & Tools

Evalcraft provides two mock classes for deterministic testing without real API calls: `MockLLM` and `MockTool`.

Both automatically record their calls into the active `CaptureContext` if one is running.

---

## MockLLM

A deterministic mock LLM for testing agent logic.

```python
from evalcraft import MockLLM
# or:
from evalcraft.mock.llm import MockLLM
```

### Constructor

```python
MockLLM(
    model: str = "mock-llm",
    default_response: str = "",
)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `model` | `str` | Model name reported in captured spans |
| `default_response` | `str` | Fallback response when no match is found |

---

### Adding responses

#### `add_response(prompt, content, ...)`

Add a response for an exact prompt or a wildcard `"*"`.

```python
mock = MockLLM()

# Exact match
mock.add_response("What is 2+2?", "4")

# Wildcard — matches anything not matched exactly
mock.add_response("*", "I don't know.")

result = mock.complete("What is 2+2?")
print(result.content)  # "4"

result = mock.complete("Some other question")
print(result.content)  # "I don't know."
```

**Chaining:**

```python
mock = (
    MockLLM()
    .add_response("Hello", "Hi there!")
    .add_response("Bye", "Goodbye!")
    .add_response("*", "...")
)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `prompt` | `str` | Exact prompt to match, or `"*"` for wildcard |
| `content` | `str` | Response content to return |
| `prompt_tokens` | `int` | Simulated prompt token count (default: 10) |
| `completion_tokens` | `int` | Simulated completion token count (default: 20) |
| `tool_calls` | `list[dict] \| None` | Optional tool calls in the response |

#### `add_pattern_response(pattern, content, ...)`

Match prompts using a regex pattern.

```python
mock = MockLLM()
mock.add_pattern_response(r"weather in (\w+)", "It's sunny there.")
mock.add_pattern_response(r"translate .+ to French", "Voilà!")

result = mock.complete("What's the weather in London?")
print(result.content)  # "It's sunny there."
```

Patterns are case-insensitive.

#### `add_sequential_responses(prompt, contents)`

Return different responses on successive calls for the same prompt.

```python
mock = MockLLM()
mock.add_sequential_responses("Next step?", [
    "Step 1: Search",
    "Step 2: Analyze",
    "Step 3: Report",
])

print(mock.complete("Next step?").content)  # "Step 1: Search"
print(mock.complete("Next step?").content)  # "Step 2: Analyze"
print(mock.complete("Next step?").content)  # "Step 3: Report"
print(mock.complete("Next step?").content)  # "Step 3: Report" (last repeated)
```

#### `set_response_fn(fn)`

Use a custom function to generate responses dynamically.

```python
def my_fn(prompt: str) -> MockResponse:
    from evalcraft.mock.llm import MockResponse
    return MockResponse(content=f"Echo: {prompt}", prompt_tokens=5, completion_tokens=10)

mock = MockLLM()
mock.set_response_fn(my_fn)

result = mock.complete("Hello world")
print(result.content)  # "Echo: Hello world"
```

---

### Calling the mock

#### `complete(prompt, **kwargs)`

Get a mock completion.

```python
result = mock.complete("What is 2+2?")
print(result.content)           # "4"
print(result.model)             # "mock-llm"
print(result.prompt_tokens)     # 10
print(result.completion_tokens) # 20
print(result.total_tokens)      # 30
print(result.finish_reason)     # "stop"
print(result.tool_calls)        # None
```

If a `CaptureContext` is active, the call is automatically recorded as an LLM span.

---

### `MockResponse` fields

| Field | Type | Description |
|-------|------|-------------|
| `content` | `str` | Response text |
| `model` | `str` | Model name |
| `prompt_tokens` | `int` | Simulated input tokens |
| `completion_tokens` | `int` | Simulated output tokens |
| `total_tokens` | `int` | Sum of prompt + completion |
| `finish_reason` | `str` | `"stop"` by default |
| `tool_calls` | `list[dict] \| None` | Optional tool calls |

---

### Assertions and inspection

#### `assert_called(times=None)`

Assert the mock was called at least once, or exactly `times` times.

```python
mock.assert_called()         # at least once
mock.assert_called(times=3)  # exactly 3 times
```

Raises `AssertionError` if the assertion fails.

#### `assert_called_with(prompt)`

Assert the mock was called with a specific prompt at least once.

```python
mock.assert_called_with("What is 2+2?")
```

#### `call_count`

Number of times `complete()` was called.

```python
print(mock.call_count)  # e.g. 3
```

#### `call_history`

List of all calls made, each as `{"prompt": ..., "response": ..., "kwargs": ...}`.

```python
for call in mock.call_history:
    print(call["prompt"], "→", call["response"])
```

#### `reset()`

Reset call history and count.

```python
mock.reset()
print(mock.call_count)  # 0
```

---

## MockTool

A deterministic mock tool for testing agent tool interactions.

```python
from evalcraft import MockTool
# or:
from evalcraft.mock.tool import MockTool
```

### Constructor

```python
MockTool(
    name: str,
    description: str = "",
)
```

```python
search = MockTool("web_search", description="Search the web")
calculator = MockTool("calculator")
```

---

### Setting return values

#### `returns(value)`

Set a static return value.

```python
search = MockTool("web_search")
search.returns({"results": [{"title": "Python docs", "url": "https://docs.python.org"}]})

result = search.call(query="Python")
print(result["results"][0]["title"])  # "Python docs"
```

Returns `self` for chaining.

#### `returns_fn(fn)`

Set a dynamic return function.

```python
def weather_fn(city: str = "", **kwargs):
    temps = {"Paris": 18, "London": 12, "Tokyo": 25}
    return {"temp": temps.get(city, 20), "condition": "sunny"}

tool = MockTool("get_weather")
tool.returns_fn(weather_fn)

print(tool.call(city="Paris")["temp"])   # 18
print(tool.call(city="Tokyo")["temp"])   # 25
print(tool.call(city="Berlin")["temp"])  # 20 (default)
```

#### `returns_sequence(values)`

Return different values on successive calls.

```python
search = MockTool("search")
search.returns_sequence([
    {"results": ["first result"]},
    {"results": ["second result"]},
    {"results": []},
])

print(search.call(q="test")["results"])  # ["first result"]
print(search.call(q="test")["results"])  # ["second result"]
print(search.call(q="test")["results"])  # []
print(search.call(q="test")["results"])  # [] (last repeated)
```

---

### Simulating errors

#### `raises(error)`

Always raise an error.

```python
from evalcraft.mock.tool import ToolError

tool = MockTool("flaky_api")
tool.raises("Connection timeout")

try:
    tool.call(endpoint="/data")
except ToolError as e:
    print(str(e))  # "Connection timeout"
```

#### `raises_after(n_calls, error)`

Succeed for the first N calls, then raise.

```python
tool = MockTool("rate_limited_api")
tool.returns({"data": "ok"})
tool.raises_after(2, "Rate limit exceeded")

print(tool.call())  # {"data": "ok"}
print(tool.call())  # {"data": "ok"}
# tool.call()  # raises ToolError: "Rate limit exceeded"
```

---

### Simulating latency

#### `with_latency(ms)`

Add artificial latency to simulate slow tools.

```python
slow_tool = MockTool("slow_database")
slow_tool.returns({"rows": [1, 2, 3]})
slow_tool.with_latency(200)  # 200ms delay

result = slow_tool.call()  # takes ~200ms
```

---

### Calling the tool

#### `call(**kwargs)`

Execute the mock tool.

```python
search = MockTool("web_search")
search.returns({"results": ["result 1", "result 2"]})

result = search.call(query="evalcraft", limit=5)
print(result)  # {"results": ["result 1", "result 2"]}
```

If a `CaptureContext` is active, the call is automatically recorded as a tool span.

#### Direct call syntax

`MockTool` is also callable directly:

```python
result = search(query="evalcraft")  # same as search.call(query="evalcraft")
```

---

### Assertions and inspection

#### `assert_called(times=None)`

```python
search.assert_called()         # at least once
search.assert_called(times=2)  # exactly twice
```

#### `assert_called_with(**expected_kwargs)`

Assert the tool was called with specific keyword arguments at least once.

```python
search.assert_called_with(query="evalcraft")
search.assert_called_with(query="evalcraft", limit=5)
```

#### `assert_not_called()`

Assert the tool was never called.

```python
email_tool.assert_not_called()
```

#### `call_count`, `call_history`, `last_call`

```python
print(tool.call_count)    # number of calls
print(tool.call_history)  # list of {"args": ..., "result": ..., "error": ...}
print(tool.last_call)     # most recent call dict, or None
```

#### `reset()`

Reset call history and count.

```python
tool.reset()
```

---

## Using mocks with CaptureContext

Both `MockLLM` and `MockTool` automatically record their calls when a `CaptureContext` is active:

```python
from evalcraft import CaptureContext, MockLLM, MockTool

llm = MockLLM()
llm.add_response("*", "The weather is fine.")

weather = MockTool("get_weather")
weather.returns({"temp": 22, "condition": "sunny"})

with CaptureContext(name="test_with_mocks", save_path="tests/cassettes/mocks.json") as ctx:
    ctx.record_input("Weather in Paris?")

    # Both calls are auto-recorded as spans
    result = weather.call(city="Paris")
    response = llm.complete(f"Weather data: {result}")

    ctx.record_output(response.content)

cassette = ctx.cassette
assert cassette.tool_call_count == 1
assert cassette.llm_call_count == 1
assert cassette.get_tool_sequence() == ["get_weather"]
```

---

## ToolError

`ToolError` is raised by `MockTool.call()` when the tool is configured to raise an error.

```python
from evalcraft.mock.tool import ToolError

tool = MockTool("risky_tool")
tool.raises("Permission denied")

try:
    tool.call(resource="secret")
except ToolError as e:
    print(e)  # "Permission denied"
```
