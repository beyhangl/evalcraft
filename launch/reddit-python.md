**Flair:** Showcase

**Title:** I built evalcraft — the pytest for AI agents

**Body:**

**What My Project Does**

Evalcraft is a pytest plugin that records AI agent runs (LLM calls, tool use, costs, latency) into JSON "cassette" files, then replays them in tests with zero API calls. Record once against a real LLM, then run tests for free forever.

```python
# Record
from evalcraft import CaptureContext
from evalcraft.adapters.openai import OpenAIAdapter

with CaptureContext("support_agent") as ctx:
    adapter = OpenAIAdapter(ctx)
    result = my_agent.run("What's my order status?")

# Replay in tests — zero API calls
from evalcraft import replay, assert_tool_called, assert_cost_under

run = replay("cassettes/support_agent.json")
assert_tool_called(run, "lookup_order")
assert_cost_under(run, max_usd=0.01)
```

It also does regression detection (catch cost blowups, tool sequence changes), golden set management, PII sanitization, and ships with a GitHub Action for CI gates. 6 framework adapters: OpenAI, Anthropic, LangGraph, CrewAI, AutoGen, LlamaIndex.

**Target Audience**

Python developers building AI agents or LLM-powered apps who want deterministic, cost-free tests in CI. If you're currently skipping agent tests because they're expensive and flaky, this is for you.

**Comparison**

- **VCR.py / responses / respx** — record HTTP, but don't understand LLM semantics (tokens, costs, tool calls). No scorers, no regression detection.
- **DeepEval / Ragas** — evaluation frameworks that score outputs but still call real LLMs on every run. Evalcraft replays from cassettes — no API costs.
- **LangSmith / Braintrust** — SaaS tracing platforms. Evalcraft is local-first, open source, pytest-native, and runs offline.
- **Manual mocks** — fragile, no cost tracking, breaks when you change models. Evalcraft captures real behavior and replays it exactly.

**Links**

- GitHub: https://github.com/beyhangl/evalcraft
- PyPI: https://pypi.org/project/evalcraft/
- Docs: https://beyhangl.github.io/evalcraft/docs/
- Quickstart: https://beyhangl.github.io/evalcraft/docs/user-guide/quickstart/

555 tests, Python 3.9–3.13, MIT licensed. `pip install evalcraft`
