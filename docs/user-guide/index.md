# User Guide Overview

Welcome to the Evalcraft user guide. Use the links below to navigate to specific topics.

## Core workflow

The typical Evalcraft workflow has three phases:

### 1. Capture (once)

Run your agent with a `CaptureContext` active. Every LLM call, tool invocation, and agent decision is recorded into a **cassette** (a plain JSON file).

```python
from evalcraft import CaptureContext

with CaptureContext(name="my_test", save_path="tests/cassettes/my_test.json") as ctx:
    ctx.record_input("user prompt")
    result = my_agent.run("user prompt")
    ctx.record_output(result)
```

Commit the cassette to git. This is your ground truth.

### 2. Replay (every test run)

Load the cassette and replay it. No API calls. No cost. 200ms.

```python
from evalcraft import replay

run = replay("tests/cassettes/my_test.json")
assert run.replayed is True
```

### 3. Assert (in CI)

Use the built-in scorers to assert behavior.

```python
from evalcraft import assert_tool_called, assert_cost_under

assert assert_tool_called(run, "web_search").passed
assert assert_cost_under(run, max_usd=0.05).passed
```

---

## Guide sections

| Section | What you'll learn |
|---------|-------------------|
| [Quickstart](quickstart.md) | Full working example in 5 minutes |
| [Concepts](concepts.md) | What cassettes, spans, and fingerprints are |
| [Capture API](capture.md) | `CaptureContext`, `record_llm_call`, `record_tool_call` |
| [Replay Engine](replay.md) | `ReplayEngine`, overrides, diffs |
| [Mock LLM & Tools](mock.md) | `MockLLM`, `MockTool` |
| [Scorers](scorers.md) | All `assert_*` functions and `Evaluator` |
| [pytest Plugin](pytest-plugin.md) | Fixtures and markers for pytest integration |
| [CLI Reference](cli.md) | `capture`, `replay`, `diff`, `eval`, `info`, `mock` commands |
| [Adapters](adapters/openai.md) | Auto-capture for OpenAI, Anthropic, LangGraph, CrewAI |
| [CI/CD](ci-cd.md) | GitHub Actions workflows |
| [Changelog](changelog.md) | What's new in each release |
