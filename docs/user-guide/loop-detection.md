# Loop detection ($0)

A stuck agent doesn't crash — it *loops*, quietly burning tokens and latency
calling the same tool with the same arguments over and over, or restating the
same conclusion every step. Evalcraft detects both, **offline, deterministically,
and `$0`**: it reads only the recorded spans and never calls a model.

```python
from evalcraft import replay, assert_no_loops

run = replay("tests/cassettes/agent.json")
assert assert_no_loops(run).passed
```

## Two signals

`assert_no_loops` flags a run when either appears:

- **Repeated tool calls** — the same `(tool_name, tool_args)` recorded more than
  `max_tool_repeats` times. An agent that calls `search({"q": "x"})` five times
  in a run is almost certainly oscillating.
- **Repeated step outputs** — the same LLM/agent-step output recorded more than
  `max_step_repeats` times.

`max_*_repeats` is the maximum number of times a call/output may appear before
it is flagged — with the default of `2`, a **3rd identical occurrence** trips it.

```python
# tighten or loosen the thresholds independently
assert_no_loops(run, max_tool_repeats=3, max_step_repeats=1)
```

## Catching near-duplicates

A real loop rarely repeats *byte-for-byte* — the agent rewords the same idea.
Set `similarity` below `1.0` to treat step outputs that overlap by at least that
fraction of tokens (Jaccard) as the "same":

```python
# "The answer is 42 today" / "...42 now" / "...42 here" -> one loop
assert assert_no_loops(run, similarity=0.6).passed is False
```

`similarity=1.0` (the default) means exact match only, after whitespace
normalisation.

## Just the tool calls

When you only care about tool oscillation:

```python
from evalcraft import assert_no_repeated_tool_calls

assert assert_no_repeated_tool_calls(run, max_repeats=3).passed
```

Tool arguments are compared order-insensitively, so
`{"a": 1, "b": 2}` and `{"b": 2, "a": 1}` count as the same call.

## Inspecting the findings

`detect_loops` returns a structured `LoopReport` if you want the details rather
than a pass/fail:

```python
from evalcraft import detect_loops

report = detect_loops(run, max_tool_repeats=2)
if report.has_loops:
    for f in report.findings:
        print(f.kind, f.signature, f"×{f.count} (max {f.max_allowed})")
# repeated_tool_call  search({"q": "x"})  ×5 (max 2)
```

## It's automatic in `generate-tests`

When you scaffold tests from a known-good cassette that has tool calls and no
loops of its own, `evalcraft generate-tests` adds an `assert_no_loops` test —
locking that clean run against future repetition regressions. (If the baseline
*itself* loops, the guard is skipped so the generated test never fails on its
own cassette.)

## Why it belongs in the `$0` path

Loop pathology is about the agent's **control flow**, not the quality of its
prose — so it needs no judge model. It's deterministic, runs in milliseconds on
the committed cassette, and turns "is my agent silently wasting tokens in a
loop?" into a regression gate that runs on every commit for free.
