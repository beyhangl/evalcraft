# Quickstart — 5 minutes to your first eval

By the end of this guide you will have:

- Installed evalcraft with an adapter
- Recorded your first cassette from a real agent run
- Written passing assertions in pytest
- Added a CI gate that blocks regressions on every PR
- Created a golden set baseline for your agent

**Prerequisites:** Python 3.9+, pip, and optionally an OpenAI or Anthropic API key (not needed for replay or mock mode).

---

## Step 1 — Install

```bash
pip install "evalcraft[openai]"
```

This installs evalcraft with the OpenAI adapter. Swap `openai` for `anthropic`, `langchain`, or `all` depending on your stack.

Then scaffold your project:

```bash
evalcraft init
```

This creates:

```
tests/
├── cassettes/          # recorded agent runs (committed to git)
└── test_agent.py       # sample test file with assertions
```

**What just happened?** `evalcraft init` generated a test directory structure and a sample test file that shows the basic capture → replay → assert pattern. The `tests/cassettes/` directory is where your recorded agent runs will live — these are plain JSON files that you commit to git.

---

## Step 2 — Record your first cassette

A **cassette** is a recording of everything your agent did: LLM calls, tool calls, inputs, outputs, cost, and tokens. Record one by wrapping your agent code with `CaptureContext`:

```python
# capture_run.py
from evalcraft import CaptureContext
from evalcraft.adapters import OpenAIAdapter
import openai

client = openai.OpenAI()

with CaptureContext(
    name="weather_agent_test",
    agent_name="weather_agent",
    save_path="tests/cassettes/weather.json",
) as ctx:
    ctx.record_input("What's the weather in Paris?")

    # The adapter auto-records all OpenAI API calls
    with OpenAIAdapter():
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "What's the weather in Paris?"}],
        )

    ctx.record_output(response.choices[0].message.content)

print(f"Saved cassette: {ctx.cassette.tool_call_count} tool calls, "
      f"{ctx.cassette.total_tokens} tokens, ${ctx.cassette.total_cost_usd:.4f}")
```

```bash
python capture_run.py
# Creates tests/cassettes/weather.json — commit this to git
```

Or use the CLI shorthand:

```bash
evalcraft capture capture_run.py --output tests/cassettes/weather.json
```

**What just happened?** `CaptureContext` recorded every LLM call your agent made — model name, prompt/completion tokens, cost estimate, and the full response. The `OpenAIAdapter` hooked into the OpenAI SDK automatically, so you didn't need manual `record_llm_call` calls. The cassette is a plain JSON file you can inspect, diff, and commit to git.

!!! tip "No API key? Use mocks"
    You can record cassettes without any API key using `MockLLM` and `MockTool`. See [Mock LLM & Tools](mock.md) for details.

---

## Step 3 — Write your first test

Load the cassette, replay it (zero API calls), and assert on the agent's behavior:

```python
# tests/test_weather_agent.py
from evalcraft import (
    replay,
    assert_tool_called,
    assert_cost_under,
    assert_token_count_under,
    assert_output_contains,
)

CASSETTE = "tests/cassettes/weather.json"


def test_agent_stays_within_budget():
    run = replay(CASSETTE)
    result = assert_cost_under(run, max_usd=0.05)
    assert result.passed, result.message


def test_agent_token_count():
    run = replay(CASSETTE)
    result = assert_token_count_under(run, max_tokens=2000)
    assert result.passed, result.message


def test_output_mentions_paris():
    run = replay(CASSETTE)
    result = assert_output_contains(run, "Paris")
    assert result.passed, result.message
```

```bash
pytest tests/test_weather_agent.py -v
# test_agent_stays_within_budget    PASSED   (12ms, $0.00)
# test_agent_token_count            PASSED   ( 9ms, $0.00)
# test_output_mentions_paris        PASSED   ( 8ms, $0.00)
# 3 passed in 0.04s
```

**What just happened?** `replay()` loaded the cassette and replayed all recorded spans — no API calls, no network, no cost. The `assert_*` functions checked the cassette's recorded data and returned `AssertionResult` objects with `.passed` and `.message` fields. Tests run in milliseconds because they're just reading JSON.

---

## Step 4 — Add to CI

Add the evalcraft GitHub Action to gate your PRs on agent test results. Cassettes are committed to git, so CI never needs an API key:

```yaml
# .github/workflows/agent-tests.yml
name: Agent Tests

on:
  pull_request:
    branches: [main]

jobs:
  agent-tests:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write

    steps:
      - uses: actions/checkout@v4

      - uses: beyhangl/evalcraft@v0.1.0
        with:
          test-path: tests/
          cassette-dir: tests/cassettes/
          max-cost: '0.10'
          max-regression: '5%'
```

This will:

1. Install evalcraft into the runner
2. Run your pytest agent tests in replay mode (no real LLM calls)
3. Post a results table as a PR comment with per-cassette metrics
4. Fail the workflow if any test fails or a cost/regression threshold is exceeded

The action posts a comment like this on every PR:

```
## 🧪 Evalcraft Agent Test Results — ✅ Passed

| Metric           | Value     |
|------------------|-----------|
| Cassettes        | 3         |
| Total tokens     | 1,240     |
| Total cost       | $0.0180   |
| Total tool calls | 4         |
```

**What just happened?** The `beyhangl/evalcraft` GitHub Action installed evalcraft, ran your tests in replay mode, checked cassette metrics against your thresholds, and posted a summary comment on the PR. No API keys needed — everything runs from committed cassettes.

---

## Step 5 — Set up golden sets

A **golden set** is a baseline snapshot of your agent's behavior. Future runs are compared against it — if tool sequences change or cost/tokens spike, tests fail.

```python
# build_golden.py
from evalcraft import GoldenSet
from evalcraft.core.models import Cassette

# Load the cassette you just recorded
cassette = Cassette.load("tests/cassettes/weather.json")

# Create a golden set from it
gs = GoldenSet(name="weather_agent", description="Baseline for weather agent")
gs.add_cassette(cassette)
gs.save("golden/weather_agent.golden.json")

print(f"Golden set saved: {len(gs.cassettes)} cassette(s)")
```

```bash
python build_golden.py
```

Then write a test that compares future runs against the golden baseline:

```python
# tests/test_golden.py
from evalcraft import GoldenSet, replay

def test_no_regression_vs_golden():
    golden = GoldenSet.load("golden/weather_agent.golden.json")
    run = replay("tests/cassettes/weather.json")

    for cassette in golden.cassettes:
        # Token count shouldn't spike
        assert run.cassette.total_tokens <= cassette.total_tokens * 1.1, \
            f"Token count regressed: {run.cassette.total_tokens} vs golden {cassette.total_tokens}"
        # Cost shouldn't spike
        assert run.cassette.total_cost_usd <= cassette.total_cost_usd * 1.1, \
            f"Cost regressed: {run.cassette.total_cost_usd} vs golden {cassette.total_cost_usd}"
```

Or use the CLI:

```bash
evalcraft golden save tests/cassettes/weather.json --name weather_agent
evalcraft golden compare tests/cassettes/weather.json --against golden/weather_agent.golden.json
```

**What just happened?** You created a golden set — a versioned baseline of your agent's behavior. When you re-record cassettes after a prompt or model change, comparing against the golden set catches regressions in cost, tokens, and tool call patterns before they hit production.

---

## What's next?

| Guide | What you'll learn |
|-------|------------------|
| [Case Study](five-minute-case-study.md) | See how a team caught a $50/day regression with evalcraft |
| [Concepts](concepts.md) | Cassettes, spans, fingerprints — the full data model |
| [Capture API](capture.md) | `CaptureContext`, `@capture` decorator, `record_*` methods |
| [Replay Engine](replay.md) | Tool overrides, step iteration, diffs |
| [Scorers](scorers.md) | All `assert_*` functions + `Evaluator` |
| [Mock API](mock.md) | `MockLLM` and `MockTool` full reference |
| [Adapters](adapters/openai.md) | OpenAI, Anthropic, LangGraph, CrewAI |
| [CLI Reference](cli.md) | `evalcraft capture`, `replay`, `diff`, `golden` |
| [CI/CD Guide](ci-cd.md) | GitHub Actions, golden sets, nightly refresh |
| [Examples](../../examples/) | Four complete example projects |
