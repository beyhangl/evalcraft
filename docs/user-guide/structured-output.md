# Structured output ($0 shape checks)

Modern agents increasingly return **structured JSON** — function calling,
`response_format`, structured outputs. Evalcraft's structured-output scorers let
you lock the *shape* of that output, and of every tool call, with assertions
that are **offline, deterministic, and `$0`**: they read only what the cassette
already recorded and never call a model or the network.

This is the cheap half of agent testing made concrete. Instead of paying an
LLM judge to answer "did the agent return the right fields / call the tool with
the right arguments?", you answer it with a byte-stable `pytest` assertion that
runs in milliseconds on every commit.

!!! tip "When to reach for these vs. an LLM judge"
    Use these for **shape** — is it valid JSON, does it have the required keys,
    are the values the right type / in the allowed set / in range, did the tool
    get called with conforming arguments. Use an [LLM-as-Judge scorer](scorers.md)
    only for **quality** — is the prose helpful, faithful, on-tone — which
    genuinely needs a live model.

## The output is valid JSON

```python
from evalcraft import replay, assert_output_json

run = replay("tests/cassettes/extractor.json")
assert assert_output_json(run).passed

# Agents often wrap JSON in prose or a ```json fence — accept that too:
assert assert_output_json(run, embedded=True).passed
```

## The output conforms to a schema

`assert_output_json_schema` accepts a schema as a **dict**, a path to a
committed **`.json` file**, an inline **JSON string**, or a **pydantic model
class** (pydantic is already a core dependency):

```python
from evalcraft import replay, assert_output_json_schema

run = replay("tests/cassettes/weather.json")

assert assert_output_json_schema(run, {
    "type": "object",
    "required": ["city", "temp_c", "status"],
    "properties": {
        "city":   {"type": "string", "minLength": 1},
        "temp_c": {"type": "number", "minimum": -90, "maximum": 60},
        "status": {"enum": ["ok", "error"]},
    },
}).passed
```

…or straight from a pydantic model you already have:

```python
from pydantic import BaseModel

class Weather(BaseModel):
    city: str
    temp_c: float
    status: str

assert assert_output_json_schema(run, Weather).passed
```

### Which schema engine runs

By default the validator uses a small, **pure-stdlib** JSON-Schema *subset*
(`type`, `required`, `properties`, `enum`, `const`, `minimum`/`maximum`/
exclusive bounds, `minLength`/`maxLength`, `pattern`, `items`, `minItems`/
`maxItems`, `uniqueItems`, `anyOf`/`allOf`/`oneOf`, and local `$ref` + `$defs`).
That covers the vast majority of agent-output schemas with **zero new
dependencies**.

If you install the optional `jsonschema` package it is used transparently for
full **Draft 2020-12** coverage:

```bash
pip install "evalcraft[schema]"
```

The built-in validator is deliberately strict: if a schema uses a keyword it
does **not** implement, it raises a clear error pointing you at
`evalcraft[schema]` — so a test can never get a false **PASS** from a construct
that was silently ignored. Force a specific engine with `engine="builtin"` or
`engine="jsonschema"` (default `"auto"`).

## Field-level assertions

For quick checks you don't need a whole schema for. Paths are dotted with
bracket/index support (`"user.id"`, `"items.0.name"`, `"items[0].name"`):

```python
from evalcraft import (
    assert_output_has_keys, assert_output_field,
    assert_output_value_in, assert_output_value_in_range,
)

assert assert_output_has_keys(run, ["city", "temp_c"]).passed
assert assert_output_field(run, "city", equals="Paris").passed
assert assert_output_value_in(run, "status", ["ok", "error"]).passed
assert assert_output_value_in_range(run, "temp_c", minimum=-90, maximum=60).passed
```

## Regex with capture groups

`assert_output_matches` tells you *whether* the output matches a pattern;
`assert_match_groups` checks *what* it captured:

```python
from evalcraft import assert_match_groups

# order id "#4521" -> group "4521"
assert assert_match_groups(run, r"#(\d+)", expected_groups=("4521",)).passed
# named groups
assert assert_match_groups(run, r"status=(?P<s>\w+)", expected_named={"s": "done"}).passed
```

## Lock the shape of tool-call arguments

The agent-native one. Other tools spend a live LLM to judge whether a tool was
called with sensible arguments; evalcraft validates the recorded `tool_args`
against a schema **deterministically, for `$0`**:

```python
from evalcraft import replay, assert_tool_args_match_schema

run = replay("tests/cassettes/booking.json")

assert assert_tool_args_match_schema(run, "book_flight", {
    "type": "object",
    "required": ["origin", "destination", "date"],
    "properties": {
        "origin":      {"type": "string", "pattern": "^[A-Z]{3}$"},
        "destination": {"type": "string", "pattern": "^[A-Z]{3}$"},
        "date":        {"type": "string"},
        "cabin":       {"enum": ["economy", "business", "first"]},
    },
}).passed
```

`which="all"` (default) requires every recorded call to `book_flight` to
conform; `which="any"` passes if at least one does.

## It's automatic in `generate-tests`

When you scaffold tests from a cassette whose output is JSON,
`evalcraft generate-tests` now emits `assert_output_json` and
`assert_output_has_keys(...)` tests for you, so the output's shape is locked
from the first run:

```bash
evalcraft generate-tests tests/cassettes/extractor.json -o tests/test_extractor.py
```

## Why this is the right layer to own

- **Deterministic & `$0`.** No model, no network, no flakiness — runs on every
  commit in milliseconds and never bills you.
- **Git-diffable.** The cassette is committed; the schema is committed. A shape
  regression shows up as a failing test in the PR, not a surprise in production.
- **Agent-shaped.** Tool-call-argument validation tests the agent's *plumbing*
  (did it wire the right arguments into the right tool), which is exactly the
  layer replay + structural scorers are built to keep fast and committed.
