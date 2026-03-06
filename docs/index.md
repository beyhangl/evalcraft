# Evalcraft

**The pytest for AI agents.** Capture, replay, mock, and evaluate agent behavior — without burning API credits on every test run.

[![CI](https://github.com/beyhangl/evalcraft/actions/workflows/ci.yml/badge.svg)](https://github.com/beyhangl/evalcraft/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/evalcraft)](https://pypi.org/project/evalcraft/)
[![Python](https://img.shields.io/pypi/pyversions/evalcraft)](https://pypi.org/project/evalcraft/)
[![License](https://img.shields.io/github/license/beyhangl/evalcraft)](https://github.com/beyhangl/evalcraft/blob/main/LICENSE)

---

## The problem

Agent testing is broken:

- **Expensive.** Running 200 tests against GPT-4 costs real money. Every commit.
- **Non-deterministic.** Tests fail randomly because LLMs aren't functions.
- **No CI/CD story.** You can't gate deploys on eval results if evals take 10 minutes and cost $5.

Evalcraft fixes this by recording agent runs as **cassettes** (like VCR for HTTP), then replaying them deterministically. Your test suite goes from 10 minutes + $5 to 200ms + $0.

---

## How it works

```
  Your Agent
      │
      ▼
┌─────────────┐    record     ┌──────────────┐
│  CaptureCtx │ ────────────► │   Cassette   │  (plain JSON, git-friendly)
│             │               │  (spans[])   │
└─────────────┘               └──────┬───────┘
                                     │
                    ┌────────────────┼────────────────┐
                    ▼                ▼                ▼
              replay()          MockLLM /        assert_*()
           (zero API calls)    MockTool()       (scorers)
                    │                                 │
                    └──────────────┬──────────────────┘
                                   ▼
                            pytest / CI gate
                           (200ms, $0.00)
```

---

## Install

```bash
pip install evalcraft

# With pytest plugin
pip install "evalcraft[pytest]"

# With framework adapters
pip install "evalcraft[openai]"      # OpenAI SDK adapter
pip install "evalcraft[anthropic]"   # Anthropic SDK adapter
pip install "evalcraft[langchain]"   # LangGraph adapter

# Everything
pip install "evalcraft[all]"
```

---

## Quick example

```python
from evalcraft import CaptureContext, MockLLM, MockTool
from evalcraft import assert_tool_called, assert_cost_under

# 1. Record a run with mocks
llm = MockLLM()
llm.add_response("*", "It's 22°C and sunny in Paris.")

search = MockTool("get_weather")
search.returns({"temp": 22, "condition": "sunny"})

with CaptureContext(name="weather_test", save_path="tests/cassettes/weather.json") as ctx:
    ctx.record_input("What's the weather in Paris?")
    result = search.call(city="Paris")
    response = llm.complete(f"Weather data: {result}")
    ctx.record_output(response.content)

# 2. Replay from cassette — zero API calls
from evalcraft import replay
run = replay("tests/cassettes/weather.json")

# 3. Assert behavior
assert assert_tool_called(run, "get_weather").passed
assert assert_cost_under(run, max_usd=0.01).passed
```

---

## Documentation

| Section | Description |
|---------|-------------|
| [Quickstart](user-guide/quickstart.md) | Get running in 5 minutes |
| [Case Study](user-guide/five-minute-case-study.md) | How a team caught a $50/day regression |
| [Concepts](user-guide/concepts.md) | Cassettes, spans, capture, replay explained |
| [Capture API](user-guide/capture.md) | Full capture API reference |
| [Replay Engine](user-guide/replay.md) | Replay and diff cassettes |
| [Mock LLM & Tools](user-guide/mock.md) | Deterministic mocks for testing |
| [Scorers](user-guide/scorers.md) | Built-in assertion functions |
| [pytest Plugin](user-guide/pytest-plugin.md) | Fixtures, markers, and CLI flags |
| [CLI Reference](user-guide/cli.md) | All 6 CLI commands |
| [Adapters](user-guide/adapters/openai.md) | OpenAI, Anthropic, LangGraph, CrewAI |
| [CI/CD](user-guide/ci-cd.md) | GitHub Actions integration |
