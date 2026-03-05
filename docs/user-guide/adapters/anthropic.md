# Anthropic Adapter

The `AnthropicAdapter` monkey-patches the Anthropic SDK so every call to `client.messages.create()` — sync or async — is automatically recorded into the active `CaptureContext`.

## Install

```bash
pip install "evalcraft[anthropic]"
```

## Quick start

```python
from evalcraft.adapters import AnthropicAdapter
from evalcraft import CaptureContext
import anthropic

client = anthropic.Anthropic()

with CaptureContext(name="anthropic_test", save_path="tests/cassettes/anthropic.json") as ctx:
    with AnthropicAdapter():
        ctx.record_input("What's the weather in Paris?")
        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            messages=[{"role": "user", "content": "What's the weather in Paris?"}],
        )
        ctx.record_output(response.content[0].text)

cassette = ctx.cassette
print(cassette.total_tokens)    # actual token count from API
print(cassette.total_cost_usd)  # estimated cost
```

## How it works

`AnthropicAdapter` patches `Messages` and `AsyncMessages` at the class level, so all client instances are captured. On exit, the original methods are restored.

## Async usage

```python
import asyncio
import anthropic
from evalcraft.adapters import AnthropicAdapter
from evalcraft import CaptureContext

client = anthropic.AsyncAnthropic()

async def main():
    async with CaptureContext(name="async_anthropic") as ctx:
        async with AnthropicAdapter():
            ctx.record_input("Summarize the French Revolution")
            response = await client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=512,
                messages=[{"role": "user", "content": "Summarize the French Revolution"}],
            )
            ctx.record_output(response.content[0].text)

asyncio.run(main())
```

## Tool use

When Claude returns tool use blocks, they are included in the recorded span output:

```python
with CaptureContext(name="tool_use_test") as ctx:
    with AnthropicAdapter():
        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            tools=[{
                "name": "get_weather",
                "description": "Get weather for a city",
                "input_schema": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}}
                }
            }],
            messages=[{"role": "user", "content": "What's the weather in Paris?"}],
        )

# The span output includes: "[tool_use:get_weather({'city': 'Paris'})]"
```

## Cost estimation

The adapter uses a built-in pricing table for Anthropic models:

| Model | Input (per 1M tokens) | Output (per 1M tokens) |
|-------|-----------------------|------------------------|
| claude-opus-4-6 | $15.00 | $75.00 |
| claude-sonnet-4-6 | $3.00 | $15.00 |
| claude-haiku-4-5-20251001 | $0.80 | $4.00 |
| claude-3-5-sonnet-20241022 | $3.00 | $15.00 |
| claude-3-5-haiku-20241022 | $0.80 | $4.00 |
| claude-3-opus-20240229 | $15.00 | $75.00 |
| claude-3-haiku-20240307 | $0.25 | $1.25 |

For models not in the table, `cost_usd` is `None`.

## Limitations

- **Not reentrant** — do not nest two `AnthropicAdapter` contexts.
- Patches the class, not a specific instance — all client instances are affected.
- Streaming responses are not currently intercepted at the span level.

## Combining with the pytest plugin

```python
import pytest
import anthropic
from evalcraft.adapters import AnthropicAdapter
from evalcraft import assert_cost_under, assert_token_count_under
from evalcraft.eval.scorers import Evaluator

@pytest.mark.evalcraft_capture(name="anthropic_haiku_test")
def test_anthropic_haiku(capture_context):
    client = anthropic.Anthropic()

    with AnthropicAdapter():
        capture_context.record_input("What is 2+2?")
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=64,
            messages=[{"role": "user", "content": "What is 2+2?"}],
        )
        capture_context.record_output(response.content[0].text)

    cassette = capture_context.cassette
    assert cassette.llm_call_count == 1

    evaluator = Evaluator()
    evaluator.add(assert_cost_under, cassette, max_usd=0.001)
    evaluator.add(assert_token_count_under, cassette, max_tokens=100)
    result = evaluator.run()
    assert result.passed, str(result.failed_assertions)
```

## Import paths

```python
# Preferred
from evalcraft.adapters import AnthropicAdapter

# Direct
from evalcraft.adapters.anthropic_adapter import AnthropicAdapter
```
