# Evalcraft v0.1.0 — Launch Day Posts

---

## 1. Show HN

**Title:** Show HN: Evalcraft – open-source cassette-based testing for AI agents (pytest-native, $0 per run)

**Body:**

Testing AI agents is painful. Every test run calls the LLM API, costs real money, takes minutes, and gives different results each time. CI? Forget about it.

Evalcraft fixes this with cassette-based capture and replay — think VCR for HTTP, but for LLM calls and tool use.

**How it works:**

1. Run your agent once with real API calls. Evalcraft records every LLM request, tool call, and response into a JSON cassette file.
2. In tests, replay from the cassette. Zero API calls, zero cost, deterministic output.
3. Assert on what matters: tool call sequences, output content, cost budgets, token counts.

```python
run = replay("cassettes/support_agent.json")
assert_tool_called(run, "lookup_order", with_args={"order_id": "ORD-1042"})
assert_tool_order(run, ["lookup_order", "search_knowledge_base"])
assert_cost_under(run, max_usd=0.01)
```

It's pytest-native — fixtures, markers, CLI flags. Works with OpenAI, Anthropic, LangGraph, CrewAI, AutoGen, and LlamaIndex out of the box. Adapters auto-instrument your agent with zero code changes.

Also ships with golden-set management, regression detection, PII sanitization, and 16 CLI commands for inspecting/diffing cassettes.

555 tests, MIT licensed, `pip install evalcraft`.

Repo: https://github.com/beyhangl/evalcraft
Docs: https://github.com/beyhangl/evalcraft/blob/main/docs/user-guide/quickstart.md

<!-- TODO: Add Discord/community link when available -->

Would love feedback from anyone testing agents in CI.

---

## 2. Twitter/X Thread

**Tweet 1:**

Agent testing is broken.

Every test run:
- Calls the LLM API
- Costs real money
- Takes minutes
- Returns different output each time

We built evalcraft to fix this — cassette-based capture and replay for AI agents. pytest-native. $0 per run.

Here's how it works:

**Tweet 2:**

Record your agent once with real API calls. Every LLM request, tool call, and response gets saved to a JSON cassette.

Then replay from cassette. Zero API calls. Zero cost. Deterministic.

Same concept as VCR for HTTP testing, applied to AI agents.

**Tweet 3:**

Here's what a test looks like:

```python
from evalcraft import replay, assert_tool_called, assert_cost_under

run = replay("cassettes/support_agent.json")

assert_tool_called(run, "lookup_order")
assert_cost_under(run, max_usd=0.01)
```

Capture once. Replay forever. Assert on behavior.

**Tweet 4:**

Before evalcraft:
- Minutes-long test suite
- Real API costs per run
- Non-deterministic, breaks CI

After evalcraft:
- 200ms test suite
- $0.00 per run
- Deterministic, runs in CI on every commit

6 framework adapters: OpenAI, Anthropic, LangGraph, CrewAI, AutoGen, LlamaIndex.

**Tweet 5:**

Get started in 2 minutes:

```bash
pip install evalcraft
evalcraft init
pytest tests/ -v
```

555 tests. MIT licensed. Fully open source.

GitHub: https://github.com/beyhangl/evalcraft

Looking for early users testing agents in production — DMs open.

<!-- TODO: Add Discord/community link when available -->

---

## 3. Reddit — r/MachineLearning

**Title:** [P] Evalcraft — cassette-based capture & replay for testing AI agents (pytest-native, 6 frameworks, $0 per run)

**Body:**

We built evalcraft to solve a specific problem: agent tests are expensive, non-deterministic, and don't run in CI.

The core idea is cassette-based recording. Run your agent once with real LLM calls — evalcraft captures every span (LLM requests, tool calls, responses) into a JSON file. Then replay from that cassette in tests: zero API calls, zero cost, deterministic output every time.

The cassette format is plain JSON, diffable, and git-friendly. You can inspect, diff, and evaluate cassettes from the CLI. Built-in scorers let you assert on tool call sequences, output content, cost budgets, and token counts.

```python
from evalcraft import replay, assert_tool_called, assert_tool_order, assert_cost_under

run = replay("cassettes/support_agent.json")

assert_tool_called(run, "lookup_order", with_args={"order_id": "ORD-1042"})
assert_tool_order(run, ["lookup_order", "search_knowledge_base"])
assert_cost_under(run, max_usd=0.01)
```

Ships with adapters for OpenAI, Anthropic, LangGraph, CrewAI, AutoGen, and LlamaIndex — they auto-instrument your agent with a context manager, no code changes needed.

Also includes golden-set management for regression detection, PII sanitization, and a pytest plugin with fixtures and markers.

555 tests. MIT licensed.

`pip install evalcraft` | [GitHub](https://github.com/beyhangl/evalcraft) | [Quickstart](https://github.com/beyhangl/evalcraft/blob/main/docs/user-guide/quickstart.md)

<!-- TODO: Add Discord/community link when available -->

---

## 4. Reddit — r/LangChain

**Title:** Built a testing framework for LangGraph agents — cassette-based replay, deterministic CI, $0 per run

**Body:**

If you're testing LangGraph agents, you know the pain: every test run hits the LLM API, costs money, returns different results, and makes CI flaky.

Evalcraft solves this with cassette-based capture and replay. The LangGraph adapter patches your compiled graph to record every node execution, LLM call, and tool invocation into a JSON cassette:

```python
from evalcraft import CaptureContext
from evalcraft.adapters import LangGraphAdapter

with CaptureContext(name="my_graph_test", save_path="cassette.json") as ctx:
    with LangGraphAdapter(graph):
        result = graph.invoke({"input": "Track order ORD-1042"})
```

Then replay in tests — zero API calls, deterministic, runs in 200ms:

```python
from evalcraft import replay, assert_tool_called, assert_tool_order, assert_cost_under

run = replay("cassette.json")
assert_tool_called(run, "lookup_order")
assert_tool_order(run, ["lookup_order", "search_knowledge_base"])
assert_cost_under(run, max_usd=0.01)
```

Also works with OpenAI, Anthropic, CrewAI, AutoGen, and LlamaIndex. pytest-native with fixtures and markers. Golden-set management for catching regressions.

`pip install evalcraft` | [GitHub](https://github.com/beyhangl/evalcraft) | [Quickstart](https://github.com/beyhangl/evalcraft/blob/main/docs/user-guide/quickstart.md)

<!-- TODO: Add Discord/community link when available -->

---

## 5. Discord Message

**yo — just shipped evalcraft, a testing framework for AI agents**

Think VCR for HTTP, but for LLM calls. Record your agent once, replay from cassette forever. Zero API cost, deterministic, runs in CI.

```python
run = replay("cassettes/my_agent.json")
assert_tool_called(run, "search")
assert_cost_under(run, max_usd=0.01)
# 200ms, $0.00
```

Works with OpenAI, Anthropic, LangGraph, CrewAI, AutoGen, LlamaIndex. pytest-native — fixtures, markers, the whole deal.

`pip install evalcraft` — MIT, fully open source
https://github.com/beyhangl/evalcraft

Looking for early users testing agents in prod. Feedback welcome.

<!-- TODO: Replace with Discord/community invite link when available -->

---

## 6. Product Hunt Listing

**Tagline:** The pytest for AI agents — capture, replay, assert

**Description:** Record AI agent runs once, replay them deterministically forever. Zero API calls, zero cost. Assert on tool calls, output, cost, and tokens. pytest-native with 6 framework adapters. Open source, MIT licensed.

**Feature 1:**
- **Title:** Cassette-Based Capture & Replay
- **Description:** Record every LLM call and tool invocation into a JSON cassette file. Replay in tests with zero API calls — deterministic output, 200ms runtime, $0.00 cost. Like VCR for HTTP, but for AI agents.

**Feature 2:**
- **Title:** 6 Framework Adapters
- **Description:** Drop-in adapters for OpenAI, Anthropic, LangGraph, CrewAI, AutoGen, and LlamaIndex. Auto-instrument your agent with a single context manager — no code changes to your agent logic.

**Feature 3:**
- **Title:** Built-In Evaluation & Regression Detection
- **Description:** Assert on tool call sequences, output content, cost budgets, and token counts. Track baselines with golden sets. Detect regressions automatically — tool order changes, cost spikes, output drift.

**Links:**
- GitHub: https://github.com/beyhangl/evalcraft
- Quickstart: https://github.com/beyhangl/evalcraft/blob/main/docs/user-guide/quickstart.md

<!-- TODO: Add Discord/community link when available -->
