# Twitter/X Thread — Evalcraft Launch

---

## Tweet 1 (265 chars)

Agent testing is broken.

Every test run:
- Calls the LLM API
- Costs real money
- Takes minutes
- Returns different output each time

We built evalcraft to fix this — cassette-based capture and replay for AI agents. pytest-native. $0 per run.

Here's how it works:

---

## Tweet 2 (248 chars)

Record your agent once with real API calls. Every LLM request, tool call, and response gets saved to a JSON cassette.

Then replay from cassette. Zero API calls. Zero cost. Deterministic.

Same concept as VCR for HTTP testing, applied to AI agents.

---

## Tweet 3 (204 chars)

Here's what a test looks like:

run = replay("cassettes/support_agent.json")
assert_tool_called(run, "lookup_order")
assert_cost_under(run, max_usd=0.01)

Capture once. Replay forever. Assert on behavior.

---

## Tweet 4 (280 chars)

Before evalcraft:
- Minutes-long test suite
- Real API costs per run
- Non-deterministic, breaks CI

After evalcraft:
- 200ms test suite
- $0.00 per run
- Deterministic, runs in CI on every commit

6 framework adapters: OpenAI, Anthropic, LangGraph, CrewAI, AutoGen, LlamaIndex.

---

## Tweet 5 (226 chars — URL counted as 23 per Twitter/X)

Get started in 2 minutes:

pip install evalcraft
evalcraft init
pytest tests/ -v

555 tests. MIT licensed. Fully open source.

GitHub: https://github.com/beyhangl/evalcraft

Looking for early users testing agents in production — DMs open.
