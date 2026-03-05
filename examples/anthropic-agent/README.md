# Example: Anthropic Code Review Agent

A multi-turn code review bot powered by Claude claude-3-5-haiku-20241022. The agent reviews pull
request diffs through a structured tool-use loop: fetch diff, run lint checks, assess
test coverage, then synthesize a structured review.

This example demonstrates evalcraft's support for **multi-turn conversations**
and **security-sensitive assertions** (verifying the agent flags critical issues).

## Scenario

**Code review bot** analyzes PRs in a Python backend repository:

- PR #101: JWT authentication middleware (has a hardcoded secret — agent must flag it)
- PR #102: Database connection pool refactor (clean code — agent should approve)

## Project layout

```
anthropic-agent/
├── agent.py                         # Agent logic (no evalcraft imports)
├── record_cassettes.py              # Run once to capture live Claude sessions
├── requirements.txt
├── tests/
│   ├── cassettes/
│   │   ├── auth_middleware_review.json    # Pre-recorded (2 LLM turns, 3 tool calls)
│   │   └── db_pool_refactor_review.json
│   └── test_code_review_agent.py    # Replay-based tests + mock unit tests
└── golden/
```

## Step-by-step setup

### 1. Install

```bash
cd examples/anthropic-agent
pip install -r requirements.txt
```

### 2. Run tests (no API key needed)

```bash
pytest tests/ -v
```

Expected output:
```
tests/test_code_review_agent.py::TestToolSequence::test_auth_pr_fetches_diff_first    PASSED
tests/test_code_review_agent.py::TestToolSequence::test_auth_pr_runs_lint_check       PASSED
tests/test_code_review_agent.py::TestSecurityReview::test_flags_hardcoded_secret      PASSED
tests/test_code_review_agent.py::TestSecurityReview::test_recommends_change           PASSED
...
22 passed in 0.28s
```

### 3. Record fresh cassettes (requires Anthropic API key)

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python record_cassettes.py
```

### 4. Understand the multi-turn test

The mock-based test in `test_code_review_agent.py::test_multi_turn_with_mocks`
demonstrates how to test multi-turn agent behavior without any API calls:

```python
llm.add_sequential_responses(
    "*",
    [
        "I'll fetch the PR diff and run checks.",       # turn 1
        "## Code Review\n**APPROVE** — Great fix.",     # turn 2
    ],
)
```

`MockLLM.add_sequential_responses` returns responses in order, simulating the
agent's tool-planning turn followed by its synthesis turn.

## Key concepts demonstrated

| Concept | Where |
|---------|-------|
| `AnthropicAdapter` auto-capture | `record_cassettes.py` |
| Multi-turn cassette replay | `test_code_review_agent.py` |
| `assert_tool_called(before=...)` | `TestToolSequence` |
| `assert_tool_order(strict=False)` | `TestToolSequence` |
| `assert_output_matches` (regex) | `TestSecurityReview` |
| Security assertion patterns | `TestSecurityReview` |
| `MockLLM.add_sequential_responses` | `test_multi_turn_with_mocks` |
| Parametrized budget tests | `TestBudgets` |

## What to try

Test what happens when the agent skips the lint check by overriding a cassette:

```python
from evalcraft.replay.engine import ReplayEngine
from evalcraft import assert_tool_called

engine = ReplayEngine("tests/cassettes/auth_middleware_review.json")
run = engine.run()

# This should pass — lint check happened
result = assert_tool_called(run, "run_lint_check")
assert result.passed
```
