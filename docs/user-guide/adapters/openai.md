# OpenAI Adapter

The `OpenAIAdapter` monkey-patches the OpenAI SDK so every call to `client.chat.completions.create()` — sync or async — is automatically recorded into the active `CaptureContext`.

## Install

```bash
pip install "evalcraft[openai]"
```

## Quick start

```python
from evalcraft.adapters import OpenAIAdapter
from evalcraft import CaptureContext
import openai

client = openai.OpenAI()

with CaptureContext(name="openai_test", save_path="tests/cassettes/openai.json") as ctx:
    with OpenAIAdapter():
        ctx.record_input("What's the weather in Paris?")
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "What's the weather in Paris?"}],
        )
        ctx.record_output(response.choices[0].message.content)

cassette = ctx.cassette
print(cassette.total_tokens)    # actual token count from API
print(cassette.total_cost_usd)  # estimated cost
```

## How it works

`OpenAIAdapter` patches the `Completions` and `AsyncCompletions` classes at the class level, so **all** client instances (including custom `base_url` clients and Azure OpenAI) are captured.

On exit, the original methods are restored — even if an exception is raised inside the `with` block.

## Async usage

```python
import asyncio
import openai
from evalcraft.adapters import OpenAIAdapter
from evalcraft import CaptureContext

client = openai.AsyncOpenAI()

async def main():
    async with CaptureContext(name="async_openai") as ctx:
        async with OpenAIAdapter():
            ctx.record_input("Hello")
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "Hello"}],
            )
            ctx.record_output(response.choices[0].message.content)

asyncio.run(main())
```

## Tool calls

Tool call information is included in the recorded span when the model returns tool calls:

```python
with CaptureContext(name="tool_call_test") as ctx:
    with OpenAIAdapter():
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "What's the weather in Paris?"}],
            tools=[{
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "parameters": {"type": "object", "properties": {"city": {"type": "string"}}}
                }
            }],
        )

# The span output includes: "[tool_call:get_weather({'city': 'Paris'})]"
```

## Cost estimation

The adapter estimates USD cost using a built-in pricing table for common OpenAI models:

| Model | Input (per 1M tokens) | Output (per 1M tokens) |
|-------|-----------------------|------------------------|
| gpt-4o | $2.50 | $10.00 |
| gpt-4o-mini | $0.15 | $0.60 |
| gpt-4-turbo | $10.00 | $30.00 |
| gpt-4 | $30.00 | $60.00 |
| gpt-3.5-turbo | $0.50 | $1.50 |
| o1 | $15.00 | $60.00 |
| o3-mini | $1.10 | $4.40 |

For models not in the table, `cost_usd` is `None`.

## Limitations

- **Not reentrant** — do not nest two `OpenAIAdapter` contexts.
- Patches the class, not a specific instance — all client instances are affected during the context.
- Streaming responses (`stream=True`) are not currently intercepted at the span level.

## With pytest

```python
import pytest
import openai
from evalcraft.adapters import OpenAIAdapter
from evalcraft import assert_tool_called, assert_cost_under

@pytest.mark.evalcraft_capture(name="openai_weather")
def test_openai_weather_agent(capture_context):
    client = openai.OpenAI()

    with OpenAIAdapter():
        capture_context.record_input("Weather in Paris?")
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Weather in Paris?"}],
        )
        capture_context.record_output(response.choices[0].message.content)

    cassette = capture_context.cassette
    assert cassette.llm_call_count == 1
    result = assert_cost_under(cassette, max_usd=0.01)
    assert result.passed, result.message
```

## Import paths

```python
# Preferred
from evalcraft.adapters import OpenAIAdapter

# Direct
from evalcraft.adapters.openai_adapter import OpenAIAdapter
```
