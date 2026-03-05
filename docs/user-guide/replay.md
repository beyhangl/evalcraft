# Replay Engine

The replay engine loads a recorded cassette and feeds the recorded responses back deterministically — no API calls, zero cost.

---

## Quick replay

The simplest way to replay is the `replay()` convenience function:

```python
from evalcraft import replay

run = replay("tests/cassettes/weather.json")

print(run.replayed)                    # True
print(run.cassette.output_text)        # "It's 18°C and cloudy in Paris."
print(run.cassette.tool_call_count)    # 1
print(run.cassette.get_tool_sequence())# ["get_weather"]
```

### With tool overrides

```python
from evalcraft import replay

run = replay(
    "tests/cassettes/weather.json",
    tool_overrides={"get_weather": {"temp": 5, "condition": "snow"}},
)
```

### `replay()` signature

```python
replay(
    cassette_path: str | Path,
    tool_overrides: dict[str, Any] | None = None,
) -> AgentRun
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `cassette_path` | `str \| Path` | Path to a cassette JSON file |
| `tool_overrides` | `dict \| None` | Map of `tool_name → new_result` to substitute |

Returns an `AgentRun` with `replayed=True`.

---

## ReplayEngine

For more control, use `ReplayEngine` directly.

```python
from evalcraft.replay.engine import ReplayEngine

engine = ReplayEngine("tests/cassettes/weather.json")
# or pass a Cassette object:
# engine = ReplayEngine(cassette)
```

### Constructor

```python
ReplayEngine(cassette: Cassette | str | Path)
```

Accepts either a `Cassette` object or a path to a JSON cassette file.

---

## Overrides

### `override_tool_result(tool_name, result)`

Substitute the result of a named tool during replay.

```python
engine = ReplayEngine("tests/cassettes/weather.json")
engine.override_tool_result("get_weather", {"temp": -5, "condition": "blizzard"})
run = engine.run()
```

Returns `self` for chaining.

```python
engine = (
    ReplayEngine("tests/cassettes/agent.json")
    .override_tool_result("web_search", {"results": []})
    .override_tool_result("send_email", {"success": True})
)
run = engine.run()
```

### `override_llm_response(call_index, response)`

Override a specific LLM response by its 0-based index.

```python
engine = ReplayEngine("tests/cassettes/agent.json")
engine.override_llm_response(0, "I don't know the weather.")
run = engine.run()
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `call_index` | `int` | 0-based index of the LLM call to override |
| `response` | `Any` | New response content |

---

## Filtering

### `filter_spans(predicate)`

Keep only spans matching a predicate during replay.

```python
from evalcraft.core.models import SpanKind

engine = ReplayEngine("tests/cassettes/agent.json")
engine.filter_spans(lambda span: span.kind == SpanKind.TOOL_CALL)
run = engine.run()
# Only tool call spans are in the result
```

---

## Running

### `run()`

Execute the full replay and return an `AgentRun`.

```python
run = engine.run()
print(run.cassette.output_text)
print(run.cassette.total_tokens)
```

### `step()`

Step through the replay one span at a time.

```python
engine = ReplayEngine("tests/cassettes/agent.json")

while True:
    span = engine.step()
    if span is None:
        break
    print(f"[{span.kind}] {span.name}")
```

Returns the next `Span`, or `None` when all spans are exhausted.

### `reset()`

Reset the step-by-step iterator back to the beginning.

```python
engine.reset()
# Now engine.step() starts from the first span again
```

---

## Querying spans

### `spans`

All spans in the cassette (respecting any active filter).

```python
for span in engine.spans:
    print(span.kind, span.name)
```

### `get_tool_calls()`

Get all tool-call spans.

```python
tool_spans = engine.get_tool_calls()
for span in tool_spans:
    print(span.tool_name, span.tool_args, span.tool_result)
```

### `get_llm_calls()`

Get all LLM spans (both `LLM_REQUEST` and `LLM_RESPONSE`).

```python
llm_spans = engine.get_llm_calls()
for span in llm_spans:
    print(span.model, span.token_usage)
```

### `get_tool_sequence()`

Get the ordered list of tool names called.

```python
seq = engine.get_tool_sequence()
# e.g. ["web_search", "summarize", "send_email"]
```

---

## Diffing cassettes

### `engine.diff(other)`

Compare this engine's cassette to another cassette and return a `ReplayDiff`.

```python
engine = ReplayEngine("tests/cassettes/v1.json")
diff = engine.diff("tests/cassettes/v2.json")

print(diff.has_changes)           # True or False
print(diff.tool_sequence_changed) # True
print(diff.output_changed)        # False
print(diff.token_count_changed)   # True
print(diff.old_tokens)            # 135
print(diff.new_tokens)            # 210
print(diff.summary())
# Tool sequence: ['search'] → ['search', 'summarize']
# Tokens: 135 → 210
```

### `ReplayDiff` properties

| Property | Type | Description |
|----------|------|-------------|
| `has_changes` | `bool` | True if any field changed |
| `tool_sequence_changed` | `bool` | Tool call order changed |
| `output_changed` | `bool` | Agent output text changed |
| `token_count_changed` | `bool` | Total token count changed |
| `cost_changed` | `bool` | Total cost changed |
| `span_count_changed` | `bool` | Number of spans changed |
| `old_tool_sequence` | `list[str]` | Tool sequence in old cassette |
| `new_tool_sequence` | `list[str]` | Tool sequence in new cassette |
| `old_output` | `str` | Output text in old cassette |
| `new_output` | `str` | Output text in new cassette |
| `old_tokens` | `int` | Tokens in old cassette |
| `new_tokens` | `int` | Tokens in new cassette |

### `ReplayDiff.compute(old, new)`

Static factory to compare two cassettes directly.

```python
from evalcraft.core.models import Cassette
from evalcraft.replay.engine import ReplayDiff

c1 = Cassette.load("cassettes/v1.json")
c2 = Cassette.load("cassettes/v2.json")
diff = ReplayDiff.compute(c1, c2)
print(diff.to_dict())
```

---

## Common patterns

### Regression test with fingerprint

```python
def test_no_regression():
    run = replay("tests/cassettes/baseline.json")
    # Fingerprint is computed from span content
    # Store the expected fingerprint in your test
    assert run.cassette.fingerprint == "a3f1c2d4e5b6a7c8"
```

### Testing different tool responses

```python
import pytest
from evalcraft.replay.engine import ReplayEngine

@pytest.mark.parametrize("weather,expected_tone", [
    ({"temp": 30, "condition": "sunny"}, "hot"),
    ({"temp": -10, "condition": "blizzard"}, "cold"),
])
def test_agent_adapts_to_weather(weather, expected_tone):
    engine = ReplayEngine("tests/cassettes/weather.json")
    engine.override_tool_result("get_weather", weather)
    run = engine.run()
    # The output changes because the tool result changed
    assert run.cassette.output_text  # non-empty
```

### Detecting regressions between versions

```python
from evalcraft.replay.engine import ReplayEngine

def test_no_new_tool_calls():
    diff = ReplayEngine("tests/cassettes/baseline.json").diff("tests/cassettes/current.json")
    if diff.tool_sequence_changed:
        pytest.fail(
            f"Tool sequence changed!\n"
            f"  Before: {diff.old_tool_sequence}\n"
            f"  After:  {diff.new_tool_sequence}"
        )
```
