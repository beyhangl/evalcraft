# Capture API

The capture module records agent runs into cassettes. Every LLM call, tool invocation, and agent step is stored as a span.

---

## CaptureContext

The central class for capturing agent runs.

```python
from evalcraft.capture.recorder import CaptureContext
# or simply:
from evalcraft import CaptureContext
```

### Constructor

```python
CaptureContext(
    name: str = "",
    agent_name: str = "",
    framework: str = "",
    save_path: str | Path | None = None,
    metadata: dict | None = None,
)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Name for this cassette (appears in reports) |
| `agent_name` | `str` | Name of the agent being tested |
| `framework` | `str` | Framework tag (e.g. `"openai"`, `"langgraph"`) |
| `save_path` | `str \| Path \| None` | If set, the cassette is saved to this path on exit |
| `metadata` | `dict \| None` | Arbitrary key-value metadata stored in the cassette |

### Usage — sync

```python
from evalcraft import CaptureContext

with CaptureContext(
    name="weather_test",
    agent_name="weather_agent",
    framework="openai",
    save_path="tests/cassettes/weather.json",
    metadata={"version": "1.2.0"},
) as ctx:
    ctx.record_input("What's the weather in Paris?")
    ctx.record_tool_call("get_weather", args={"city": "Paris"}, result={"temp": 18})
    ctx.record_output("It's 18°C in Paris.")

cassette = ctx.cassette
print(cassette.tool_call_count)  # 1
print(cassette.fingerprint)       # a3f1c2d4...
```

### Usage — async

```python
async with CaptureContext(name="async_test", save_path="tests/cassettes/async.json") as ctx:
    ctx.record_input("Async query")
    response = await my_async_agent.run("Async query")
    ctx.record_output(response)
```

---

## Recording methods

### `record_input(text)`

Records the user's input to the agent. Sets `cassette.input_text`.

```python
ctx.record_input("What's the weather in Paris?")
```

### `record_output(text)`

Records the agent's final output. Sets `cassette.output_text`.

```python
ctx.record_output("It's 18°C and cloudy in Paris.")
```

### `record_llm_call(...)`

Records an LLM call.

```python
ctx.record_llm_call(
    model="gpt-4o",
    input="User asked about weather. Tool: cloudy 18°C",
    output="It's 18°C and cloudy in Paris right now.",
    duration_ms=320.0,
    prompt_tokens=120,
    completion_tokens=15,
    cost_usd=0.0008,
    metadata={"finish_reason": "stop"},
)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `model` | `str` | Model name (e.g. `"gpt-4o"`, `"claude-3-5-sonnet-20241022"`) |
| `input` | `Any` | Prompt or messages sent to the model |
| `output` | `Any` | Model's response |
| `duration_ms` | `float` | Latency in milliseconds |
| `prompt_tokens` | `int` | Input token count |
| `completion_tokens` | `int` | Output token count |
| `cost_usd` | `float \| None` | Estimated cost in USD |
| `metadata` | `dict \| None` | Extra data (e.g. finish reason) |

Returns the created `Span`.

### `record_tool_call(...)`

Records a tool call.

```python
ctx.record_tool_call(
    tool_name="get_weather",
    args={"city": "Paris"},
    result={"temp": 18, "condition": "cloudy"},
    duration_ms=120.0,
    error=None,
    metadata={"source": "openweather"},
)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `tool_name` | `str` | Name of the tool |
| `args` | `dict \| None` | Arguments passed to the tool |
| `result` | `Any` | Tool's return value |
| `duration_ms` | `float` | Latency in milliseconds |
| `error` | `str \| None` | Error message if the tool failed |
| `metadata` | `dict \| None` | Extra data |

Returns the created `Span`.

### `record_span(span)`

Low-level method to record any `Span` directly.

```python
from evalcraft.core.models import Span, SpanKind

span = Span(
    kind=SpanKind.AGENT_STEP,
    name="planning_step",
    input="User query",
    output="Plan: step1, step2, step3",
    duration_ms=50.0,
)
ctx.record_span(span)
```

---

## `capture` decorator

Wraps a function so its execution is captured automatically.

```python
from evalcraft.capture.recorder import capture

@capture(
    name="weather_agent_test",
    save_path="tests/cassettes/weather.json",
)
def test_weather():
    ctx = get_active_context()
    ctx.record_input("Weather in Paris?")
    # ... run agent ...

# Works with async functions too
@capture(name="async_test")
async def test_async():
    ctx = get_active_context()
    ctx.record_input("Async query")
    # ...
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Cassette name (defaults to function name) |
| `agent_name` | `str` | Agent name tag |
| `framework` | `str` | Framework tag |
| `save_path` | `str \| Path \| None` | Where to save the cassette |
| `metadata` | `dict \| None` | Extra metadata |

---

## Module-level helper functions

These functions operate on the **currently active** `CaptureContext`. They are used by framework adapters and `MockLLM`/`MockTool` to record calls automatically.

### `get_active_context()`

Returns the currently active `CaptureContext`, or `None` if no context is active.

```python
from evalcraft.capture.recorder import get_active_context

ctx = get_active_context()
if ctx:
    print(f"Recording into: {ctx.cassette.name}")
```

### `record_span(span)`

Records a span in the active context. Returns `None` if no context is active.

```python
from evalcraft.capture.recorder import record_span
from evalcraft.core.models import Span, SpanKind

record_span(Span(kind=SpanKind.AGENT_STEP, name="my_step"))
```

### `record_llm_call(**kwargs)`

Convenience wrapper for the active context's `record_llm_call`.

```python
from evalcraft.capture.recorder import record_llm_call

record_llm_call(
    model="gpt-4o",
    input="Hello",
    output="Hi there!",
    prompt_tokens=5,
    completion_tokens=3,
)
```

### `record_tool_call(**kwargs)`

Convenience wrapper for the active context's `record_tool_call`.

```python
from evalcraft.capture.recorder import record_tool_call

record_tool_call(
    tool_name="calculator",
    args={"expression": "2 + 2"},
    result=4,
)
```

---

## Accessing the cassette

After the context exits, the cassette is available via `ctx.cassette`:

```python
with CaptureContext(name="my_test") as ctx:
    ctx.record_input("test")
    ctx.record_output("answer")

cassette = ctx.cassette

print(cassette.name)           # "my_test"
print(cassette.input_text)     # "test"
print(cassette.output_text)    # "answer"
print(cassette.llm_call_count) # 0
print(cassette.tool_call_count)# 0
print(cassette.total_tokens)   # 0
print(cassette.fingerprint)    # e.g. "a3f1c2d4e5b6a7c8"

# All spans
for span in cassette.spans:
    print(span.kind, span.name)
```

---

## Common patterns

### Capturing with an OpenAI adapter

```python
from evalcraft import CaptureContext
from evalcraft.adapters import OpenAIAdapter
import openai

client = openai.OpenAI()

with CaptureContext(name="openai_test", save_path="tests/cassettes/openai.json") as ctx:
    with OpenAIAdapter():  # auto-records all client.chat.completions.create() calls
        ctx.record_input("Summarize the French Revolution")
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Summarize the French Revolution"}],
        )
        ctx.record_output(response.choices[0].message.content)
```

### Saving with explicit path

```python
from pathlib import Path

save_dir = Path("tests/cassettes")
save_dir.mkdir(parents=True, exist_ok=True)

with CaptureContext(
    name="explicit_save",
    save_path=save_dir / "explicit.json",
) as ctx:
    ctx.record_input("test input")
    ctx.record_output("test output")
# File is written when the context exits
```

### Re-using a context outside the with block

The cassette is available immediately after the `with` block exits:

```python
with CaptureContext(name="test") as ctx:
    ctx.record_tool_call("search", args={"q": "evalcraft"}, result=["result1"])

cassette = ctx.cassette
assert cassette.tool_call_count == 1
assert cassette.get_tool_sequence() == ["search"]
```
