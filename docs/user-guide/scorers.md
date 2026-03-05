# Scorers

Evalcraft provides a set of assertion functions ("scorers") for evaluating cassettes and agent runs. Each function returns an `AssertionResult` rather than raising immediately, so you can collect all failures before reporting.

All scorers accept either a `Cassette` or an `AgentRun` as their first argument.

```python
from evalcraft import (
    assert_tool_called,
    assert_tool_order,
    assert_no_tool_called,
    assert_output_contains,
    assert_output_matches,
    assert_cost_under,
    assert_latency_under,
    assert_token_count_under,
)
from evalcraft.eval.scorers import Evaluator
```

---

## AssertionResult

Every scorer returns an `AssertionResult`:

```python
result = assert_tool_called(cassette, "web_search")

print(result.passed)    # True or False
print(result.name)      # "assert_tool_called(web_search)"
print(result.expected)  # "web_search"
print(result.actual)    # ["web_search", "summarize"]
print(result.message)   # "" if passed, error description if failed
```

In pytest, use `assert result.passed, result.message` to get descriptive failures:

```python
result = assert_tool_called(run, "web_search")
assert result.passed, result.message
# If failed: "Tool 'web_search' was never called. Called tools: ['search', 'analyze']"
```

---

## Tool assertions

### `assert_tool_called(cassette, tool_name, ...)`

Assert that a specific tool was called.

```python
from evalcraft import assert_tool_called, replay

run = replay("tests/cassettes/agent.json")

# Basic: tool was called at least once
result = assert_tool_called(run, "web_search")
assert result.passed

# Called exactly N times
result = assert_tool_called(run, "web_search", times=2)

# Called with specific arguments
result = assert_tool_called(run, "web_search", with_args={"query": "Paris weather"})

# Called before another tool
result = assert_tool_called(run, "web_search", before="summarize")

# Called after another tool
result = assert_tool_called(run, "summarize", after="web_search")
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `cassette` | `Cassette \| AgentRun` | The run to check |
| `tool_name` | `str` | Name of the tool |
| `times` | `int \| None` | Exact number of calls expected |
| `with_args` | `dict \| None` | Arguments that must have been passed |
| `before` | `str \| None` | Tool that should come AFTER this one |
| `after` | `str \| None` | Tool that should come BEFORE this one |

### `assert_tool_order(cassette, expected_order, strict=False)`

Assert tools were called in a specific order.

```python
# Non-strict: the tools must appear in order, but other tools can be in between
result = assert_tool_order(run, ["web_search", "summarize", "send_email"])
assert result.passed

# Strict: the sequence must match exactly
result = assert_tool_order(
    run,
    ["web_search", "summarize", "send_email"],
    strict=True,
)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `cassette` | `Cassette \| AgentRun` | The run to check |
| `expected_order` | `list[str]` | Expected tool names in order |
| `strict` | `bool` | If `True`, exact match required. If `False`, subsequence match. |

### `assert_no_tool_called(cassette, tool_name)`

Assert a specific tool was NOT called.

```python
result = assert_no_tool_called(run, "send_email")
assert result.passed, result.message
# If failed: "Tool 'send_email' was called 1 times, expected 0"
```

---

## Output assertions

### `assert_output_contains(cassette, substring, case_sensitive=True)`

Assert the agent's output contains a substring.

```python
result = assert_output_contains(run, "Paris")
assert result.passed

# Case-insensitive
result = assert_output_contains(run, "paris", case_sensitive=False)
assert result.passed
```

### `assert_output_matches(cassette, pattern)`

Assert the agent's output matches a regex pattern.

```python
result = assert_output_matches(run, r"\d+°C")
assert result.passed, result.message
# If failed: "Output does not match pattern '\\d+°C'"

result = assert_output_matches(run, r"(sunny|cloudy|rainy)")
assert result.passed
```

---

## Cost and performance assertions

### `assert_cost_under(cassette, max_usd)`

Assert the total estimated cost is under a threshold.

```python
result = assert_cost_under(run, max_usd=0.05)
assert result.passed
# If failed: "Cost $0.0823 exceeds limit $0.0500"
```

!!! note
    Cost is only available if recorded during capture (e.g., via `record_llm_call(cost_usd=...)` or an adapter that estimates cost).

### `assert_latency_under(cassette, max_ms)`

Assert total wall-clock time is under a threshold (in milliseconds).

```python
result = assert_latency_under(run, max_ms=5000)
assert result.passed
# If failed: "Latency 6234.0ms exceeds limit 5000.0ms"
```

### `assert_token_count_under(cassette, max_tokens)`

Assert total token count is under a threshold.

```python
result = assert_token_count_under(run, max_tokens=2000)
assert result.passed
# If failed: "Token count 2341 exceeds limit 2000"
```

---

## Evaluator

The `Evaluator` class lets you compose multiple assertions into a single evaluation.

```python
from evalcraft.eval.scorers import Evaluator
from evalcraft import (
    assert_tool_called,
    assert_tool_order,
    assert_cost_under,
    assert_token_count_under,
    assert_output_contains,
    replay,
)

run = replay("tests/cassettes/agent.json")

evaluator = Evaluator()
evaluator.add(assert_tool_called, run, "web_search")
evaluator.add(assert_tool_order, run, ["web_search", "summarize"])
evaluator.add(assert_cost_under, run, max_usd=0.05)
evaluator.add(assert_token_count_under, run, max_tokens=2000)
evaluator.add(assert_output_contains, run, "summary")

result = evaluator.run()

print(result.passed)          # True if all pass
print(result.score)           # e.g. 0.8 = 4/5 passed
print(len(result.assertions)) # 5

for assertion in result.assertions:
    status = "PASS" if assertion.passed else "FAIL"
    print(f"[{status}] {assertion.name}")
    if not assertion.passed:
        print(f"       {assertion.message}")
```

#### `Evaluator.add(assertion_fn, *args, **kwargs)`

Add an assertion to run.

```python
evaluator.add(assert_cost_under, cassette, max_usd=0.10)
```

Returns `self` for chaining.

#### `Evaluator.run()`

Run all assertions and return an `EvalResult`.

### `EvalResult` fields

| Field | Type | Description |
|-------|------|-------------|
| `passed` | `bool` | True if all assertions passed |
| `score` | `float` | Fraction of assertions that passed (0.0–1.0) |
| `assertions` | `list[AssertionResult]` | Individual assertion results |
| `failed_assertions` | `list[AssertionResult]` | Only failed assertions |

```python
result = evaluator.run()
if not result.passed:
    for a in result.failed_assertions:
        print(f"FAIL: {a.name} — {a.message}")
```

---

## Complete example

```python
import pytest
from evalcraft import replay
from evalcraft import (
    assert_tool_called,
    assert_tool_order,
    assert_no_tool_called,
    assert_output_contains,
    assert_cost_under,
    assert_token_count_under,
    assert_latency_under,
)
from evalcraft.eval.scorers import Evaluator


@pytest.fixture
def run():
    return replay("tests/cassettes/research_agent.json")


def test_searches_before_summarizing(run):
    result = assert_tool_called(run, "web_search", before="summarize")
    assert result.passed, result.message


def test_no_email_sent(run):
    result = assert_no_tool_called(run, "send_email")
    assert result.passed, result.message


def test_output_is_informative(run):
    result = assert_output_contains(run, "summary", case_sensitive=False)
    assert result.passed, result.message


def test_budget(run):
    evaluator = Evaluator()
    evaluator.add(assert_cost_under, run, max_usd=0.10)
    evaluator.add(assert_token_count_under, run, max_tokens=3000)
    evaluator.add(assert_latency_under, run, max_ms=10_000)

    result = evaluator.run()
    assert result.passed, "\n".join(
        f"{a.name}: {a.message}" for a in result.failed_assertions
    )
```
