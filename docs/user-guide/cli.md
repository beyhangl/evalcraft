# CLI Reference

Evalcraft ships a command-line tool with 6 commands for working with cassettes.

```bash
evalcraft [command] [options]
```

Get help at any level:

```bash
evalcraft --help
evalcraft capture --help
evalcraft replay --help
```

---

## `evalcraft capture`

Run a Python script with evalcraft capture enabled and save the cassette.

```bash
evalcraft capture SCRIPT [OPTIONS]
```

The script is executed in the current Python interpreter with a `CaptureContext` active, so any evalcraft instrumentation in the script (`record_llm_call`, `record_tool_call`, etc.) is automatically recorded.

### Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--output PATH` | `-o` | `<script>.cassette.json` | Output cassette path |
| `--name NAME` | `-n` | `<script stem>` | Cassette name |
| `--agent NAME` | `-a` | `""` | Agent name tag |
| `--framework NAME` | `-f` | `""` | Framework tag |

### Example

```bash
# Capture with default output path
evalcraft capture my_agent.py

# Capture with explicit output
evalcraft capture my_agent.py --output cassettes/run1.json --name "weather_test" --agent "weather_agent"
```

**Output:**

```
  capturing  my_agent.py  →  cassettes/run1.json
  saved      cassettes/run1.json
  spans=4  llm=1  tools=1  tokens=135  cost=$0.0008  time=450ms
```

### How it works

`evalcraft capture` uses `runpy.run_path()` to execute the script in the same Python interpreter, with a `CaptureContext` active as the global context. Any calls to `record_llm_call()`, `record_tool_call()`, or mock completions are recorded into the cassette.

```python
# my_agent.py — example script to capture
from evalcraft.capture.recorder import record_llm_call, record_tool_call

record_tool_call("get_weather", args={"city": "Paris"}, result={"temp": 18})
record_llm_call(
    model="gpt-4o",
    input="Weather data: 18°C",
    output="It's 18°C in Paris.",
    prompt_tokens=50,
    completion_tokens=10,
    cost_usd=0.0003,
)
```

---

## `evalcraft replay`

Replay a cassette and display the results.

```bash
evalcraft replay CASSETTE [OPTIONS]
```

Feeds recorded responses back through the replay engine without making any real LLM API calls.

### Options

| Option | Short | Description |
|--------|-------|-------------|
| `--verbose` | `-v` | Show each span |

### Example

```bash
evalcraft replay cassettes/run1.json
```

**Output:**

```
  replaying  run1.json

  name         weather_test
  agent        weather_agent
  framework    —
  fingerprint  a3f1c2d4e5b6a7c8
  spans        4
  llm calls    1
  tool calls   1
  tokens       135
  cost         $0.0008
  duration     450ms

  output:
  It's 18°C and cloudy in Paris right now.

  done
```

**Verbose mode:**

```bash
evalcraft replay cassettes/run1.json --verbose
```

Shows each span with kind, name, and token count:

```
  spans:
  [0]  user_input
  [1]  tool_call              get_weather
  [2]  llm_response           gpt-4o  (135t)
  [3]  agent_output
```

---

## `evalcraft diff`

Compare two cassettes and show what changed.

```bash
evalcraft diff OLD NEW [OPTIONS]
```

Useful for detecting regressions between agent runs — changes in tool order, output text, token usage, or cost.

### Options

| Option | Description |
|--------|-------------|
| `--json` | Output diff as JSON |

### Example

```bash
evalcraft diff cassettes/baseline.json cassettes/new_run.json
```

**Output (no changes):**

```
  diff  baseline.json  →  new_run.json

  =  tool sequence          unchanged
  =  output text            unchanged
  =  token count            unchanged
  =  cost                   unchanged
  =  span count             unchanged
```

**Output (with changes):**

```
  diff  baseline.json  →  new_run.json

  ~  tool sequence          ['web_search']  →  ['web_search', 'summarize']
  =  output text            unchanged
  ~  token count            135  →  420
  ~  cost                   $0.0008  →  $0.0024
  ~  span count             4  →  6
```

**JSON output:**

```bash
evalcraft diff baseline.json new_run.json --json
```

```json
{
  "has_changes": true,
  "tool_sequence_changed": true,
  "output_changed": false,
  "token_count_changed": true,
  "cost_changed": true,
  "span_count_changed": true,
  "old_tool_sequence": ["web_search"],
  "new_tool_sequence": ["web_search", "summarize"],
  "old_tokens": 135,
  "new_tokens": 420,
  "old_cost": 0.0008,
  "new_cost": 0.0024
}
```

Use in CI to fail if changes are detected:

```bash
DIFF=$(evalcraft diff baseline.json current.json --json)
if echo "$DIFF" | python -c "import sys, json; d=json.load(sys.stdin); sys.exit(1 if d['has_changes'] else 0)"; then
  echo "No regression"
else
  echo "Agent behavior changed!" && exit 1
fi
```

---

## `evalcraft eval`

Run eval assertions on a cassette and report pass/fail.

```bash
evalcraft eval CASSETTE [OPTIONS]
```

Without thresholds, prints a metrics summary. With thresholds, runs assertions and exits with code `1` if any fail (useful in CI).

### Options

| Option | Description |
|--------|-------------|
| `--max-cost USD` | Maximum acceptable cost in USD |
| `--max-tokens N` | Maximum acceptable token count |
| `--max-latency MS` | Maximum acceptable latency in milliseconds |
| `--tool NAME` | Tool that must have been called (repeatable) |
| `--json` | Output as JSON |

### Example — metrics summary (no thresholds)

```bash
evalcraft eval cassettes/run1.json
```

```
  eval  run1.json

  metrics (no thresholds set)
  tokens    135
  cost      $0.0008
  latency   450ms
  llm       1 calls
  tools     ['get_weather']
```

### Example — with thresholds

```bash
evalcraft eval cassettes/run1.json \
    --max-cost 0.05 \
    --max-tokens 4000 \
    --tool get_weather \
    --tool summarize
```

```
  eval  run1.json

  PASS  assert_cost_under($0.05)
  PASS  assert_token_count_under(4000)
  PASS  assert_tool_called(get_weather)
  FAIL  assert_tool_called(summarize)
        Tool 'summarize' was never called. Called tools: ['get_weather']
        expected: summarize
        actual:   ['get_weather']

  score: 75%  (3/4 passed)
```

Exit code is `1` if any assertion fails — ideal for CI gates.

### Example — JSON output

```bash
evalcraft eval cassettes/run1.json --max-cost 0.05 --json
```

```json
{
  "passed": true,
  "score": 1.0,
  "assertions": [
    {
      "name": "assert_cost_under($0.05)",
      "passed": true,
      "expected": 0.05,
      "actual": 0.0008,
      "message": ""
    }
  ],
  "metadata": {}
}
```

---

## `evalcraft info`

Show metadata for a cassette — spans, tools, tokens, cost.

```bash
evalcraft info CASSETTE [OPTIONS]
```

### Options

| Option | Description |
|--------|-------------|
| `--json` | Output raw cassette JSON |
| `--spans` | Show all spans |

### Example

```bash
evalcraft info cassettes/run1.json
```

```
  cassette info

  id           a1b2c3d4-e5f6-7890-abcd-ef1234567890
  name         weather_test
  agent        weather_agent
  framework    —
  version      1.0
  created      2026-03-05 14:23:11
  fingerprint  a3f1c2d4e5b6a7c8

  metrics
  spans        4
  llm calls    1
  tool calls   1
  tokens       135
  cost         $0.0008
  duration     450ms

  tool sequence
    1.  get_weather

  input:
  What's the weather in Paris?

  output:
  It's 18°C and cloudy in Paris right now.
```

**Show all spans:**

```bash
evalcraft info cassettes/run1.json --spans
```

```
  all spans
  [0]  user_input              user_input
  [1]  tool_call               get_weather              120ms
  [2]  llm_response            gpt-4o                   320ms  135t  $0.0008
  [3]  agent_output            agent_output
```

**Raw JSON:**

```bash
evalcraft info cassettes/run1.json --json
```

---

## `evalcraft mock`

Generate `MockLLM` and tool fixtures from a cassette.

```bash
evalcraft mock CASSETTE [OPTIONS]
```

Emits a Python module with a factory function that returns a `MockLLM` pre-loaded with all recorded responses, plus a `TOOL_RESULTS` dict — ready to paste into your test suite.

### Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--output PATH` | `-o` | stdout | Output Python file |
| `--var NAME` | | `mock_llm` | Variable name for the MockLLM factory |

### Example

```bash
evalcraft mock cassettes/run1.json --output tests/fixtures/mock_agent.py
```

**Output:**

```
  generated  tests/fixtures/mock_agent.py
  llm responses: 1
  tool fixtures: 1
```

**Generated file:**

```python
"""Auto-generated mock fixtures.
   Source:    run1.json
   Agent:     weather_agent
   Framework: (unknown)
   LLM spans: 1
   Tools:     1
"""

from evalcraft.mock.llm import MockLLM
from evalcraft.replay.engine import ReplayEngine


def make_mock_llm() -> MockLLM:
    """MockLLM with 1 recorded response(s)."""
    mock = MockLLM(model='mock-llm')

    # LLM call 0
    mock.add_response(
        'Weather data: 18°C',
        "It's 18°C and cloudy in Paris right now.",
        prompt_tokens=120,
        completion_tokens=15,
    )

    return mock


# Recorded tool results — override as needed in your tests
TOOL_RESULTS: dict = {
    'get_weather': {'temp': 18, 'condition': 'cloudy'},
}


def make_replay_engine(cassette_path: str) -> ReplayEngine:
    """ReplayEngine pre-loaded with recorded tool results."""
    engine = ReplayEngine(cassette_path)
    engine.override_tool_result('get_weather', TOOL_RESULTS['get_weather'])
    return engine
```

Use the generated fixtures in tests:

```python
from tests.fixtures.mock_agent import make_mock_llm, TOOL_RESULTS

def test_with_generated_fixtures():
    llm = make_mock_llm()
    result = llm.complete("Weather data: 18°C")
    assert result.content == "It's 18°C and cloudy in Paris right now."
```

---

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | Assertion failure (`eval` command) or unhandled error |

Use exit codes in CI scripts:

```bash
evalcraft eval cassettes/run.json --max-cost 0.05 --tool web_search
if [ $? -ne 0 ]; then
    echo "Eval failed — blocking deploy"
    exit 1
fi
```
