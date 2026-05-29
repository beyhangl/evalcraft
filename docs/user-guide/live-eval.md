# Live Eval — catching drift

[Replay](replay.md) tests a *recorded* run: it never re-executes the live model,
so it **cannot** catch the regressions that come from **model / prompt /
retrieval drift** (a provider updates a model, you edit a prompt, your retrieval
corpus changes). Live-eval is the complementary layer that does.

| | Replay (per-commit) | Live-eval (nightly / gated) |
|---|---|---|
| Runs the real model? | No — replays a cassette | **Yes** |
| Cost / determinism | $0, deterministic, offline | Paid, non-deterministic, online |
| Catches glue / logic regressions | ✅ | ✅ |
| Catches model / prompt / retrieval drift | ❌ | ✅ |
| Where it runs | every push | nightly or release gate |

Use **both**: replay for fast per-commit checks of your agent's deterministic
glue, live-eval to track real quality over time.

## How it works

You define a set of golden **inputs** (not frozen outputs), supply a `runner`
that executes your real agent, and attach scorers. Live-eval runs each input,
scores the live output, and aggregates per-case scores you can compare against a
saved baseline.

```python
from evalcraft.eval.live import LiveEvalCase, LiveEvalResult, run_live_eval, compare_to_baseline
from evalcraft import assert_output_contains

cases = [
    LiveEvalCase(
        name="paris_weather",
        input="What's the weather in Paris?",
        scorers=[lambda c: assert_output_contains(c, "Paris")],
    ),
]

def runner(case):
    # Run your REAL agent. Return a str, or a Cassette / AgentRun for trace scoring.
    return my_agent.run(case.input)

result = run_live_eval(cases, runner)        # live, paid, non-deterministic
print(result.pass_rate, result.mean_score)
result.save("live-baseline.json")            # save the first good run as a baseline
```

## Gating CI against a baseline

Re-run live-eval (e.g. nightly), then fail the build if any case regresses:

```python
current = run_live_eval(cases, runner)
comparison = compare_to_baseline(
    current,
    LiveEvalResult.load("live-baseline.json"),
    max_score_drop=0.1,
)
assert comparison.passed, comparison.summary()
```

Or save the current result and gate from the CLI:

```bash
evalcraft live-eval current.json --baseline live-baseline.json --max-drop 0.1
# exits non-zero if any case's score dropped by more than 0.1
```

A case missing from the baseline is reported as **new** (never a regression); a
case missing from the current run is reported as **removed**.

!!! warning
    Live-eval makes real model calls. Keep it out of the `$0` per-commit path —
    run it on a schedule or as a release gate.
