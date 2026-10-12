# order-agent: break the agent, watch the test fail

A small support agent (`agent.py`) that answers order questions by calling a
`lookup_order` tool through the OpenAI SDK, with one offline regression test.

```bash
pip install "evalcraft[pytest,openai]"
cd examples/order-agent
pytest                     # 1 passed: no API key, no network, $0
```

The test runs the real `run_agent` function. Only the model's replies come from
`tests/cassettes/order_status.json`, and every request the code sends must
match the one recorded. Now break the agent instead of the recording. In
`agent.py`, stop running the tool:

```python
            result = {"status": "unknown"}   # was: lookup_order(**args)
```

```text
$ pytest
E   PlaybackMismatchError: model call 2 (recording: tests/cassettes/order_status.json)
E   does not match the recording:
E     messages[3].content.eta: recorded "2026-10-09", now (missing)
E     messages[3].content.status: recorded "shipped", now "unknown"
```

Undo the change and it passes again. A bug inside `lookup_order`, an edited
system prompt or a different model id fails the same way.

## About the recording

`tests/cassettes/order_status.json` was recorded by running this agent and the
real OpenAI SDK against a scripted stand-in for the model (`scripted_model.py`),
so anyone can regenerate it for free:

```bash
python scripted_model.py
```

To record against the real model, set `OPENAI_API_KEY` and run
`pytest --evalcraft-record=all`. That makes two real API calls.
