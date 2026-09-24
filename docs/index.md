# Evalcraft

**Catch the agent that quietly stopped calling its tools — and the one that tripled your bill.**

Agents rarely crash. They return `200 OK`, report "task completed", and skip the tool call that did the actual work. Evalcraft locks your agent's **tool calls, arguments, output shape and cost budget** as ordinary **pytest** assertions that run offline in CI for **$0** — no model call, no LLM judge, no flaky reruns.

[![CI](https://github.com/beyhangl/evalcraft/actions/workflows/ci.yml/badge.svg)](https://github.com/beyhangl/evalcraft/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/evalcraft)](https://pypi.org/project/evalcraft/)
[![Python](https://img.shields.io/pypi/pyversions/evalcraft)](https://pypi.org/project/evalcraft/)
[![License](https://img.shields.io/github/license/beyhangl/evalcraft)](https://github.com/beyhangl/evalcraft/blob/main/LICENSE)

---

## The problem

**Agents fail silently.** They return `200 OK`, report "task completed", and never call the tool that did the work. A crash is the good outcome — it's loud and it stops. The quiet ones sit there looking green.

**Output-only evals miss it.** If you score the final text, an agent that quietly stopped calling `lookup_order` still passes.

**And the bill climbs.** Judge-based evals on every commit cost real money, so the gate gets disabled.

Evalcraft asserts the parts of an agent that *are* deterministic: which tools ran, in what order, with which arguments, what shape came back, whether it looped, and what it cost. Those assertions read a run you already recorded, so they execute in milliseconds for **$0** on every commit. For the questions that genuinely need a live model — quality, drift, LLM-judge, RAG — run [live-eval](user-guide/live-eval.md) on a schedule.

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
