# CrewAI Adapter

The `CrewAIAdapter` instruments a CrewAI `Crew` to record all agent actions, tool calls, task completions, and delegation events as evalcraft spans.

## Install

```bash
pip install "evalcraft[crewai]"
```

Requires `crewai>=0.28`.

## Quick start

```python
from evalcraft.adapters import CrewAIAdapter
from evalcraft import CaptureContext

# crew is a crewai.Crew instance
with CaptureContext(name="crew_run", save_path="tests/cassettes/crew.json") as ctx:
    with CrewAIAdapter(crew):
        result = crew.kickoff(inputs={"topic": "AI safety"})
    ctx.record_output(str(result))

cassette = ctx.cassette
print(cassette.get_tool_sequence())  # tools called during the run
print(cassette.tool_call_count)
```

## Async usage

```python
import asyncio
from evalcraft.adapters import CrewAIAdapter
from evalcraft import CaptureContext

async def main():
    async with CaptureContext(name="crew_async") as ctx:
        async with CrewAIAdapter(crew):
            result = await crew.kickoff_async(inputs={"topic": "AI safety"})
        ctx.record_output(str(result))

asyncio.run(main())
```

## How it works

`CrewAIAdapter` instruments a crew instance by:

1. **Patching `kickoff()` and `kickoff_async()`** — records overall execution time and final output as an `AGENT_STEP` span (`crew:kickoff`)
2. **Injecting `step_callback`** — captures each agent action (tool calls, delegation steps, finish events)
3. **Injecting `task_callback`** — captures task completions including the responsible agent

Existing `step_callback` and `task_callback` values on the crew are preserved and called after the adapter's own recording.

## Span types produced

| Event | SpanKind | Name |
|-------|----------|------|
| Tool use | `TOOL_CALL` | `tool:<tool_name>` |
| Agent finish | `AGENT_STEP` | `agent:finish` |
| Task completed | `AGENT_STEP` | `task:<description[:60]>` |
| Kickoff success | `AGENT_STEP` | `crew:kickoff` |
| Kickoff error | `AGENT_STEP` | `crew:kickoff:error` |

## Full example

```python
from crewai import Agent, Task, Crew
from crewai_tools import SerperDevTool

from evalcraft.adapters import CrewAIAdapter
from evalcraft import CaptureContext, assert_tool_called, assert_cost_under

# Define agents
researcher = Agent(
    role="Research Analyst",
    goal="Find the latest information on AI trends",
    backstory="You are an expert researcher...",
    tools=[SerperDevTool()],
    verbose=True,
)

# Define tasks
research_task = Task(
    description="Research the latest AI safety developments in 2026",
    expected_output="A summary of key AI safety developments",
    agent=researcher,
)

# Create crew
crew = Crew(agents=[researcher], tasks=[research_task], verbose=True)

# Capture the run
with CaptureContext(
    name="ai_safety_research",
    agent_name="researcher_crew",
    save_path="tests/cassettes/crew_research.json",
) as ctx:
    with CrewAIAdapter(crew):
        result = crew.kickoff(inputs={"topic": "AI safety 2026"})
    ctx.record_output(str(result))

cassette = ctx.cassette
print(f"Tools used: {cassette.get_tool_sequence()}")
print(f"Tasks completed: {cassette.tool_call_count}")
```

## Capturing LLM usage

To also capture LLM token usage, combine `CrewAIAdapter` with `OpenAIAdapter` (or `AnthropicAdapter`):

```python
from evalcraft.adapters import CrewAIAdapter, OpenAIAdapter
from evalcraft import CaptureContext

with CaptureContext(name="crew_with_llm") as ctx:
    with OpenAIAdapter():        # captures GPT-4 token usage and cost
        with CrewAIAdapter(crew):
            result = crew.kickoff(inputs={"topic": "test"})
    ctx.record_output(str(result))

cassette = ctx.cassette
print(f"Total tokens: {cassette.total_tokens}")
print(f"Estimated cost: ${cassette.total_cost_usd:.4f}")
```

## Multi-agent crews

For multi-agent crews, delegation is surfaced as tool calls with the name `"Delegate work to coworker"`. The `task_callback` metadata includes the responsible agent's role:

```python
# After kickoff, check which agents did what
for span in cassette.spans:
    if span.kind.value == "agent_step" and span.name.startswith("task:"):
        agent_role = span.metadata.get("agent", "unknown")
        print(f"Task completed by {agent_role}: {span.output[:100]}")
```

## Testing with fixtures

```python
import pytest
from evalcraft.adapters import CrewAIAdapter
from evalcraft import assert_tool_called

@pytest.mark.evalcraft_cassette("tests/cassettes/crew_research.json")
def test_crew_used_search(cassette):
    # Assumes crew called a search tool
    result = assert_tool_called(cassette, "Search the internet")
    assert result.passed, result.message

@pytest.mark.evalcraft_cassette("tests/cassettes/crew_research.json")
def test_crew_produced_output(cassette):
    assert len(cassette.output_text) > 100
```

## Limitations

- **Not reentrant** — do not nest two `CrewAIAdapter` contexts on the same crew.
- Patches the instance, not the class — multiple crews can be wrapped independently.
- For LLM token usage, combine with `OpenAIAdapter` or `AnthropicAdapter`.

## Import paths

```python
# Preferred
from evalcraft.adapters import CrewAIAdapter

# Direct
from evalcraft.adapters.crewai_adapter import CrewAIAdapter
```
