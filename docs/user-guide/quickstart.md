# Quickstart — 5 minutes to your first eval

By the end of this guide you will have:
- Captured a real agent run into a cassette
- Replayed it with zero API calls
- Written passing assertions in pytest
- Set up a CI-ready test that costs $0 per run

---

## Install

```bash
pip install "evalcraft[pytest]"
```

For framework-specific adapters (optional — install what you use):

```bash
pip install "evalcraft[openai]"      # OpenAI SDK auto-capture
pip install "evalcraft[anthropic]"   # Anthropic SDK auto-capture
pip install "evalcraft[langchain]"   # LangGraph / LangChain auto-capture
pip install "evalcraft[all]"         # Everything
```

---

## Step 1 — Capture

Record your agent's behavior into a **cassette** file. Run this once
with a real API key:

```python
# capture_run.py
from evalcraft import CaptureContext

with CaptureContext(
    name="support_agent_test",
    agent_name="support_agent",
    save_path="tests/cassettes/support.json",  # committed to git
) as ctx:

    # Record the user input
    ctx.record_input("Where is my order ORD-1042?")

    # Record tool calls your agent made
    ctx.record_tool_call(
        tool_name="lookup_order",
        args={"order_id": "ORD-1042"},
        result={"status": "shipped", "carrier": "UPS", "tracking": "1Z999AA1"},
        duration_ms=45.0,
    )

    # Record the LLM call
    ctx.record_llm_call(
        model="gpt-4o-mini",
        input="Order ORD-1042: shipped via UPS. Answer the customer.",
        output="Your order ORD-1042 is shipped via UPS. Tracking: 1Z999AA1.",
        prompt_tokens=85,
        completion_tokens=22,
        cost_usd=0.000017,
    )

    # Record the final answer
    ctx.record_output("Your order ORD-1042 is shipped via UPS. Tracking: 1Z999AA1.")

cassette = ctx.cassette
print(f"Spans:       {len(cassette.spans)}")
print(f"Tool calls:  {cassette.tool_call_count}")
print(f"Tokens:      {cassette.total_tokens}")
print(f"Cost:        ${cassette.total_cost_usd:.5f}")
print(f"Fingerprint: {cassette.fingerprint}")
# Spans:       4
# Tool calls:  1
# Tokens:      107
# Cost:        $0.00002
# Fingerprint: a3f1c2d4e5b6a7c8
```

```bash
python capture_run.py
# Creates tests/cassettes/support.json — commit this to git.
```

### Using framework adapters (zero-code capture)

If you use the OpenAI or Anthropic SDK, the adapter records every API call
automatically — no manual `record_*` calls needed:

```python
# With OpenAI
from evalcraft import CaptureContext
from evalcraft.adapters import OpenAIAdapter
import openai

client = openai.OpenAI()

with CaptureContext(name="openai_run", save_path="tests/cassettes/run.json") as ctx:
    ctx.record_input("What's the weather in Paris?")
    with OpenAIAdapter():
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "What's the weather in Paris?"}],
        )
    ctx.record_output(response.choices[0].message.content)
```

```python
# With Anthropic
from evalcraft.adapters import AnthropicAdapter
import anthropic

client = anthropic.Anthropic()

with CaptureContext(name="claude_run", save_path="tests/cassettes/claude.json") as ctx:
    ctx.record_input("Summarize this document.")
    with AnthropicAdapter():
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=512,
            messages=[{"role": "user", "content": "Summarize this document."}],
        )
    ctx.record_output(response.content[0].text)
```

```python
# With LangGraph
from evalcraft.adapters import LangGraphAdapter

graph = build_my_graph()  # your compiled LangGraph StateGraph

with CaptureContext(name="graph_run", save_path="tests/cassettes/graph.json") as ctx:
    ctx.record_input("Plan a trip to Tokyo")
    with LangGraphAdapter(graph):
        result = graph.invoke({"messages": [("user", "Plan a trip to Tokyo")]})
    ctx.record_output(result["messages"][-1].content)
```

---

## Step 2 — Replay

Load the cassette and replay it. **Zero API calls. Zero cost.**

```python
from evalcraft import replay

run = replay("tests/cassettes/support.json")

print(run.replayed)            # True
print(run.cassette.output_text)
# Your order ORD-1042 is shipped via UPS. Tracking: 1Z999AA1.

print(run.cassette.total_tokens)   # 107
print(run.cassette.total_cost_usd) # 0.000017
```

---

## Step 3 — Assert

Write assertions using evalcraft's built-in scorers:

```python
from evalcraft import (
    replay,
    assert_tool_called,
    assert_tool_order,
    assert_output_contains,
    assert_cost_under,
    assert_token_count_under,
)

run = replay("tests/cassettes/support.json")

# Did the agent call the right tool?
result = assert_tool_called(run, "lookup_order")
assert result.passed, result.message

# Did it pass the right argument?
result = assert_tool_called(run, "lookup_order", with_args={"order_id": "ORD-1042"})
assert result.passed, result.message

# Did the output mention the carrier?
result = assert_output_contains(run, "UPS")
assert result.passed, result.message

# Did it stay within budget?
result = assert_cost_under(run, max_usd=0.01)
assert result.passed, result.message
```

All scorers return an `AssertionResult` with `.passed`, `.message`, `.expected`, `.actual`.
They never raise on failure — you decide whether to `assert` or collect results.

---

## Step 4 — pytest

Put it all in a test file. Replay is fast — under 100ms per test:

```python
# tests/test_support_agent.py
from evalcraft import replay, assert_tool_called, assert_output_contains, assert_cost_under

CASSETTE = "tests/cassettes/support.json"

def test_agent_calls_lookup_order():
    run = replay(CASSETTE)
    result = assert_tool_called(run, "lookup_order")
    assert result.passed, result.message

def test_agent_passes_order_id():
    run = replay(CASSETTE)
    result = assert_tool_called(run, "lookup_order", with_args={"order_id": "ORD-1042"})
    assert result.passed, result.message

def test_output_mentions_carrier():
    run = replay(CASSETTE)
    result = assert_output_contains(run, "UPS")
    assert result.passed, result.message

def test_cost_within_budget():
    run = replay(CASSETTE)
    result = assert_cost_under(run, max_usd=0.01)
    assert result.passed, result.message
```

```bash
pytest tests/test_support_agent.py -v
# test_agent_calls_lookup_order    PASSED   (18ms, $0.00)
# test_agent_passes_order_id       PASSED   (12ms, $0.00)
# test_output_mentions_carrier     PASSED   ( 9ms, $0.00)
# test_cost_within_budget          PASSED   ( 7ms, $0.00)
# 4 passed in 0.05s
```

---

## Step 5 — Mock (unit testing without cassettes)

Use `MockLLM` and `MockTool` for self-contained unit tests that need no
cassette file and no API key:

```python
from evalcraft import CaptureContext, MockLLM, MockTool, assert_tool_called

def test_agent_with_mocks():
    # Set up deterministic mocks
    order_tool = MockTool("lookup_order")
    order_tool.returns({"status": "shipped", "carrier": "FedEx"})

    llm = MockLLM()
    llm.add_response("*", "Your order shipped via FedEx.")

    # Run with capture
    with CaptureContext(name="mock_test") as ctx:
        ctx.record_input("Where is ORD-9999?")
        order_data = order_tool.call(order_id="ORD-9999")
        response = llm.complete(f"Order data: {order_data}. Answer the customer.")
        ctx.record_output(response.content)

    # Assert on the cassette
    cassette = ctx.cassette
    assert assert_tool_called(cassette, "lookup_order").passed
    order_tool.assert_called(times=1)
    order_tool.assert_called_with(order_id="ORD-9999")
    llm.assert_called(times=1)
    assert "FedEx" in cassette.output_text
```

`MockLLM` supports:
- `add_response(prompt, content)` — exact or wildcard (`"*"`) match
- `add_pattern_response(regex, content)` — regex match
- `add_sequential_responses(prompt, [r1, r2, r3])` — multi-turn simulation

`MockTool` supports:
- `returns(value)` — static return
- `returns_fn(fn)` — dynamic return based on args
- `returns_sequence([v1, v2, v3])` — sequential returns
- `raises(error)` — error simulation
- `with_latency(ms)` — simulated slowness

---

## Step 6 — CI gate

Add to your CI pipeline. Cassettes are committed to git, so CI never needs
an API key for replay:

```yaml
# .github/workflows/ci.yml
- name: Run agent evals
  run: |
    pip install "evalcraft[pytest]"
    pytest tests/ -v
  # Runs in ~30 seconds, costs $0.00
  # No API keys needed — cassettes are in the repo
```

To refresh cassettes periodically (when prompts or tools change):

```yaml
# Nightly cassette refresh — needs API key
- name: Refresh cassettes
  if: github.event_name == 'schedule'
  run: python capture_run.py
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

---

## What's next?

| Guide | What you'll learn |
|-------|------------------|
| [Concepts](concepts.md) | Cassettes, spans, fingerprints — the full data model |
| [Capture API](capture.md) | `CaptureContext`, `@capture` decorator, `record_*` methods |
| [Replay Engine](replay.md) | Tool overrides, step iteration, diffs |
| [Scorers](scorers.md) | All `assert_*` functions + `Evaluator` |
| [Mock API](mock.md) | `MockLLM` and `MockTool` full reference |
| [Adapters](adapters/openai.md) | OpenAI, Anthropic, LangGraph, CrewAI |
| [CLI Reference](cli.md) | `evalcraft replay`, `diff`, `inspect` |
| [CI/CD Guide](ci-cd.md) | GitHub Actions, GitLab CI, golden sets |
| [Examples](../../examples/) | Four complete example projects |
