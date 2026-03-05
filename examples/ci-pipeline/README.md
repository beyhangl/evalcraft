# Example: CI Pipeline Integration

This example shows how to use evalcraft as a **CI quality gate** — blocking
deploys when agent behavior regresses. Two complementary approaches are
provided: a pytest-native suite and a standalone gate script.

## The two CI patterns

### Pattern A: pytest (recommended)
Run evalcraft tests just like any other pytest suite. Tests replay cassettes
in milliseconds without API calls:

```yaml
# .github/workflows/eval.yml
- name: Run agent eval tests
  run: pytest tests/ -v
  # Zero API calls, zero cost, ~30 seconds
```

### Pattern B: Standalone gate script
Use `evalcraft_gate.py` when you need a custom check suite outside pytest —
useful for scripted pipelines (Makefile, shell scripts, Jenkins):

```bash
python evalcraft_gate.py                  # All checks
python evalcraft_gate.py --only cost      # Cost checks only
python evalcraft_gate.py --json-output ci-report.json
```

Exit code 0 = all checks pass. Exit code 1 = one or more checks failed.

## Project layout

```
ci-pipeline/
├── evalcraft_gate.py              # Standalone CI gate script
├── requirements.txt
├── tests/
│   └── test_ci_gate.py            # Tests for the gate script itself
└── .github/
    └── workflows/
        └── eval.yml               # Complete GitHub Actions workflow
```

## GitHub Actions workflow explained

The `eval.yml` workflow has 4 jobs:

### Job 1: `replay-tests` (runs on every push)
- Replays pre-recorded cassettes — **no API key, ~30 seconds, $0**
- Blocks merge if tool sequences, cost, or outputs regress
- Uses `EVALCRAFT_BLOCK_NETWORK=true` to prevent accidental live calls

### Job 2: `golden-regression` (runs on PRs to main)
- Compares cassettes against the saved golden baseline
- Catches subtle regressions (token count creep, prompt drift)
- Only runs if a golden set exists

### Job 3: `refresh-cassettes` (nightly or manual)
- Calls real APIs to refresh cassettes when they go stale
- Runs in a protected environment (requires secret approval)
- Auto-commits updated cassettes

### Job 4: `cassette-summary` (PRs only)
- Posts a cassette summary table as a GitHub step summary
- Informational — doesn't fail the build

## Quick start

### 1. Copy the workflow to your repo

```bash
cp -r .github/workflows/eval.yml your-repo/.github/workflows/
```

### 2. Customize the check suite

Edit `evalcraft_gate.py` and add your cassette paths and check functions:

```python
CHECKS = [
    # (check_function, kwargs, cassette_path, check_name)
    (check_tool_called, {"tool_name": "my_tool"}, "tests/cassettes/my_agent.json", "my_agent:calls_tool"),
    (check_cost, {"max_usd": 0.05}, "tests/cassettes/my_agent.json", "my_agent:cost_budget"),
    (check_output_keyword, {"keyword": "success"}, "tests/cassettes/my_agent.json", "my_agent:output_quality"),
]
```

### 3. Add to your CI

```yaml
# Simple integration — add to any existing workflow
- name: Agent quality gate
  run: |
    pip install evalcraft
    python evalcraft_gate.py --json-output eval-report.json
  # exit code 1 if any check fails → CI fails
```

### 4. Run tests locally

```bash
cd examples/ci-pipeline
pip install -r requirements.txt
pytest tests/ -v
```

## Cassette freshness strategy

| Trigger | What happens |
|---------|-------------|
| Every push | Replay-based tests run (free, fast) |
| PR to main | Golden-set regression check |
| Nightly | Live re-capture refreshes cassettes |
| After prompt change | Manually trigger `refresh-cassettes` job |

## Setting up secrets

For `refresh-cassettes` (nightly live re-capture), add these secrets to your
GitHub repository (Settings → Secrets → Actions):

```
OPENAI_API_KEY    = sk-...
ANTHROPIC_API_KEY = sk-ant-...
```

And create a GitHub Environment named `production-evals` with required
reviewers if you want human approval before live API calls.

## The cost story

| CI run type | API calls | Cost | Time |
|-------------|-----------|------|------|
| Replay tests (every push) | 0 | $0.00 | ~30s |
| Golden regression (PRs) | 0 | $0.00 | ~15s |
| Full live re-capture (nightly) | ~30 | ~$0.05 | ~2min |

Compared to running live evals on every push (30 tests × $0.01 avg = $0.30
per push, potentially $100+/month), evalcraft reduces eval costs to under
$2/month.
