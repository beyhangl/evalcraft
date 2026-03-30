<p align="center">
  <img src="site/logo.png" alt="Evalcraft" width="400" />
</p>
<p align="center"><strong>The pytest for AI agents.</strong> Capture, replay, mock, and evaluate agent behavior — without burning API credits on every test run.</p>

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

Evalcraft fixes this by recording agent runs as **cassettes** (like VCR for HTTP), then replaying them deterministically. Your test suite goes from 10 minutes + $5 to 200ms + $0.

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

### 4. LLM-as-Judge evaluation

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

### 5. RAG evaluation metrics

```python
from evalcraft import replay, assert_faithfulness, assert_answer_relevance

run = replay("tests/cassettes/rag_agent.json")
contexts = ["Paris has a population of 2.1 million...", "The Eiffel Tower..."]

# Does the output stay faithful to retrieved context?
assert assert_faithfulness(run, contexts=contexts).passed

# Does the answer address the original question?
assert assert_answer_relevance(run, query="Tell me about Paris").passed
```

### 6. Use with pytest

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

### 7. Auto-generate tests from cassettes

```bash
evalcraft generate-tests tests/cassettes/weather.json -o tests/test_weather.py
# Generates a complete pytest file with tool, output, cost, token, and latency assertions
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

## Why Evalcraft?

| | Evalcraft | Braintrust | LangSmith | Promptfoo |
|---|---|---|---|---|
| Cassette-based replay | **Yes** | No | No | No |
| Zero-cost CI testing | **Yes** | No | No | Partial |
| pytest-native | **Yes** | No | No | No |
| Mock LLM / Tools | **Yes** | No | No | No |
| LLM-as-Judge scoring | **Yes** | Yes | Yes | Yes |
| RAG evaluation metrics | **Yes** | No | No | No |
| Auto-test generation | **Yes** | No | No | No |
| Framework agnostic | **Yes** | Yes | Yes | Yes |
| Self-hostable | **Yes** | No | Partial | Yes |
| Pricing | Free / OSS | Paid SaaS | Paid SaaS | Free / OSS |

> Evalcraft is a **testing** tool, not an observability platform. Use Braintrust or LangSmith for production tracing; use Evalcraft to keep your test suite fast and free.

---

## Features

| Feature | Description |
|---------|-------------|
| **Capture** | Record every LLM call, tool use, and agent decision as a cassette |
| **Replay** | Re-run cassettes deterministically — no API calls, zero cost |
| **Mock LLM** | Substitute real LLMs with deterministic mocks (exact / pattern / wildcard) |
| **Mock Tools** | Mock any tool with static, dynamic, sequential, or error-simulating responses |
| **Scorers** | 16 built-in assertions: tool calls, output, cost, latency, tokens, LLM-as-Judge, RAG metrics |
| **LLM-as-Judge** | Semantic evaluation, factual consistency, tone, custom criteria — via OpenAI or Anthropic |
| **RAG Metrics** | Faithfulness, context relevance, answer relevance, context recall |
| **Diff** | Compare two cassette runs to detect regressions |
| **Golden Sets** | Version baselines and detect regressions automatically |
| **Auto-generate** | `evalcraft generate-tests` creates pytest files from cassettes |
| **CLI** | `evalcraft replay`, `evalcraft diff`, `evalcraft eval`, `evalcraft generate-tests` |
| **pytest plugin** | Native fixtures and markers — `cassette`, `mock_llm`, `@pytest.mark.evalcraft` |
| **CI Gate** | GitHub Action with PR comments, score thresholds, regression detection |
| **JS/TS SDK** | Full TypeScript SDK with feature parity — scorers, mocks, adapters |

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

---

## Data model

```
Cassette
+-- id, name, agent_name, framework
+-- input_text, output_text
+-- total_tokens, total_cost_usd, total_duration_ms
+-- llm_call_count, tool_call_count
+-- fingerprint  (SHA-256 of span content -- detects regressions)
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

```bash
npm install evalcraft
```

```typescript
import { CaptureContext, replay, assertToolCalled, assertCostUnder } from 'evalcraft';
import { assertOutputSemantic, assertFaithfulness } from 'evalcraft';
import { wrapOpenAI } from 'evalcraft/adapters/openai';
import { wrapGemini } from 'evalcraft/adapters/gemini';
```

Full feature parity with the Python SDK — scorers, mocks, LLM-as-Judge, RAG metrics, and framework adapters.

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

We're working with 10 early teams to shape evalcraft. Design partners get:

- **Hands-on setup help** — we'll pair with you to get evalcraft into your CI pipeline
- **Direct Slack access** — talk to the maintainers, not a support queue
- **Influence the roadmap** — your use cases drive what we build next

Interested? [Sign up here](https://beyhangl.github.io/evalcraft/#frameworks) or email us directly.

---

## License

MIT © 2026 Beyhan Gul. See [LICENSE](LICENSE).
