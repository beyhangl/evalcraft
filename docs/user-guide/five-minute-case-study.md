# Case Study: How a Weather Agent Team Caught a $50/day Regression

This is the story of a team that saved $1,500/month by catching a broken model swap before it hit production — in under 5 minutes of CI time.

---

## The setup

**Team:** 3 engineers at a logistics startup building a weather-aware routing agent.

**Agent:** Takes a city name, calls a `get_weather` tool, and returns a natural-language forecast. Powers route planning for 10,000+ daily deliveries.

**Stack:** Python, OpenAI SDK (GPT-4o), pytest, GitHub Actions.

The agent is straightforward — one tool call, one LLM call:

```python
# agent.py
import openai

client = openai.OpenAI()

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather for a city",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
    }
]


def run_weather_agent(city: str) -> str:
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": f"What's the weather in {city}?"}],
        tools=TOOLS,
    )
    # ... handle tool calls, return final answer
    return response.choices[0].message.content
```

---

## Step 1: Record the baseline

The team installs evalcraft and records their first cassette:

```bash
pip install "evalcraft[openai]"
evalcraft init
```

```python
# record.py
from evalcraft import CaptureContext
from evalcraft.adapters import OpenAIAdapter
import openai

client = openai.OpenAI()

with CaptureContext(
    name="weather_paris",
    agent_name="weather_agent",
    save_path="tests/cassettes/weather_paris.json",
) as ctx:
    ctx.record_input("What's the weather in Paris?")

    with OpenAIAdapter():
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "What's the weather in Paris?"}],
            tools=[{
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get current weather for a city",
                    "parameters": {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                        "required": ["city"],
                    },
                },
            }],
        )

    ctx.record_output(response.choices[0].message.content)
```

```bash
python record.py
# Saved tests/cassettes/weather_paris.json
# spans=3  llm=1  tools=1  tokens=185  cost=$0.0028
```

They write tests:

```python
# tests/test_weather.py
from evalcraft import (
    replay,
    assert_tool_called,
    assert_cost_under,
    assert_token_count_under,
    assert_output_contains,
)
from evalcraft.eval.scorers import Evaluator

CASSETTE = "tests/cassettes/weather_paris.json"


def test_calls_weather_tool():
    run = replay(CASSETTE)
    result = assert_tool_called(run, "get_weather")
    assert result.passed, result.message


def test_passes_correct_city():
    run = replay(CASSETTE)
    result = assert_tool_called(run, "get_weather", with_args={"city": "Paris"})
    assert result.passed, result.message


def test_output_mentions_city():
    run = replay(CASSETTE)
    result = assert_output_contains(run, "Paris")
    assert result.passed, result.message


def test_budget():
    run = replay(CASSETTE)
    evaluator = Evaluator()
    evaluator.add(assert_cost_under, run, max_usd=0.01)
    evaluator.add(assert_token_count_under, run, max_tokens=500)
    result = evaluator.run()
    assert result.passed, "\n".join(
        f"{a.name}: {a.message}" for a in result.failed_assertions
    )
```

```bash
pytest tests/test_weather.py -v
# test_calls_weather_tool    PASSED  (11ms)
# test_passes_correct_city   PASSED  ( 9ms)
# test_output_mentions_city  PASSED  ( 8ms)
# test_budget                PASSED  ( 7ms)
# 4 passed in 0.04s
```

They create a golden set baseline:

```bash
evalcraft golden save tests/cassettes/weather_paris.json --name weather_agent
# Saved golden/weather_agent.golden.json
```

And add the CI gate:

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
          max-cost: '0.05'
          max-regression: '10%'
```

All tests pass. The golden set is committed. CI is green.

---

## Step 2: The "cost savings" PR

A week later, an engineer opens a PR to switch from `gpt-4o` to `gpt-4o-mini` for cost savings. The change looks harmless — just one line:

```diff
- model="gpt-4o",
+ model="gpt-4o-mini",
```

They re-record the cassette with the new model:

```bash
python record.py
# spans=2  llm=1  tools=0  tokens=92  cost=$0.0001
```

Wait — `tools=0`? The agent didn't call the weather tool this time. `gpt-4o-mini` decided to answer the weather question directly instead of calling the tool.

They commit the updated cassette and push.

---

## Step 3: CI catches the regression

The evalcraft GitHub Action runs on the PR. Three tests fail immediately:

```
FAILED test_calls_weather_tool
  AssertionError: Tool 'get_weather' was never called. Called tools: []

FAILED test_passes_correct_city
  AssertionError: Tool 'get_weather' was never called. Called tools: []

FAILED test_budget
  assert_token_count_under: Token count 92 — PASSED
  assert_cost_under: Cost $0.0001 — PASSED
  (but the tool assertions already caught the real issue)
```

The action posts a PR comment:

```
## 🧪 Evalcraft Agent Test Results — ❌ Failed

| Metric           | Value     |
|------------------|-----------|
| Cassettes        | 1         |
| Total tokens     | 92        |
| Total cost       | $0.0001   |
| Total tool calls | 0         |

### ⚠️ Threshold Violations

- `weather_paris` tokens increased by **0.0%** — within limits
- 3 pytest assertions failed — see test output above
```

The team sees the problem instantly: **the cheaper model doesn't reliably use tools.** The agent is now hallucinating weather data instead of looking it up.

---

## Step 4: The fix

The engineer adds an explicit instruction to the system prompt:

```diff
  messages=[
+     {"role": "system", "content": "Always use the get_weather tool to look up weather data. Never guess."},
      {"role": "user", "content": f"What's the weather in {city}?"},
  ],
```

They re-record and re-run:

```bash
python record.py
# spans=3  llm=1  tools=1  tokens=110  cost=$0.0002

pytest tests/test_weather.py -v
# 4 passed in 0.04s
```

The model swap works now — tool calling is reliable, and the cost dropped from $0.0028 to $0.0002 per call.

At 10,000 calls/day, that's:

- **Before:** $28/day ($840/month)
- **Broken version:** $1/day — but returning wrong data
- **Fixed version:** $2/day ($60/month) — correct data, 93% cost reduction

They update the golden set and push:

```bash
evalcraft golden save tests/cassettes/weather_paris.json --name weather_agent
git add tests/cassettes/ golden/
git commit -m "feat: switch to gpt-4o-mini with explicit tool instruction"
```

CI goes green. The PR merges.

---

## What evalcraft caught

Without evalcraft, this regression would have shipped silently:

| | Without evalcraft | With evalcraft |
|---|---|---|
| **Detection** | Users report wrong forecasts days later | CI fails in 30 seconds |
| **Cost of bug** | $50/day in bad routing decisions | $0 — caught before merge |
| **Time to fix** | Hours of debugging production logs | Minutes — test tells you exactly what broke |
| **Confidence** | "I think it works?" | 4 passing assertions + golden set comparison |

---

## Try it yourself

The full weather agent example is in the repo — cassettes included, no API key needed:

```bash
git clone https://github.com/beyhangl/evalcraft
cd evalcraft/examples/openai-agent
pip install -r requirements.txt
pytest tests/ -v
# 15 tests pass in ~0.3s, $0.00
```

Or start from scratch with your own agent:

```bash
pip install "evalcraft[openai]"
evalcraft init
```

See the [quickstart](quickstart.md) for the full step-by-step guide.

---

## Get started

We're working with 10 early teams to shape evalcraft. Design partners get hands-on setup help, direct Slack access, and influence over the roadmap.

[Sign up as a design partner](https://beyhangl.github.io/evalcraft/#frameworks) or jump straight into the [quickstart](quickstart.md).
