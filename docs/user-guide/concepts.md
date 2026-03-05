# Concepts

Understanding Evalcraft's core abstractions.

---

## Cassette

A **cassette** is a complete recording of one agent run. It is serialized as plain JSON and is the fundamental unit in Evalcraft.

Named after VCR cassettes — you record something once, then play it back as many times as you want.

```json
{
  "evalcraft_version": "0.1.0",
  "cassette": {
    "id": "a1b2c3d4-...",
    "name": "weather_agent_test",
    "agent_name": "weather_agent",
    "framework": "openai",
    "input_text": "What's the weather in Paris?",
    "output_text": "It's 18°C and cloudy in Paris.",
    "total_tokens": 135,
    "total_cost_usd": 0.0008,
    "total_duration_ms": 450.0,
    "llm_call_count": 1,
    "tool_call_count": 1,
    "fingerprint": "a3f1c2d4e5b6a7c8",
    "metadata": {}
  },
  "spans": [...]
}
```

### Key properties

| Property | Type | Description |
|----------|------|-------------|
| `id` | `str` | UUID, unique per run |
| `name` | `str` | Human-readable test name |
| `agent_name` | `str` | Name of the agent under test |
| `framework` | `str` | e.g. `"openai"`, `"langgraph"` |
| `input_text` | `str` | User's input to the agent |
| `output_text` | `str` | Agent's final output |
| `total_tokens` | `int` | Sum of all token usage |
| `total_cost_usd` | `float` | Estimated dollar cost |
| `total_duration_ms` | `float` | Wall-clock time in milliseconds |
| `llm_call_count` | `int` | Number of LLM calls made |
| `tool_call_count` | `int` | Number of tool calls made |
| `fingerprint` | `str` | SHA-256 of span content (first 16 hex chars) |
| `spans` | `list[Span]` | Ordered list of all recorded events |

### Cassettes are git-friendly

Cassettes are stored as plain JSON. This means:

- **Diff them in PRs** — review exactly which tools were called, what tokens were used
- **Version them** — each cassette represents a specific agent behavior
- **Detect regressions** — the `fingerprint` field changes if any span changes

---

## Span

A **span** is a single recorded event in an agent run. Each LLM call, tool invocation, or agent step is a span.

### Span kinds

| SpanKind | Value | Description |
|----------|-------|-------------|
| `LLM_REQUEST` | `"llm_request"` | Before an LLM call |
| `LLM_RESPONSE` | `"llm_response"` | After an LLM call (with output and tokens) |
| `TOOL_CALL` | `"tool_call"` | A tool was invoked |
| `TOOL_RESULT` | `"tool_result"` | Result of a tool call |
| `AGENT_STEP` | `"agent_step"` | A node or chain step (LangGraph) |
| `USER_INPUT` | `"user_input"` | The user's input message |
| `AGENT_OUTPUT` | `"agent_output"` | The agent's final answer |

### Span fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | UUID |
| `kind` | `SpanKind` | Type of event |
| `name` | `str` | Human-readable label (e.g. `"tool:get_weather"`) |
| `timestamp` | `float` | Unix timestamp when the span started |
| `duration_ms` | `float` | Duration in milliseconds |
| `input` | `Any` | Input data (prompt, tool args) |
| `output` | `Any` | Output data (response text, tool result) |
| `error` | `str \| None` | Error message if the call failed |
| `model` | `str \| None` | LLM model name (LLM spans only) |
| `token_usage` | `TokenUsage \| None` | Token counts (LLM spans only) |
| `cost_usd` | `float \| None` | Estimated cost (LLM spans only) |
| `tool_name` | `str \| None` | Tool name (tool spans only) |
| `tool_args` | `dict \| None` | Arguments passed to the tool |
| `tool_result` | `Any` | Return value of the tool |
| `metadata` | `dict` | Arbitrary extra data |

---

## Capture

**Capturing** means running your agent with a `CaptureContext` active. All LLM calls and tool calls recorded during the context are collected into a cassette.

```python
from evalcraft import CaptureContext

# Context manager — sync
with CaptureContext(name="my_test", save_path="cassettes/my_test.json") as ctx:
    # ... run your agent ...
    pass

# Context manager — async
async with CaptureContext(name="async_test") as ctx:
    # ... run your async agent ...
    pass
```

There are three ways to record events into a cassette:

1. **Manual recording** — call `ctx.record_llm_call(...)`, `ctx.record_tool_call(...)` directly
2. **MockLLM / MockTool** — auto-record when `MockLLM.complete()` or `MockTool.call()` is invoked inside an active context
3. **Framework adapters** — `OpenAIAdapter`, `AnthropicAdapter`, `LangGraphAdapter`, `CrewAIAdapter` monkey-patch the SDK to record automatically

---

## Replay

**Replaying** means loading a cassette and running the recorded spans without making any real API calls.

```python
from evalcraft import replay, ReplayEngine

# Simple replay
run = replay("cassettes/my_test.json")
assert run.replayed is True

# Replay with modifications
engine = ReplayEngine("cassettes/my_test.json")
engine.override_tool_result("get_weather", {"temp": 5, "condition": "snow"})
run = engine.run()
```

During replay:
- LLM responses are returned from the cassette (no API calls)
- Tool results are returned from the cassette (no real tool execution)
- Overrides can substitute new values for specific tools or LLM calls

---

## Fingerprint

The **fingerprint** is a 16-character hex digest (SHA-256) of the cassette's span content. It changes if any span's input, output, tool name, or model changes.

Use fingerprints to:
- **Detect regressions** — if your agent's behavior changes between runs, the fingerprint changes
- **CI gates** — fail a build if the fingerprint changes unexpectedly
- **Diff** — compare two cassettes with `evalcraft diff`

```python
from evalcraft import replay

run = replay("cassettes/v1.json")
print(run.cassette.fingerprint)  # e.g. "a3f1c2d4e5b6a7c8"
```

---

## AgentRun

An `AgentRun` is the result object returned by `replay()` and `ReplayEngine.run()`. It wraps a `Cassette` with metadata about whether the run was live or replayed.

```python
from evalcraft import replay

run = replay("cassettes/my_test.json")
print(run.cassette.output_text)  # the agent's answer
print(run.replayed)              # True
print(run.success)               # True
print(run.error)                 # None
```

All scorer functions (`assert_tool_called`, etc.) accept either a `Cassette` or an `AgentRun`.
