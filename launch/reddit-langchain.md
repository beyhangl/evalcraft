**Title:** Built a testing framework for LangGraph agents — cassette-based replay, deterministic CI, $0 per run

**Body:**

If you're testing LangGraph agents, you know the pain: every test run hits the LLM API, costs money, returns different results, and makes CI flaky.

Evalcraft solves this with cassette-based capture and replay. The LangGraph adapter patches your compiled graph to record every node execution, LLM call, and tool invocation into a JSON cassette:

```python
from evalcraft import CaptureContext
from evalcraft.adapters import LangGraphAdapter

with CaptureContext(name="my_graph_test", save_path="cassette.json") as ctx:
    with LangGraphAdapter(graph):
        result = graph.invoke({"input": "Track order ORD-1042"})
```

Then replay in tests — zero API calls, deterministic, runs in 200ms:

```python
from evalcraft import replay, assert_tool_called, assert_tool_order, assert_cost_under

run = replay("cassette.json")
assert_tool_called(run, "lookup_order")
assert_tool_order(run, ["lookup_order", "search_knowledge_base"])
assert_cost_under(run, max_usd=0.01)
```

Also works with OpenAI, Anthropic, CrewAI, AutoGen, and LlamaIndex. pytest-native with fixtures and markers. Golden-set management for catching regressions.

`pip install evalcraft` | [GitHub](https://github.com/beyhangl/evalcraft) | [PyPI](https://pypi.org/project/evalcraft/) | [Docs](https://beyhangl.github.io/evalcraft/docs/)
