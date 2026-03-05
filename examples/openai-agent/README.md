# Example: OpenAI Support Agent

A realistic customer support agent powered by GPT-4o-mini. The agent handles
customer queries by searching a knowledge base and looking up order details
before drafting a reply.

This example demonstrates the full evalcraft workflow:
**Record once → Commit cassettes → Replay for free in CI forever.**

## Scenario

**ShopEasy** customer support agent answers questions about:
- Order tracking (calls `lookup_order` + `search_knowledge_base`)
- Returns and refunds (calls both tools, explains 30-day policy)
- Damaged/missing items (calls both tools, offers replacement or refund)

## Project layout

```
openai-agent/
├── agent.py                    # Agent logic (no evalcraft imports)
├── record_cassettes.py         # Run once to capture live agent runs
├── build_golden.py             # Promote cassettes to a golden baseline
├── requirements.txt
├── tests/
│   ├── cassettes/              # Pre-recorded cassettes (committed to git)
│   │   ├── order_tracking.json
│   │   ├── return_request.json
│   │   └── damaged_item.json
│   ├── test_support_agent.py   # Replay-based regression tests
│   └── test_golden.py          # Golden-set comparison tests
└── golden/
    └── support_agent.golden.json
```

## Step-by-step setup

### 1. Install dependencies

```bash
cd examples/openai-agent
pip install -r requirements.txt
```

### 2. Run tests (no API key needed)

The cassettes are already committed. Tests replay them deterministically:

```bash
pytest tests/test_support_agent.py -v
```

Expected output:
```
tests/test_support_agent.py::TestOrderTracking::test_lookup_order_called    PASSED
tests/test_support_agent.py::TestOrderTracking::test_lookup_order_correct_id PASSED
tests/test_support_agent.py::TestOrderTracking::test_knowledge_base_consulted PASSED
...
15 passed in 0.31s
```

Zero API calls. Zero cost.

### 3. Record fresh cassettes (requires API key)

When you change the agent, re-record the cassettes:

```bash
export OPENAI_API_KEY=sk-...
python record_cassettes.py
```

This calls the live OpenAI API once per scenario and saves the responses
to `tests/cassettes/`. Commit the updated cassettes to git.

### 4. Build a golden set (regression baseline)

```bash
python build_golden.py
```

Creates `golden/support_agent.golden.json`. Future runs are compared against
this baseline — tests fail if tool sequences change or cost/tokens spike.

```bash
pytest tests/test_golden.py -v
```

### 5. Update the golden set after intentional changes

After a deliberate agent improvement, bump the golden version:

```python
from evalcraft import GoldenSet
gs = GoldenSet.load("golden/support_agent.golden.json")
gs.bump_version()
gs.add_cassette(new_cassette)
gs.save("golden/support_agent.golden.json")
```

## Key concepts demonstrated

| Concept | Where |
|---------|-------|
| `CaptureContext` | `record_cassettes.py` |
| `OpenAIAdapter` auto-capture | `record_cassettes.py` |
| `replay()` | All test files |
| `assert_tool_called` with `with_args` | `test_support_agent.py` |
| `assert_tool_order` | `test_support_agent.py` |
| `assert_cost_under` | `test_support_agent.py` |
| `Evaluator` composite assertions | `test_support_agent.py` |
| `MockLLM` + `MockTool` unit tests | `test_support_agent.py` |
| `GoldenSet` regression | `test_golden.py` |

## What to try

- Break the agent (remove a tool call) and watch tests fail
- Override a tool result in a test using `ReplayEngine`:

```python
from evalcraft.replay.engine import ReplayEngine

engine = ReplayEngine("tests/cassettes/order_tracking.json")
engine.override_tool_result("lookup_order", {"error": "order not found"})
run = engine.run()
# Now test how the agent handles an unknown order
```
