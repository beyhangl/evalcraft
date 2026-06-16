<p align="center">
  <img src="https://raw.githubusercontent.com/beyhangl/evalcraft/main/site/logo.png" alt="Evalcraft" width="400" />
</p>
<p align="center"><strong>Deterministic tests for AI agents — generated from one real run.</strong></p>
<p align="center">Capture an agent run and evalcraft writes a <strong>pytest</strong> that locks its tool calls, output shape, and cost — then replays it in CI for <strong>$0</strong>. Like VCR for HTTP, but it writes the agent tests for you.</p>

[![CI](https://github.com/beyhangl/evalcraft/actions/workflows/ci.yml/badge.svg)](https://github.com/beyhangl/evalcraft/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/evalcraft)](https://pypi.org/project/evalcraft/)
[![Python](https://img.shields.io/pypi/pyversions/evalcraft)](https://pypi.org/project/evalcraft/)
[![License](https://img.shields.io/github/license/beyhangl/evalcraft)](LICENSE)

---

## Get Started in 60 Seconds

```bash
pip install evalcraft
evalcraft init                # scaffolds tests/cassettes/ and a sample test
pytest --evalcraft            # run with recording
```

That's it. Your first cassette is recorded, committed to git, and replays for free on every future run. See the [5-minute quickstart](https://beyhangl.github.io/evalcraft/docs/user-guide/quickstart/) for the full walkthrough.

---

## The problem

Agent testing is broken:

- **Expensive.** Running 200 tests against GPT-4.1 costs real money. Every commit.
- **Non-deterministic.** Tests fail randomly because LLMs aren't functions.
- **No CI/CD story.** You can't gate deploys on eval results if evals take 10 minutes and cost $5.

Evalcraft records agent runs as **cassettes** (like VCR for HTTP) and replays them deterministically — so the tests that exercise your agent's *plumbing* (tool wiring, control flow, output shape, cost/latency budgets) drop from 10 minutes + $5 to **200ms + $0**. For the questions that genuinely need a live model — quality, drift, LLM-judge, RAG — run [live-eval](#catching-drift-live-eval) on a schedule.

---

## How it works

```
  Your Agent
      |
      v
+-------------+    record     +--------------+
|  CaptureCtx | ------------> |   Cassette   |  (plain JSON, git-friendly)
|             |               |  (spans[])   |
+-------------+               +------+-------+
                                     |
                    +----------------+----------------+
                    v                v                v
              replay()          MockLLM /        assert_*()
           (zero API calls)    MockTool()       (scorers)
                    |                                 |
                    +----------------+----------------+
                                     v
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
pip install "evalcraft[openai]"       # OpenAI SDK adapter
pip install "evalcraft[anthropic]"    # Anthropic SDK adapter
pip install "evalcraft[gemini]"       # Google Gemini adapter
pip install "evalcraft[pydantic-ai]"  # Pydantic AI adapter
pip install "evalcraft[langchain]"    # LangChain/LangGraph adapter

# Everything
pip install "evalcraft[all]"
```

---

## 5-minute quickstart

### 1. Capture an agent run

```python
from evalcraft import CaptureContext

with CaptureContext(
    name="weather_agent_test",
    agent_name="weather_agent",
    save_path="tests/cassettes/weather.json",
) as ctx:
    ctx.record_input("What's the weather in Paris?")

    # Run your agent — wrap tool/LLM calls with record_* methods
    ctx.record_tool_call("get_weather", args={"city": "Paris"}, result={"temp": 18, "condition": "cloudy"})
    ctx.record_llm_call(
        model="gpt-4.1-mini",
        input="User asked about weather. Tool returned: cloudy 18C",
        output="It's 18C and cloudy in Paris right now.",
        prompt_tokens=120,
        completion_tokens=15,
        cost_usd=0.0003,
    )

    ctx.record_output("It's 18C and cloudy in Paris right now.")

cassette = ctx.cassette
print(f"Captured {cassette.tool_call_count} tool calls, ${cassette.total_cost_usd:.4f}")
# Captured 1 tool calls, $0.0003
```

### 2. Replay without API calls

```python
from evalcraft import replay

# Loads the cassette and replays all spans — zero LLM calls
run = replay("tests/cassettes/weather.json")

assert run.replayed is True
assert run.cassette.output_text == "It's 18C and cloudy in Paris right now."
```

### 3. Assert tool behavior

```python
from evalcraft import replay, assert_tool_called, assert_cost_under

run = replay("tests/cassettes/weather.json")

assert assert_tool_called(run, "get_weather").passed
assert assert_tool_called(run, "get_weather", with_args={"city": "Paris"}).passed
assert assert_cost_under(run, max_usd=0.05).passed
```

### 4. Lock structured output & tool-call shape (deterministic, $0)

When your agent emits structured JSON or calls tools, validate the **shape**
with zero model calls — these run offline in milliseconds on every commit:

```python
from evalcraft import (
    replay, assert_output_json_schema, assert_output_value_in,
    assert_tool_args_match_schema,
)

run = replay("tests/cassettes/weather.json")

# The final output is JSON conforming to a schema (dict / .json file / pydantic model)
assert assert_output_json_schema(run, {
    "type": "object",
    "required": ["city", "temp_c", "status"],
    "properties": {
        "city":   {"type": "string"},
        "temp_c": {"type": "number", "minimum": -90, "maximum": 60},
        "status": {"enum": ["ok", "error"]},
    },
}).passed
assert assert_output_value_in(run, "status", ["ok", "error"]).passed

# The agent called the tool with correctly-shaped arguments — the $0 answer to a
# question other tools spend a live LLM on:
assert assert_tool_args_match_schema(run, "get_weather", {
    "type": "object", "required": ["city"],
    "properties": {"city": {"type": "string"}},
}).passed
```

Uses a pure-stdlib JSON-Schema subset by default; `pip install "evalcraft[schema]"`
for full Draft 2020-12. See [Structured Output](https://beyhangl.github.io/evalcraft/docs/user-guide/structured-output/).

### 5. LLM-as-Judge evaluation

> ⚠️ **These are live scorers.** Unlike replay + the structural scorers (which are
> offline, deterministic, and $0), the LLM-as-Judge / RAG / pairwise scorers call a
> real model at test time — they cost money, need an API key, and are non-deterministic
> (use `eval_n` + confidence intervals). See [Offline vs. live scorers](https://beyhangl.github.io/evalcraft/user-guide/scorers/).

```python
from evalcraft import replay, assert_output_semantic, assert_factual_consistency

run = replay("tests/cassettes/weather.json")

# Semantic evaluation — uses an LLM to judge output quality
result = assert_output_semantic(run, criteria="Mentions temperature and city name")
assert result.passed

# Factual consistency check
result = assert_factual_consistency(run, ground_truth="Paris is 18C and cloudy")
assert result.passed
```

### 6. RAG evaluation metrics

```python
from evalcraft import replay, assert_faithfulness, assert_answer_relevance

run = replay("tests/cassettes/rag_agent.json")
contexts = ["Paris has a population of 2.1 million...", "The Eiffel Tower..."]

# Does the output stay faithful to retrieved context?
assert assert_faithfulness(run, contexts=contexts).passed

# Does the answer address the original question?
assert assert_answer_relevance(run, query="Tell me about Paris").passed
```

### 7. Use with pytest

```python
# tests/test_weather_agent.py
from evalcraft import replay, assert_tool_called, assert_cost_under

def test_agent_calls_weather_tool():
    run = replay("tests/cassettes/weather.json")
    result = assert_tool_called(run, "get_weather")
    assert result.passed, result.message

def test_agent_cost_budget():
    run = replay("tests/cassettes/weather.json")
    result = assert_cost_under(run, max_usd=0.01)
    assert result.passed, result.message
```

```bash
pytest tests/ -v
# 200ms, $0.00
```

### 8. Pairwise A/B comparison

```python
from evalcraft import pairwise_compare, pairwise_rank

# Compare two agent outputs — LLM judge picks the winner
result = pairwise_compare(cassette_a, cassette_b, criteria="Which is more helpful?")
print(result.winner)      # "A", "B", or "tie"
print(result.confidence)  # 0.0-1.0

# Rank multiple agents via round-robin tournament
rankings = pairwise_rank([agent_a, agent_b, agent_c], criteria="Accuracy and helpfulness")
for entry in rankings:
    print(f"{entry.name}: {entry.wins}W/{entry.losses}L (score {entry.score:.2f})")
```

Position bias is mitigated by randomizing presentation order.

### 9. Statistical evaluation with confidence intervals

```python
from evalcraft import eval_n, assert_output_semantic

# Run a scorer 5 times — LLM outputs are non-deterministic, one run means nothing
result = eval_n(run, assert_output_semantic, n=5, criteria="Mentions the city name")
assert result.pass_rate >= 0.8

print(f"Pass rate: {result.pass_rate:.0%} ({result.passes}/{result.n})")
print(f"95% CI: [{result.ci_lower:.2f}, {result.ci_upper:.2f}]")
```

### 10. Auto-generate tests from cassettes

```bash
evalcraft generate-tests tests/cassettes/weather.json -o tests/test_weather.py
# Generates a complete pytest file with tool, output, cost, token, and latency assertions
```

### 11. Diagnose your setup

```bash
evalcraft doctor
#   ✓ Python 3.11.5
#   ✓ evalcraft 0.1.0
#   ✓ openai 2.30.0
#   ! anthropic not installed
#   ✓ OPENAI_API_KEY configured
#   ✓ Cassette directory: tests/cassettes/ (3 cassettes)
#   ! 1 stale cassette (>30 days old)
#   ✓ pytest plugin registered
```

---

## Examples

Four complete, self-contained example projects — each with pre-recorded cassettes,
working test suites, and step-by-step READMEs.

| Example | Scenario | What it demonstrates |
|---------|----------|---------------------|
| [openai-agent/](examples/openai-agent/) | Customer support agent (ShopEasy) | `OpenAIAdapter`, tool call assertions, golden sets, `MockLLM` + `MockTool` unit tests |
| [anthropic-agent/](examples/anthropic-agent/) | Code review bot (PRs via Claude) | `AnthropicAdapter`, multi-turn testing, security assertions, `add_sequential_responses` |
| [langgraph-workflow/](examples/langgraph-workflow/) | RAG policy Q&A pipeline | `LangGraphAdapter`, node-order assertions, `SpanKind.AGENT_STEP` inspection, citation validation |
| [ci-pipeline/](examples/ci-pipeline/) | GitHub Actions CI gate | GitHub Actions workflow, standalone gate script, cassette refresh strategy |

### Run any example in 60 seconds (no API key needed)

```bash
cd examples/openai-agent
pip install -r requirements.txt
pytest tests/ -v
# 15 tests pass in ~0.3s, $0.00
```

All cassettes are pre-recorded and committed to the repo. Tests replay
them deterministically — no API key, no network calls, no cost.

---

## How Evalcraft compares

An honest comparison against the closest tools. ✅ first-class · ⚠️ partial / via integration · ❌ no · — not applicable.

| | Evalcraft | DeepEval | Promptfoo | LangSmith | Braintrust | Ragas |
|---|---|---|---|---|---|---|
| Git-committed cassette replay | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Zero-cost CI re-runs | ✅ replay | ✅ cache | ✅ cache | ⚠️ | ❌ | — |
| pytest-native | ✅ | ✅ | ❌ CLI/YAML | ✅ | ❌ | ⚠️ library |
| First-class Mock LLM / Tools | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| LLM-as-Judge scoring | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| RAG metrics | ✅ | ✅ | ✅ | ⚠️ | ⚠️ | ✅ reference |
| Pairwise A/B | ✅ | ⚠️ | ✅ | ✅ | ✅ | ❌ |
| Statistical eval w/ confidence intervals | ✅ Wilson | ⚠️ | ⚠️ repeat | ⚠️ | ⚠️ | ❌ |
| Auto-generate tests from runs | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| OSS / self-hostable | ✅ | ✅ | ✅ | ⚠️ enterprise | ❌ enterprise | ✅ |
| Primary focus | CI / glue testing | LLM eval framework | eval + red-team | tracing + eval | eval + observability | RAG metrics |
| Pricing | Free / OSS | Free / OSS (+cloud) | Free / OSS | Paid SaaS (free tier) | Paid SaaS (free tier) | Free / OSS |

**What's genuinely distinctive** (vs. the table-stakes everyone has): git-committed, PR-diffable **cassettes** capturing full agent traces (LLM + tool + steps); **auto-generating** a pytest file from a recorded run; first-class **MockLLM / MockTool**; and a packaged **Wilson-interval** statistical helper.

**Honest caveats:**
- *Zero-cost CI is not unique* — Promptfoo (disk cache, on by default) and DeepEval (`-c`) already make re-runs free. Evalcraft's angle is *deterministic replay of a committed artifact*, not a lower bill per se.
- *Replay only re-checks a recorded run.* It does not re-execute the live model, so on its own it can't catch model/prompt/retrieval drift — see [what replay does and doesn't test](docs/user-guide/replay.md). For drift, re-record or run a live eval.
- *The LLM-as-Judge, RAG, and pairwise scorers make real, paid model calls at test time* — they are **not** part of the $0 deterministic path.
- Other strong OSS/self-hostable options not shown: **Langfuse**, **Arize Phoenix**, **Inspect AI**.

> Evalcraft is a **testing** tool for your agent's deterministic glue + budgets — not an observability platform. Use Braintrust / LangSmith / Langfuse for production tracing; use Evalcraft to keep that layer of your suite fast and committed to git.

<sub>Sources for the contested rows: [Promptfoo caching](https://www.promptfoo.dev/docs/configuration/caching/) · [DeepEval CI/CD + cache](https://deepeval.com/docs/evaluation-unit-testing-in-ci-cd) · [LangSmith pairwise](https://docs.langchain.com/langsmith/evaluate-pairwise)</sub>

---

## Features

| Feature | Description |
|---------|-------------|
| **Capture** | Record every LLM call, tool use, and agent decision as a cassette |
| **Replay** | Re-run cassettes deterministically — no API calls, zero cost |
| **Mock LLM** | Substitute real LLMs with deterministic mocks (exact / pattern / wildcard) |
| **Mock Tools** | Mock any tool with static, dynamic, sequential, or error-simulating responses |
| **Scorers** | 27 built-in assertions: tool calls, output, cost, latency, tokens, **structured output / JSON-Schema**, LLM-as-Judge, RAG metrics |
| **Structured Output** | Deterministic, `$0` shape checks — valid JSON, JSON-Schema conformance, required keys, enum, range, regex capture groups, and **tool-call-argument schema validation** — no model call |
| **LLM-as-Judge** | Semantic evaluation, factual consistency, tone, custom criteria — via OpenAI or Anthropic |
| **RAG Metrics** | Faithfulness, context relevance, answer relevance, context recall |
| **Pairwise A/B** | Arena-style comparison — LLM judge picks winner with position-bias mitigation |
| **Statistical Eval** | Run scorers N times, get pass rate with Wilson score confidence intervals |
| **Diff** | Compare two cassette runs to detect regressions |
| **Golden Sets** | Version baselines and detect regressions automatically |
| **Auto-generate** | `evalcraft generate-tests` creates pytest files from cassettes |
| **CLI** | 14 commands: replay, diff, eval, generate-tests, doctor, golden, regression, sanitize, ... |
| **pytest plugin** | Native fixtures and markers — `cassette`, `mock_llm`, `@pytest.mark.evalcraft` |
| **CI Gate** | GitHub Action with PR comments, score thresholds, regression detection |
| **JS/TS SDK** | TypeScript SDK (pre-release, source-only): capture/replay, mocks, 16 scorers, OpenAI/Gemini/Vercel AI adapters |

---

## Supported frameworks

| Framework | Adapter | Install |
|-----------|---------|---------|
| **OpenAI SDK** | `OpenAIAdapter` — auto-records `chat.completions.create` (sync + async) | `evalcraft[openai]` |
| **Anthropic SDK** | `AnthropicAdapter` — auto-records `messages.create` (sync + async) | `evalcraft[anthropic]` |
| **Google Gemini** | `GeminiAdapter` — auto-records `generate_content` (sync + async) | `evalcraft[gemini]` |
| **Pydantic AI** | `PydanticAIAdapter` — auto-records `agent.run` / `agent.run_sync` | `evalcraft[pydantic-ai]` |
| **LangGraph** | `LangGraphAdapter` — callback handler for graphs and chains | `evalcraft[langchain]` |
| **CrewAI** | `CrewAIAdapter` — instruments `Crew.kickoff()` | `evalcraft[crewai]` |
| **AutoGen** | `AutoGenAdapter` — captures multi-agent conversations | `evalcraft[autogen]` |
| **LlamaIndex** | `LlamaIndexAdapter` — hooks into query/retrieval pipeline | `evalcraft[llamaindex]` |
| **Any agent** | Manual `record_tool_call` / `record_llm_call` works with any framework | — |

### OpenAI

```python
from evalcraft.adapters import OpenAIAdapter
from evalcraft import CaptureContext
import openai

client = openai.OpenAI()

with CaptureContext(name="openai_run", save_path="tests/cassettes/openai_run.json") as ctx:
    with OpenAIAdapter():  # auto-records all LLM + tool calls
        ctx.record_input("Summarize the French Revolution")

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": "Summarize the French Revolution"}],
        )

        ctx.record_output(response.choices[0].message.content)
```

### Gemini

```python
from evalcraft.adapters import GeminiAdapter
from evalcraft import CaptureContext
import google.generativeai as genai

genai.configure(api_key="...")
model = genai.GenerativeModel("gemini-2.0-flash")

with CaptureContext(name="gemini_run", save_path="tests/cassettes/gemini_run.json") as ctx:
    with GeminiAdapter():
        ctx.record_input("What is quantum computing?")
        response = model.generate_content("What is quantum computing?")
        ctx.record_output(response.text)
```

### Pydantic AI

```python
from evalcraft.adapters import PydanticAIAdapter
from evalcraft import CaptureContext
from pydantic_ai import Agent

agent = Agent("openai:gpt-4.1-mini", system_prompt="You are helpful.")

with CaptureContext(name="pydantic_run", save_path="tests/cassettes/pydantic_run.json") as ctx:
    with PydanticAIAdapter():
        ctx.record_input("What's the weather?")
        result = agent.run_sync("What's the weather?")
        ctx.record_output(result.data)
```

---

## CI/CD integration

### GitHub Action

```yaml
# .github/workflows/evalcraft.yml
- uses: beyhangl/evalcraft@v1
  with:
    test-path: tests/
    cassette-dir: tests/cassettes
    max-cost: '0.50'
    max-regression: '10'
    post-comment: 'true'
```

The action runs your agent tests, checks cost/regression thresholds, and posts a results table as a PR comment. See [examples/ci-pipeline/](examples/ci-pipeline/) for a complete workflow.

---

## Catching drift: live-eval

Replay is deterministic and free because it **doesn't run your model** — which is
exactly why it can't catch model/prompt/retrieval **drift**. Live-eval is the
complementary layer: it runs your *real* agent over a golden set of **inputs**,
scores the live output, and gates CI when quality regresses against a baseline.

```python
from evalcraft.eval.live import LiveEvalCase, LiveEvalResult, run_live_eval, compare_to_baseline
from evalcraft import assert_output_contains

cases = [LiveEvalCase(name="paris", input="Weather in Paris?",
                      scorers=[lambda c: assert_output_contains(c, "Paris")])]

def runner(case):
    return my_agent.run(case.input)   # your REAL agent — paid, non-deterministic

result = run_live_eval(cases, runner)
comparison = compare_to_baseline(
    result, LiveEvalResult.load("live-baseline.json"), max_score_drop=0.1
)
assert comparison.passed, comparison.summary()
```

Run it nightly or as a release gate (not on every commit). See [Live Eval](https://beyhangl.github.io/evalcraft/user-guide/live-eval/).

---

## CLI reference

```
evalcraft [command] [options]
```

| Command | Description |
|---------|-------------|
| `evalcraft init` | Scaffold a test project for your framework |
| `evalcraft capture <script>` | Run a script with capture enabled |
| `evalcraft replay <cassette>` | Replay a cassette (zero API calls) |
| `evalcraft diff <old> <new>` | Compare two cassettes |
| `evalcraft eval <cassette>` | Run assertions with thresholds |
| `evalcraft info <cassette>` | Inspect cassette metadata |
| `evalcraft generate-tests <cassette>` | Auto-generate a pytest file |
| `evalcraft mock <cassette>` | Generate MockLLM fixtures from a cassette |
| `evalcraft golden save <cassette>` | Save a golden-set baseline |
| `evalcraft golden compare <cassette>` | Compare against a baseline |
| `evalcraft regression <cassette>` | Detect regressions |
| `evalcraft sanitize <cassette>` | Redact PII and secrets |
| `evalcraft doctor` | Diagnose setup issues (deps, API keys, cassettes) |
| `evalcraft live-eval <current> --baseline <b>` | Gate a live-eval run vs a baseline (catch drift) |
| `evalcraft check-stale <cassettes> --models <set>` | Fail CI when a cassette's recorded model was retired or swapped |

---

## Data model

```
Cassette
+-- id, name, agent_name, framework
+-- input_text, output_text
+-- total_tokens, total_cost_usd, total_duration_ms
+-- llm_call_count, tool_call_count
+-- fingerprint  (SHA-256 of span content -- changes when the recording changes)
+-- spans[]
    +-- Span (llm_request / llm_response)
    |   +-- model, token_usage, cost_usd
    |   +-- input, output
    +-- Span (tool_call)
        +-- tool_name, tool_args, tool_result
        +-- duration_ms, error
```

Cassettes are plain JSON — check them into git, diff them in PRs.

---

## TypeScript / JavaScript SDK

> **Status: pre-release (source-only).** The JS/TS SDK is **not yet published to npm.**
> Until it is, build it from source from this repo:

```bash
git clone https://github.com/beyhangl/evalcraft
cd evalcraft/packages/evalcraft-js
npm install && npm run build   # emits dist/ (CJS + ESM + type defs)
```

```typescript
import {
  CaptureContext, replay, assertToolCalled, assertCostUnder,  // Core
  assertOutputSemantic, assertTone, assertCustomCriteria,     // LLM-as-Judge
  assertFaithfulness, assertContextRelevance,                 // RAG metrics
} from 'evalcraft';
import { wrapOpenAI } from 'evalcraft/adapters/openai';
import { wrapGemini } from 'evalcraft/adapters/gemini';
```

The JS/TS SDK covers the core workflow — capture, replay, `MockLLM`/`MockTool`, and **16 scorers** (8 core + 4 LLM-as-Judge + 4 RAG) — with OpenAI, Gemini, and Vercel AI adapters. It is **not yet at full parity** with the Python SDK.

### Python vs JS/TS parity

| Capability | Python | JS/TS |
|---|---|---|
| Capture / replay / cassettes | ✅ | ✅ |
| `MockLLM` / `MockTool` | ✅ | ✅ |
| Core scorers (tool / output / cost / latency / tokens) | ✅ (8) | ✅ (8) |
| LLM-as-Judge scorers | ✅ (4) | ✅ (4) |
| RAG metrics | ✅ (4) | ✅ (4) |
| Pairwise A/B | ✅ | ❌ |
| Statistical eval (`eval_n`) | ✅ | ❌ |
| Multi-judge jury / consensus | ✅ | ❌ |
| Hallucination detection | ✅ | ❌ |
| Golden sets / regression / trend | ✅ | ❌ |
| CLI + pytest plugin | ✅ | ❌ |
| Framework adapters | 8 (OpenAI, Anthropic, Gemini, Pydantic AI, LangGraph, CrewAI, AutoGen, LlamaIndex) | 3 (OpenAI, Gemini, Vercel AI) |

---

## Contributing

```bash
git clone https://github.com/beyhangl/evalcraft
cd evalcraft
pip install -e ".[dev]"
pytest
```

- Format: `ruff format .`
- Lint: `ruff check .`
- Type check: `mypy evalcraft/`

PRs welcome. Please open an issue first for significant changes. See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

---

## Design Partners

**We're looking for design partners.** evalcraft is early (v0.1.0), and we'd like a few teams to help shape it. Partners get:

- **Hands-on setup help** — we'll pair with you to get evalcraft into your CI pipeline
- **Direct access to the maintainer** — not a support queue
- **Influence the roadmap** — your use cases drive what we build next

Interested? [Open an issue](https://github.com/beyhangl/evalcraft/issues) and say hi.

---

## License

MIT © 2026 Beyhan Gul. See [LICENSE](LICENSE).
