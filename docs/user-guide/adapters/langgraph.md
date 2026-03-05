# LangGraph Adapter

The `LangGraphAdapter` instruments a compiled LangGraph graph to record all LLM calls, tool calls, and node executions as evalcraft spans.

## Install

```bash
pip install "evalcraft[langchain]"
# or if you already have langgraph:
pip install evalcraft langgraph
```

`langchain-core>=0.2` is required. LangGraph depends on it automatically.

## Quick start

```python
from evalcraft.adapters import LangGraphAdapter
from evalcraft import CaptureContext

# graph is a compiled LangGraph StateGraph / CompiledGraph
with CaptureContext(name="langgraph_run", save_path="tests/cassettes/lg.json") as ctx:
    with LangGraphAdapter(graph):
        ctx.record_input("What is 2+2?")
        result = graph.invoke({"messages": [HumanMessage("What is 2+2?")]})
        ctx.record_output(result["messages"][-1].content)

cassette = ctx.cassette
print(cassette.get_tool_sequence())  # ["web_search", ...] if tools were called
print(cassette.total_tokens)
```

## How it works

`LangGraphAdapter` patches `invoke`, `ainvoke`, `stream`, and `astream` on the graph **instance** (not the class). For each call, it injects an evalcraft LangChain callback handler that records:

- **LLM calls** — every `on_llm_end` event becomes an `LLM_RESPONSE` span with token usage and model name
- **Tool calls** — every `on_tool_end` event becomes a `TOOL_CALL` span with args and result
- **Node executions** — every `on_chain_end` event becomes an `AGENT_STEP` span (internal LangChain runnables are filtered out to reduce noise)

## Async usage

```python
import asyncio
from evalcraft.adapters import LangGraphAdapter
from evalcraft import CaptureContext

async def main():
    async with CaptureContext(name="async_lg") as ctx:
        async with LangGraphAdapter(graph):
            ctx.record_input("Plan a trip to Tokyo")
            result = await graph.ainvoke({"messages": [HumanMessage("Plan a trip to Tokyo")]})
            ctx.record_output(result["messages"][-1].content)

asyncio.run(main())
```

## Streaming

```python
from evalcraft.adapters import LangGraphAdapter
from evalcraft import CaptureContext

with CaptureContext(name="streaming") as ctx:
    with LangGraphAdapter(graph):
        ctx.record_input("Write a poem")
        for chunk in graph.stream({"messages": [HumanMessage("Write a poem")]}):
            pass  # spans are recorded via callbacks, not per-chunk
        # record_output requires extracting from last chunk
```

!!! note
    Individual streaming chunks are not intercepted. LLM and tool events are still recorded via the LangChain callback system.

## Full example with a ReAct agent

```python
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage

from evalcraft.adapters import LangGraphAdapter, OpenAIAdapter
from evalcraft import CaptureContext, assert_tool_called

@tool
def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    return f"18°C, cloudy"

llm = ChatOpenAI(model="gpt-4o-mini")
graph = create_react_agent(llm, tools=[get_weather])

with CaptureContext(name="react_agent", save_path="tests/cassettes/react.json") as ctx:
    with OpenAIAdapter():       # capture LLM token usage
        with LangGraphAdapter(graph):
            ctx.record_input("What's the weather in Paris?")
            result = graph.invoke({"messages": [HumanMessage("What's the weather in Paris?")]})
            ctx.record_output(result["messages"][-1].content)

cassette = ctx.cassette
print(cassette.get_tool_sequence())   # ["get_weather"]
print(cassette.total_tokens)

result = assert_tool_called(cassette, "get_weather")
assert result.passed
```

!!! tip
    Combine `LangGraphAdapter` with `OpenAIAdapter` (or `AnthropicAdapter`) to capture both graph-level events and LLM token usage/cost.

## Span types produced

| Event | SpanKind | Name |
|-------|----------|------|
| LLM call | `LLM_RESPONSE` | `llm:<model_name>` |
| Tool call | `TOOL_CALL` | `tool:<tool_name>` |
| Graph node | `AGENT_STEP` | `node:<node_name>` |
| Error in LLM | `LLM_RESPONSE` | `llm:error` |
| Error in tool | `TOOL_CALL` | `tool:<name>` (with error) |
| Error in chain | `AGENT_STEP` | `node:<name>:error` |

## Filtered chain names

Internal LangChain/LangGraph runnables that produce noise are automatically filtered:

- `RunnableLambda`, `RunnableSequence`, `RunnableParallel`
- `ChannelWrite`, `ChannelRead`
- `StateGraph`, `CompiledStateGraph`, `CompiledGraph`
- `Branch`, `PregelNode`

## Limitations

- **Not reentrant** — do not nest two `LangGraphAdapter` contexts on the same graph.
- Patches the instance, not the class — multiple graphs can be wrapped independently.
- Streaming events are only recorded via callbacks, not per-yielded chunk.

## Import paths

```python
# Preferred
from evalcraft.adapters import LangGraphAdapter

# Direct
from evalcraft.adapters.langgraph_adapter import LangGraphAdapter
```
