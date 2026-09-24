---
name: evalcraft
description: Write offline, $0 pytest tests for AI agents with evalcraft. Record an agent run to a cassette, generate tests from it, and assert which tools were called, their argument schemas, the output shape, loops, and cost/token/latency budgets. Also check saved cassettes for retired or swapped models. Use when the user imports evalcraft, mentions cassettes or agent regression tests, or asks to test an LLM agent's tool calls, add a cost budget, catch an agent that stopped calling a tool, or detect a retired model in saved test recordings.
license: MIT
compatibility: Requires Python 3.10+ and pytest 8+
metadata:
  version: "0.8.0"
---

# Testing AI agents with evalcraft

evalcraft asserts the deterministic parts of an agent run: which tools ran, in
what order, with which arguments, what shape came back, whether it looped, and
what it cost. The assertions read a run that was already recorded (a
"cassette", plain JSON committed to git), so they run offline, in milliseconds,
for $0. No model is called.

Every assertion returns an `AssertionResult`. Always assert `.passed` and
surface `.message` so a failure explains itself:

```python
result = assert_tool_called(run, "lookup_order")
assert result.passed, result.message
```

## Task 1 — Add evalcraft tests for an agent

1. Record one real run. Wrap the agent with the adapter for its SDK
   (`OpenAIAdapter`, `AnthropicAdapter`, `GeminiAdapter`, `PydanticAIAdapter`,
   `LangGraphAdapter`, `CrewAIAdapter`, `AutoGenAdapter`, `LlamaIndexAdapter`)
   inside a `CaptureContext`:

   ```python
   from evalcraft import CaptureContext
   from evalcraft.adapters import OpenAIAdapter

   with CaptureContext(name="order_status", save_path="tests/cassettes/order_status.json") as ctx:
       with OpenAIAdapter():
           ctx.record_input("Where is order 4521?")
           answer = my_agent.run("Where is order 4521?")
           ctx.record_output(answer)
   ```

   No SDK adapter? Call `ctx.record_tool_call(name, args=..., result=...)` and
   `ctx.record_llm_call(model=..., input=..., output=..., prompt_tokens=...,
   completion_tokens=..., cost_usd=...)` yourself.

2. Write tests against the recording with `replay()`:

   ```python
   from evalcraft import (
       replay, assert_tool_called, assert_tool_args_match_schema,
       assert_tool_trajectory, assert_no_loops, assert_cost_under,
   )

   def test_order_status_agent():
       run = replay("tests/cassettes/order_status.json")
       for result in [
           assert_tool_called(run, "lookup_order"),
           assert_tool_args_match_schema(run, "lookup_order", {
               "type": "object", "required": ["order_id"],
               "properties": {"order_id": {"type": "string"}},
           }),
           assert_tool_trajectory(run, ["lookup_order", "send_reply"], mode="unordered"),
           assert_no_loops(run),
           assert_cost_under(run, max_usd=0.05),
       ]:
           assert result.passed, result.message
   ```

3. Commit the cassette with the test. Run `pytest`.

## Task 2 — Generate tests from a recording

```bash
evalcraft generate-tests tests/cassettes/order_status.json -o tests/test_order_status.py
```

This writes a real pytest file with tool, output, cost, token, latency and
loop assertions taken from the recording. Review it; tighten the budgets it
picks (it uses roughly 2–3x the recorded values).

To test agent *code* changes without a live model, turn the recording into
mocks and run the real agent against them:

```bash
evalcraft mock tests/cassettes/order_status.json -o tests/fixtures/mock_order.py
```

## Task 3 — Check saved cassettes for retired or swapped models

```bash
evalcraft check-stale tests/cassettes/*.json --models "gpt-5.1,claude-sonnet-4-5"
```

Pass the models the project ships today. It exits non-zero if a cassette was
recorded against a model not in that list, or from a reasoning model with its
reasoning blocks missing (a recording that cannot be replayed faithfully). Add
`--prompts FILE` to flag prompt drift and `--max-age-days N` for age. Put it
in CI next to the tests.

## Task 4 — Budgets and tool-call contracts

- Cost: `assert_cost_under(run, max_usd=...)`
- Tokens: `assert_token_count_under(run, max_tokens=...)`
- Latency: `assert_latency_under(run, max_ms=...)`
- A tool ran / never ran: `assert_tool_called(run, name, times=None, with_args=None)`,
  `assert_no_tool_called(run, name)`
- Tool order: `assert_tool_trajectory(run, tools, mode=...)` with `strict`,
  `unordered`, `subset` or `superset`
- Argument shape: `assert_tool_args_match_schema(run, name, schema)`
- Output shape: `assert_output_json_schema(run, schema)`

The full list, and which assertions cost money, is in
[references/assertions.md](references/assertions.md).

## Common mistakes

- **Never edit, delete or re-record a cassette to make a failing test pass.**
  A failing evalcraft assertion usually means the agent changed behaviour. Fix
  the agent, or ask the user before updating the recorded baseline. Cassette
  changes should show up in the diff for a human to review.
- `replay()` does not run the agent. It reads the recording back. A green
  replay test does not prove new agent code works. Use `evalcraft mock` and
  run the real agent against the mocks, or re-record and compare with
  `evalcraft diff old.json new.json`.
- Prefer `mode="unordered"` for trajectories unless order genuinely matters.
  Models reorder independent tool calls between versions, and `strict` makes
  those harmless reorderings fail.
- The pytest flag is `--evalcraft-record=none|new|all`, not `--evalcraft`.
  The default `none` never writes a cassette. `new` records only missing ones
  and never touches existing ones; `all` overwrites everything. Only use `all`
  when the user has asked to re-record.
- In CI a missing cassette **fails** the test (locally it skips). Deleting a
  cassette is therefore not a way to get a test out of the way; if a recording
  is genuinely obsolete, remove the test that uses it too.
- `evalcraft init --framework generic` scaffolds a runnable suite without a
  prompt. Other values: `openai`, `anthropic`, `langgraph`, `crewai`.
- `assert_output_semantic`, `assert_factual_consistency`, `assert_tone`,
  `assert_custom_criteria`, the RAG assertions and `pairwise_compare` call a
  live model: they need an API key and cost money. Keep them out of the
  per-commit suite.
