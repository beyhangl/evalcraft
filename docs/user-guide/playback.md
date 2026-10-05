# Playback — test your current agent code offline

`replay()` reads a recording back; it never runs your code. That's useful for
checking a saved run against contracts, but it can't tell you whether a change
to your agent broke something. **Playback can.** Your agent runs for real
(its prompts, its tools, its control flow) and every OpenAI or Anthropic call
it makes is answered from a recording instead of the network.

```python
from evalcraft import CaptureContext, assert_tool_called, playback

with CaptureContext(name="now") as run, playback("tests/cassettes/order_status.json"):
    answer = run_agent(client, "Where is ORDER-123?")

assert "shipped" in answer
assert assert_tool_called(run.cassette, "lookup_order",
                          with_args={"order_id": "ORDER-123"}).passed
```

Inside a `CaptureContext`, the calls playback answers are recorded into the new
cassette. Note that the tool calls in it are the ones the *model* asked for, so
they come from the recording. What checks that your code actually ran the
tool, and ran it correctly, is the request match below: the tool's result is
part of the next request.

## What makes it fail

Each model call must match the request the recording was made with. The
comparison covers the model id, every message (including the tool calls the
code echoes back and the tool results it computed, and which call each result
answers), the system prompt, the tools offered (name, description and schema)
and the other settings the code passed (`temperature`, `tool_choice`,
`max_tokens`, `response_format`, …). Generated ids, key order and the order of
results answering the same turn are ignored. Values masked by
`CaptureContext(redact=True)` match whatever they masked.

| The current code… | Result |
|---|---|
| sends the same requests as when recorded | passes |
| stops running a tool, or a tool returns something else | `PlaybackMismatchError` naming the field, e.g. `messages[3].content.status: recorded "shipped", now "unknown"` |
| has a different prompt, user input or model id | `PlaybackMismatchError` naming the field |
| makes more model calls than recorded | `PlaybackExhaustedError` |
| stops after fewer calls | `PlaybackIncompleteError` when the block ends |
| catches the error inside the agent and carries on | the error is raised again when the block ends |
| uses a client method playback doesn't answer (`responses.create`, `.parse`, `.stream`) | `PlaybackUnsupportedError`, even if the agent catches it |
| opens any other network connection, sync or async | blocked the same way; localhost stays reachable (`allow_hosts`), `block_network=False` turns it off |

All of these are `AssertionError`s. With the pytest fixture they are reported
as a failure of the test itself, once, and if the test already failed for its
own reason, that failure is the one you see.

## In pytest

```python
@pytest.mark.evalcraft_playback("tests/cassettes/order_status.json")
def test_answers_order_status(evalcraft_playback):
    answer = run_agent(OpenAI(api_key="playback"), "Where is ORDER-123?")
    assert "shipped" in answer
    run = evalcraft_playback.cassette          # what the current code just did
    assert assert_tool_called(run, "lookup_order").passed
```

The fixture follows the usual record modes:

| `--evalcraft-record` | Cassette exists | Cassette missing |
|---|---|---|
| `none` (default) | play back | fail in CI, skip locally |
| `new` | play back (re-record if [expired](expiry.md)) | run live and save it |
| `all` | run live and overwrite | run live and save it |

In live mode the OpenAI and Anthropic adapters record the real calls, and
`evalcraft_playback.live` is `True`. The recording is saved only if the test
passes, so a failing live run never replaces a good cassette. A live run calls
the real provider and costs money.

## Options

```python
playback(path, match="strict", ignore_request_fields=(), block_network=True,
         allow_hosts=("localhost", "127.0.0.1", "::1"), require_all=True)
```

The marker takes the same keyword arguments:
`@pytest.mark.evalcraft_playback(path, ignore_request_fields=["messages[0].content"])`.

- `match="sequence"` answers calls in order without comparing requests, for
  tests that only care about how the code handles the replies.
- `ignore_request_fields` leaves fields out of the comparison. Patterns use `*`
  and `?`, and brackets are literal: `"messages[0].content"` for a system prompt
  that embeds today's date. A prompt that changes on every run is better fixed
  in the code; `evalcraft check-stale` flags timestamps and IDs baked into a
  recording.
- `require_all=False` allows the code to make fewer calls than recorded.

## Limits

- **Supported:** OpenAI Chat Completions (`client.chat.completions.create`) and
  Anthropic Messages (`client.messages.create`), sync and async.
- **Not yet:** streaming, the OpenAI Responses API, `.parse()`,
  `with_raw_response`, Gemini and framework-level clients such as LangGraph.
  Streaming, `.parse()`, `.stream()` and the Responses API fail with
  `PlaybackUnsupportedError`. `with_raw_response` isn't supported either.
  Anything else that tries to reach the network is blocked.
- **Your tools run for real.** If a tool talks to a database or an API, mock
  it in the test as you would anywhere else. Playback replaces the model, not
  the world.
- Calls are matched in the order they happen. Code that makes model calls
  from several threads at once can fail to match even when nothing changed.

## Recordings from older versions

Cassettes recorded with evalcraft 0.13 or later store the exact provider
request and response. Older cassettes still play back: the responses are
rebuilt from the recorded text and tool calls, and requests are compared as
text. Re-record to get field-level mismatch messages.
