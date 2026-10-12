# Google Gemini adapter

`GeminiAdapter()` captures non-streaming calls made through the current
[`google-genai` SDK](https://googleapis.github.io/python-genai/). It records
`client.models.generate_content()` and
`await client.aio.models.generate_content()` into the active `CaptureContext`.

## Install and migration

```bash
pip install "evalcraft[gemini]"
```

Google [recommends the Google GenAI SDK](https://ai.google.dev/gemini-api/docs/libraries)
and deprecated the legacy Python `google-generativeai` library on November 30,
2025. The Evalcraft context-manager name stays `GeminiAdapter()`, but application
calls must use the current SDK:

| Legacy application code | Current application code |
| --- | --- |
| `import google.generativeai as genai` | `from google import genai` |
| `genai.configure(api_key=...)` | `client = genai.Client(api_key=...)` |
| `genai.GenerativeModel(model_name)` | Pass `model=model_name` on each call |
| `model.generate_content(contents)` | `client.models.generate_content(model=..., contents=...)` |
| `await model.generate_content_async(contents)` | `await client.aio.models.generate_content(model=..., contents=...)` |

The adapter no longer intercepts legacy SDK calls. Install and migrate the SDK
in your application before relying on capture.

## Sync usage

Recording a real provider response calls the model and costs money. The test
suite below uses fake responses and needs no API key.

```python
from google import genai
from evalcraft import CaptureContext
from evalcraft.adapters import GeminiAdapter

with genai.Client() as client:
    with CaptureContext(name="gemini_example") as ctx, GeminiAdapter():
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents="Summarize the refund policy in one sentence.",
        )
        ctx.record_output(response.text or "")

cassette = ctx.cassette
```

Use a model available to your account. The model in this example demonstrates
the call shape rather than recommending a current production model.

## Async usage

```python
from google import genai
from evalcraft import CaptureContext
from evalcraft.adapters import GeminiAdapter

async def run_example():
    async with genai.Client().aio as client:
        with CaptureContext(name="async_gemini") as ctx:
            async with GeminiAdapter():
                response = await client.models.generate_content(
                    model="gemini-2.5-flash", contents="Hello",
                )
                ctx.record_output(response.text or "")
        return ctx.cassette
```

## What is recorded

The adapter patches the sync `Models` and async `AsyncModels` resource classes,
so it captures clients created before entering the adapter. Original methods
are restored on exit, including after provider errors. Nested adapter contexts
raise `RuntimeError` to prevent duplicate recordings or premature restoration.

Each successful call records readable input, the first candidate's visible text
and function-call requests, duration, model, finish reason, and token usage.
Function-call names and arguments also appear in `span.metadata["function_calls"]`.
A requested function is not an executed tool: wrap the actual application
function with Evalcraft's tool capture to record execution and its result.
The SDK may automatically execute Python functions supplied as tools and make
several internal model turns. This adapter records the high-level method result;
it does not separately record those internal turns or tool executions.

Following Google's [token metadata documentation](https://ai.google.dev/gemini-api/docs/generate-content/tokens):

- `prompt_tokens` contains fresh input: `prompt_token_count` minus
  `cached_content_token_count`.
- `cache_read_tokens` contains cached input, capped at the total reported input
  if a mocked or inconsistent SDK response reports more cached tokens.
- `completion_tokens` includes `candidates_token_count` plus
  `thoughts_token_count`. Thought text is excluded from visible output, and
  the thought-token count is retained in span metadata.
- Missing or mocked usage fields become ordinary integer zeroes.

Built-in cost rates are historical text-token estimates. Cached input is
conservatively priced at the ordinary input rate unless you register a
`cached_input_usd_per_mtok` override through `register_price`. They exclude
cache storage, multimodal tiers, grounding, and provider tool charges; an
unlisted model has `cost_usd=None`.

## API-key-free adapter tests

```bash
python -m pytest tests/test_gemini_adapter.py
```

The basic tests use fake resource classes. If `google-genai` is installed,
additional tests exercise the real SDK through an `httpx.MockTransport`; no
request leaves the process and the key is a synthetic placeholder.

## Coverage limits

Streaming (`generate_content_stream`), Live API calls, and the legacy SDK are
not intercepted. Gemini playback is not implemented: this capture adapter does
not extend Playback's supported-provider guarantees. Global class patching is
process-local; avoid overlapping adapter contexts across threads.
