Show HN: Evalcraft – open-source cassette-based testing for AI agents (pytest-native, $0 per run)

Testing AI agents is painful. Every test run calls the LLM API, costs real money, takes minutes, and gives different results each time. CI? Forget about it.

Evalcraft fixes this with cassette-based capture and replay — think VCR for HTTP, but for LLM calls and tool use.

How it works:

1. Run your agent once with real API calls. Evalcraft records every LLM request, tool call, and response into a JSON cassette file.

2. In tests, replay from the cassette. Zero API calls, zero cost, deterministic output.

3. Assert on what matters: tool call sequences, output content, cost budgets, token counts.

  run = replay("cassettes/support_agent.json")
  assert_tool_called(run, "lookup_order", with_args={"order_id": "ORD-1042"})
  assert_tool_order(run, ["lookup_order", "search_knowledge_base"])
  assert_cost_under(run, max_usd=0.01)

It's pytest-native — fixtures, markers, CLI flags. Works with OpenAI, Anthropic, LangGraph, CrewAI, AutoGen, and LlamaIndex out of the box. Adapters auto-instrument your agent with zero code changes.

Also ships with golden-set management, regression detection, PII sanitization, and 16 CLI commands for inspecting/diffing cassettes.

555 tests, MIT licensed, `pip install evalcraft`.

Repo: https://github.com/beyhangl/evalcraft
PyPI: https://pypi.org/project/evalcraft/
Docs: https://beyhangl.github.io/evalcraft/docs/

Would love feedback from anyone testing agents in CI.
