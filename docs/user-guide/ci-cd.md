# CI/CD Integration

Evalcraft ships a reusable GitHub Action that gates pull requests on agent test results. Add it to your workflow in under five minutes.

## Quick Start

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
          test-path: tests/agent_tests/
          cassette-dir: tests/cassettes/
          max-cost: '0.10'
          max-regression: '5%'
```

This will:
1. Install evalcraft into the runner
2. Run your pytest agent tests in replay mode (no real LLM calls)
3. Post a results table as a PR comment
4. Fail the workflow if any test fails or a threshold is exceeded

---

## Inputs

| Input | Default | Description |
|-------|---------|-------------|
| `test-path` | `tests/` | Path to agent test files or directory |
| `cassette-dir` | `tests/cassettes` | Where cassettes are stored/loaded |
| `record-mode` | `none` | `none` · `new` · `all` — see [Record Modes](#record-modes) |
| `max-cost` | _(none)_ | Maximum total cost in USD. Fails if exceeded. |
| `max-regression` | _(none)_ | Max % increase in any cassette metric vs. baseline. |
| `evalcraft-version` | `latest` | Pin to a specific release (e.g. `0.1.0`) |
| `python-version` | `3.11` | Python version to use |
| `extra-pytest-args` | _(none)_ | Extra flags forwarded to pytest verbatim |
| `post-comment` | `true` | Post PR comment with results table |
| `github-token` | `${{ github.token }}` | Token for posting PR comments |

## Outputs

| Output | Description |
|--------|-------------|
| `passed` | `"true"` if all tests and thresholds passed |
| `total-cost` | Total USD cost across all cassettes |
| `total-tokens` | Total token count across all cassettes |
| `total-tool-calls` | Total tool call count |
| `cassette-count` | Number of cassette files evaluated |

Use outputs in downstream steps:

```yaml
- uses: beyhangl/evalcraft@v0.1.0
  id: evalcraft
  with:
    test-path: tests/agent_tests/

- name: Notify on regression
  if: steps.evalcraft.outputs.passed == 'false'
  run: echo "Agent regressions detected — total cost ${{ steps.evalcraft.outputs.total-cost }}"
```

---

## Record Modes

| Mode | Description | Requires LLM keys |
|------|-------------|:-----------------:|
| `none` | Replay only. Skips tests whose cassette is missing. | No |
| `new` | Record cassettes that don't exist yet; replay the rest. | Yes |
| `all` | Always re-record every cassette (live LLM calls). | Yes |

The default `none` keeps CI fast and deterministic — no real API calls are made.

---

## Threshold Checks

### max-cost

Fails the action if the total cost across all cassettes exceeds the limit.

```yaml
- uses: beyhangl/evalcraft@v0.1.0
  with:
    max-cost: '0.10'   # fail if agents collectively spend > $0.10
```

### max-regression

Compares cassette metrics (tokens, cost) against the baseline versions committed in git. Fails if any metric increases by more than the specified percentage.

```yaml
- uses: beyhangl/evalcraft@v0.1.0
  with:
    max-regression: '5%'    # fail if any metric regresses > 5%
    record-mode: all        # re-record so fresh metrics are available
```

> **Note:** `max-regression` is only meaningful when `record-mode` is `new` or `all` — it compares the freshly-recorded cassettes against the baseline versions already committed to git.

---

## PR Comment

When `post-comment: true` (default) and the action runs on a pull request, evalcraft posts a formatted results table:

```
## 🧪 Evalcraft Agent Test Results — ✅ Passed

| Metric           | Value     |
|------------------|-----------|
| Cassettes        | 4         |
| Total tokens     | 2,840     |
| Total cost       | $0.0423   |
| Total tool calls | 12        |

### Per-Cassette Metrics

| Cassette           | LLM Calls | Tool Calls | Tokens | Cost    | Duration | Fingerprint |
|--------------------|:---------:|:----------:|-------:|--------:|:--------:|:-----------:|
| `math_agent`       | 1         | 0          | 312    | $0.0041 | 210ms    | `a1b2c3d4`  |
| `search_agent`     | 3         | 4          | 1,240  | $0.0180 | 1.24s    | `e5f6g7h8`  |
```

The action updates the same comment on each push (no comment spam).

---

## Pinning Versions

Always pin evalcraft to a specific version in production workflows for reproducibility:

```yaml
- uses: beyhangl/evalcraft@v0.1.0
  with:
    evalcraft-version: '0.1.0'
```

---

## Full Example

See [`.github/workflows/example-ci-gate.yml`](../../.github/workflows/example-ci-gate.yml) for a complete workflow you can copy to your project.

```yaml
name: Agent Tests (Evalcraft CI Gate)

on:
  pull_request:
    branches: [main]

concurrency:
  group: evalcraft-${{ github.ref }}
  cancel-in-progress: true

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
          test-path: tests/agent_tests/
          cassette-dir: tests/cassettes/
          max-cost: '0.10'
          max-regression: '5%'
          record-mode: none
          post-comment: 'true'
```

---

## Nightly Cassette Refresh

To keep cassettes up to date with model changes, run a nightly re-record job and open a PR if anything changed:

```yaml
# .github/workflows/cassette-refresh.yml
name: Nightly cassette refresh

on:
  schedule:
    - cron: '0 3 * * *'   # 3 AM UTC daily

jobs:
  refresh:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write

    steps:
      - uses: actions/checkout@v4

      - uses: beyhangl/evalcraft@v0.1.0
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        with:
          test-path: tests/agent_tests/
          cassette-dir: tests/cassettes/
          record-mode: all          # re-record every cassette
          max-regression: '10%'    # allow up to 10% model drift
          post-comment: 'false'

      - uses: peter-evans/create-pull-request@v6
        with:
          commit-message: 'chore: refresh evalcraft cassettes'
          title: '🤖 Cassette refresh'
          branch: cassette-refresh/nightly
          labels: cassettes, automated
```

---

## Required Permissions

The action only needs elevated permissions for PR comment posting:

```yaml
permissions:
  contents: read        # read cassette files from the repo
  pull-requests: write  # post / update results comment
```

If you set `post-comment: 'false'` you can drop `pull-requests: write`.

---

## Troubleshooting

**Tests are skipped in CI**

If tests are skipped with "Cassette not found", your cassette files aren't committed to the repo. Either commit the cassettes or switch to `record-mode: new` (requires LLM API keys as secrets).

**PR comment not posting**

Ensure `permissions: pull-requests: write` is set on the job and that the workflow trigger is `pull_request` (not `push`).

**`max-regression` not triggering**

Regression checks compare freshly-recorded cassettes to the git-committed baseline. Make sure `record-mode` is `new` or `all` so new cassettes are written before the comparison runs.

**Pinning evalcraft version in eval step**

If you use `evalcraft-version: latest` but need reproducible results, pin to a release: `evalcraft-version: '0.1.0'`.
