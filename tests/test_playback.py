"""Playback: current agent code against recorded model responses.

Recordings here are made the way a user makes them: the real OpenAI and
Anthropic SDKs, driven through a scripted HTTP transport instead of a model.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

anthropic = pytest.importorskip("anthropic")
openai = pytest.importorskip("openai")

from evalcraft import CaptureContext, assert_tool_called, playback  # noqa: E402
from evalcraft.adapters import AnthropicAdapter, OpenAIAdapter  # noqa: E402
from evalcraft.core.models import Cassette  # noqa: E402
from evalcraft.playback import (  # noqa: E402
    PlaybackError,
    PlaybackExhaustedError,
    PlaybackIncompleteError,
    PlaybackMismatchError,
    load_interactions,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS = [{"type": "function", "function": {
    "name": "lookup_order", "description": "Look up an order",
    "parameters": {"type": "object", "properties": {"order_id": {"type": "string"}}}}}]
ORDERS = {"ORDER-123": {"status": "shipped"}}


def _openai_reply(n, content=None, call=None):
    message = {"role": "assistant", "content": content}
    if call:
        message["tool_calls"] = [{"id": f"call_{n}", "type": "function", "function": {
            "name": call[0], "arguments": json.dumps(call[1])}}]
    return {"id": f"c{n}", "object": "chat.completion", "created": n, "model": "gpt-6.1-sol",
            "choices": [{"index": 0, "finish_reason": "tool_calls" if call else "stop",
                         "message": message}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}


OPENAI_SCRIPT = [
    _openai_reply(1, call=("lookup_order", {"order_id": "ORDER-123"})),
    _openai_reply(2, content="ORDER-123 has shipped."),
]


def _scripted_openai(script):
    replies = iter(script)
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json=next(replies)))
    return openai.OpenAI(api_key="x", http_client=httpx.Client(transport=transport))


def openai_agent(client, question, *, run_tool=True, extra_turn=False):
    messages = [{"role": "system", "content": "Support agent."},
                {"role": "user", "content": question}]
    while True:
        r = client.chat.completions.create(model="gpt-6.1-sol", messages=messages, tools=TOOLS)
        msg = r.choices[0].message
        if not msg.tool_calls:
            if extra_turn:
                extra_turn = False
                messages.append({"role": "user", "content": "Anything else?"})
                continue
            return msg.content
        messages.append(msg)
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments)
            result = ORDERS.get(args["order_id"], {}) if run_tool else {}
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result)})


@pytest.fixture
def openai_cassette(tmp_path):
    path = tmp_path / "order.json"
    with CaptureContext(name="order", save_path=path), OpenAIAdapter():
        openai_agent(_scripted_openai(OPENAI_SCRIPT), "Where is ORDER-123?")
    return path


LIVE = openai.OpenAI(api_key="x")


class TestOpenAI:
    def test_recording_carries_exact_request_and_response(self, openai_cassette):
        its = load_interactions(Cassette.load(openai_cassette))
        assert len(its) == 2 and all(i.request and i.response for i in its)
        assert its[1].request["messages"][3] == {"role": "tool", "answers": "2.0",
                                                 "content": {"status": "shipped"}}
        assert its[0].request["tools"]["lookup_order"]["description"] == "Look up an order"

    def test_unchanged_code_passes_and_is_recorded(self, openai_cassette):
        with CaptureContext(name="now") as run, playback(openai_cassette):
            assert openai_agent(LIVE, "Where is ORDER-123?") == "ORDER-123 has shipped."
        assert run.cassette.llm_call_count == 2
        assert assert_tool_called(run.cassette, "lookup_order",
                                  with_args={"order_id": "ORDER-123"}).passed

    def test_tool_no_longer_run_fails_with_the_field(self, openai_cassette):
        with pytest.raises(PlaybackMismatchError) as err, playback(openai_cassette):
            openai_agent(LIVE, "Where is ORDER-123?", run_tool=False)
        assert "model call 2" in str(err.value)
        assert 'messages[3].content.status: recorded "shipped", now (missing)' in str(err.value)

    def test_different_input_fails(self, openai_cassette):
        with pytest.raises(PlaybackMismatchError, match="messages\\[1\\].content"), \
                playback(openai_cassette):
            openai_agent(LIVE, "Where is ORDER-999?")

    def test_more_calls_than_recorded(self, openai_cassette):
        with pytest.raises(PlaybackExhaustedError), playback(openai_cassette):
            openai_agent(LIVE, "Where is ORDER-123?", extra_turn=True)

    def test_fewer_calls_than_recorded(self, openai_cassette):
        with pytest.raises(PlaybackIncompleteError), playback(openai_cassette):
            LIVE.chat.completions.create(
                model="gpt-6.1-sol", tools=TOOLS,
                messages=[{"role": "system", "content": "Support agent."},
                          {"role": "user", "content": "Where is ORDER-123?"}])
        with playback(openai_cassette, require_all=False):
            LIVE.chat.completions.create(
                model="gpt-6.1-sol", tools=TOOLS,
                messages=[{"role": "system", "content": "Support agent."},
                          {"role": "user", "content": "Where is ORDER-123?"}])

    def test_agent_swallowing_the_error_still_fails(self, openai_cassette):
        def careless_agent():
            try:
                return openai_agent(LIVE, "Where is ORDER-999?")
            except Exception:
                return "Sorry, something went wrong."
        with pytest.raises(PlaybackMismatchError), playback(openai_cassette):
            assert careless_agent() == "Sorry, something went wrong."

    def test_sequence_mode_and_ignored_fields(self, openai_cassette):
        with playback(openai_cassette, match="sequence"):
            openai_agent(LIVE, "Where is ORDER-999?")
        with playback(openai_cassette, ignore_request_fields=["messages[1].content"]):
            openai_agent(LIVE, "Where is ORDER-123, please?")

    def test_model_change_is_a_mismatch(self, openai_cassette):
        with pytest.raises(PlaybackMismatchError, match="model"), playback(openai_cassette):
            LIVE.chat.completions.create(model="gpt-6-astra", messages=[], tools=TOOLS)

    def test_streaming_is_refused(self, openai_cassette):
        with pytest.raises(PlaybackError, match="streaming"), playback(openai_cassette):
            LIVE.chat.completions.create(model="gpt-6.1-sol", messages=[], stream=True)

    def test_other_network_is_blocked(self, openai_cassette):
        with pytest.raises(Exception, match="(?i)network|blocked|connect"), \
                playback(openai_cassette, require_all=False):
            socket.create_connection(("example.com", 80), timeout=1)

    def test_patch_is_removed_afterwards(self, openai_cassette):
        from openai.resources.chat.completions import Completions
        before = Completions.create
        with playback(openai_cassette, match="sequence"):
            openai_agent(LIVE, "Where is ORDER-123?")
        assert Completions.create is before

    def test_adapter_inside_playback_does_not_double_record(self, openai_cassette):
        with CaptureContext(name="now") as run, playback(openai_cassette), OpenAIAdapter():
            openai_agent(LIVE, "Where is ORDER-123?")
        assert run.cassette.llm_call_count == 2

    def test_async(self, openai_cassette):
        async def go():
            client = openai.AsyncOpenAI(api_key="x")
            messages = [{"role": "system", "content": "Support agent."},
                        {"role": "user", "content": "Where is ORDER-123?"}]
            r = await client.chat.completions.create(
                model="gpt-6.1-sol", messages=messages, tools=TOOLS)
            tc = r.choices[0].message.tool_calls[0]
            messages += [r.choices[0].message, {"role": "tool", "tool_call_id": tc.id,
                                                "content": json.dumps({"status": "shipped"})}]
            r = await client.chat.completions.create(
                model="gpt-6.1-sol", messages=messages, tools=TOOLS)
            return r.choices[0].message.content
        with playback(openai_cassette):
            assert asyncio.run(go()) == "ORDER-123 has shipped."

    def test_legacy_cassette_without_payloads(self, openai_cassette):
        data = json.loads(openai_cassette.read_text())
        for span in data["spans"]:
            for key in ("request", "response", "provider"):
                (span.get("metadata") or {}).pop(key, None)
        openai_cassette.write_text(json.dumps(data))
        with playback(openai_cassette):
            assert openai_agent(LIVE, "Where is ORDER-123?") == "ORDER-123 has shipped."
        with pytest.raises(PlaybackMismatchError, match="line"), playback(openai_cassette):
            openai_agent(LIVE, "Where is ORDER-123?", run_tool=False)


# ── Anthropic ────────────────────────────────────────────────────────────────

ANTHROPIC_SCRIPT = [
    {"id": "m1", "type": "message", "role": "assistant", "model": "claude-sonnet-5-5",
     "content": [{"type": "tool_use", "id": "toolu_1", "name": "lookup_order",
                  "input": {"order_id": "ORDER-123"}}],
     "stop_reason": "tool_use", "stop_sequence": None,
     "usage": {"input_tokens": 10, "output_tokens": 5}},
    {"id": "m2", "type": "message", "role": "assistant", "model": "claude-sonnet-5-5",
     "content": [{"type": "text", "text": "It has shipped."}],
     "stop_reason": "end_turn", "stop_sequence": None,
     "usage": {"input_tokens": 20, "output_tokens": 5}},
]
A_TOOLS = [{"name": "lookup_order", "description": "Look up an order",
            "input_schema": {"type": "object", "properties": {"order_id": {"type": "string"}}}}]


def anthropic_agent(client, question, *, run_tool=True):
    messages = [{"role": "user", "content": question}]
    while True:
        r = client.messages.create(model="claude-sonnet-5-5", max_tokens=512,
                                   system="Support agent.", messages=messages, tools=A_TOOLS)
        uses = [b for b in r.content if b.type == "tool_use"]
        if not uses:
            return "".join(b.text for b in r.content if b.type == "text")
        messages.append({"role": "assistant", "content": r.content})
        messages.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": u.id,
             "content": json.dumps(ORDERS.get(u.input["order_id"], {}) if run_tool else {})}
            for u in uses]})


@pytest.fixture
def anthropic_cassette(tmp_path):
    replies = iter(ANTHROPIC_SCRIPT)
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json=next(replies)))
    client = anthropic.Anthropic(api_key="x", http_client=httpx.Client(transport=transport))
    path = tmp_path / "a.json"
    with CaptureContext(name="a", save_path=path), AnthropicAdapter():
        anthropic_agent(client, "Where is ORDER-123?")
    return path


class TestAnthropic:
    def test_playback_and_mismatch(self, anthropic_cassette):
        live = anthropic.Anthropic(api_key="x")
        with CaptureContext(name="now") as run, playback(anthropic_cassette):
            assert anthropic_agent(live, "Where is ORDER-123?") == "It has shipped."
        assert run.cassette.get_tool_sequence() == ["lookup_order"] or \
            run.cassette.llm_call_count == 2
        with pytest.raises(PlaybackMismatchError, match="tool_result"), \
                playback(anthropic_cassette):
            anthropic_agent(live, "Where is ORDER-123?", run_tool=False)

    def test_wrong_provider_is_a_mismatch(self, anthropic_cassette):
        with pytest.raises(PlaybackMismatchError, match="openai"), \
                playback(anthropic_cassette, require_all=False):
            LIVE.chat.completions.create(model="gpt-6.1-sol", messages=[])

    def test_legacy_rebuild(self, anthropic_cassette):
        data = json.loads(anthropic_cassette.read_text())
        for span in data["spans"]:
            for key in ("request", "response", "provider"):
                (span.get("metadata") or {}).pop(key, None)
        anthropic_cassette.write_text(json.dumps(data))
        live = anthropic.Anthropic(api_key="x")
        with playback(anthropic_cassette, match="sequence"):
            assert anthropic_agent(live, "Where is ORDER-123?") == "It has shipped."


# ── pytest integration and the order-agent example ───────────────────────────

def _pytest(project: Path, *args: str, ci: bool = False) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in ("CI", "OPENAI_API_KEY")}
    if ci:
        env["CI"] = "true"
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *args],
        cwd=project, env=env, capture_output=True, text=True, timeout=180,
    )


@pytest.fixture
def example(tmp_path):
    dest = tmp_path / "order-agent"
    shutil.copytree(REPO_ROOT / "examples" / "order-agent", dest,
                    ignore=shutil.ignore_patterns("__pycache__"))
    return dest


class TestOrderAgentExample:
    """The README's claim: break the agent, not the recording, and the test fails."""

    def _break(self, example, old, new):
        agent = example / "agent.py"
        text = agent.read_text()
        assert old in text
        agent.write_text(text.replace(old, new))

    def test_passes_offline_in_ci(self, example):
        result = _pytest(example, ci=True)
        assert result.returncode == 0, result.stdout + result.stderr

    def test_deleting_the_tool_call_fails(self, example):
        self._break(example, "result = lookup_order(**args)", 'result = {"status": "unknown"}')
        result = _pytest(example, ci=True)
        assert result.returncode != 0
        assert "does not match the recording" in result.stdout
        assert 'messages[3].content.status: recorded "shipped", now "unknown"' in result.stdout

    def test_bug_in_the_tool_fails(self, example):
        self._break(example, "ORDERS.get(order_id,", "ORDERS.get(order_id.lower(),")
        result = _pytest(example, ci=True)
        assert result.returncode != 0 and 'now "not_found"' in result.stdout

    def test_prompt_change_fails(self, example):
        self._break(example, "Use lookup_order for any order question.", "Be brief.")
        result = _pytest(example, ci=True)
        assert result.returncode != 0 and "messages[0].content" in result.stdout

    def test_missing_cassette_fails_in_ci(self, example):
        (example / "tests" / "cassettes" / "order_status.json").unlink()
        result = _pytest(example, ci=True)
        assert result.returncode != 0 and "Cassette not found" in result.stdout

    def test_record_all_records_live(self, example):
        # Live mode talks to the provider: point the SDK at a scripted server via
        # the test itself, then check that the new recording plays back.
        (example / "tests" / "test_live.py").write_text(
            "import httpx, openai, pytest\n"
            "from agent import run_agent\n"
            "from scripted_model import REPLIES\n"
            "@pytest.mark.evalcraft_playback('tests/cassettes/live.json')\n"
            "def test_live(evalcraft_playback):\n"
            "    if evalcraft_playback.live:\n"
            "        it = iter(REPLIES)\n"
            "        t = httpx.MockTransport(lambda r: httpx.Response(200, json=next(it)))\n"
            "        client = openai.OpenAI(api_key='x', http_client=httpx.Client(transport=t))\n"
            "    else:\n"
            "        client = openai.OpenAI(api_key='x')\n"
            "    assert 'shipped' in run_agent(client, 'Where is ORDER-123?')\n"
        )
        assert _pytest(example, "tests/test_live.py", ci=True).returncode != 0  # missing
        recorded = _pytest(example, "tests/test_live.py", "--evalcraft-record=new")
        assert recorded.returncode == 0, recorded.stdout + recorded.stderr
        assert (example / "tests" / "cassettes" / "live.json").exists()
        played = _pytest(example, "tests/test_live.py", ci=True)
        assert played.returncode == 0, played.stdout + played.stderr


# ── regressions from review ──────────────────────────────────────────────────

from evalcraft.playback import PlaybackUnsupportedError  # noqa: E402


class TestNetworkAndUnsupported:
    def test_responses_api_is_refused_even_if_swallowed(self, openai_cassette):
        def agent():
            try:
                LIVE.responses.create(model="gpt-6.1-sol", input="hi")
            except Exception:
                return "fallback"
        with pytest.raises(PlaybackUnsupportedError, match="client.responses.create"), \
                playback(openai_cassette, require_all=False):
            assert agent() == "fallback"

    def test_async_http_is_blocked_and_latched(self, openai_cassette):
        async def fetch():
            async with httpx.AsyncClient() as client:
                try:
                    await client.get("http://example.com/")
                except Exception:
                    return "swallowed"
        with pytest.raises(PlaybackUnsupportedError, match="example.com"), \
                playback(openai_cassette, require_all=False):
            assert asyncio.run(fetch()) == "swallowed"

    def test_sync_http_is_blocked(self, openai_cassette):
        with pytest.raises(PlaybackUnsupportedError), playback(openai_cassette, require_all=False):
            httpx.get("http://example.com/")

    def test_localhost_is_allowed(self, openai_cassette):
        import http.server
        import threading

        server = http.server.HTTPServer(("127.0.0.1", 0), http.server.SimpleHTTPRequestHandler)
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()
        try:
            with playback(openai_cassette, require_all=False):
                status = httpx.get(f"http://127.0.0.1:{server.server_port}/").status_code
            assert status in (200, 404)
        finally:
            server.server_close()

    def test_everything_is_restored(self, openai_cassette):
        from openai.resources.chat.completions import Completions
        from openai.resources.responses import Responses
        before = (Completions.create, Completions.parse, Responses.create,
                  httpx.HTTPTransport.handle_request,
                  httpx.AsyncHTTPTransport.handle_async_request, socket.create_connection)
        with playback(openai_cassette, match="sequence"):
            openai_agent(LIVE, "Where is ORDER-123?")
        after = (Completions.create, Completions.parse, Responses.create,
                 httpx.HTTPTransport.handle_request,
                 httpx.AsyncHTTPTransport.handle_async_request, socket.create_connection)
        assert before == after


def _two_call_cassette(tmp_path):
    reply = _openai_reply(1)
    reply["choices"][0]["message"]["tool_calls"] = [
        {"id": "call_a", "type": "function", "function": {
            "name": "lookup_order", "arguments": json.dumps({"order_id": "A"})}},
        {"id": "call_b", "type": "function", "function": {
            "name": "lookup_order", "arguments": json.dumps({"order_id": "B"})}},
    ]
    reply["choices"][0]["finish_reason"] = "tool_calls"
    path = tmp_path / "two.json"
    with CaptureContext(name="two", save_path=path), OpenAIAdapter():
        two_call_agent(_scripted_openai([reply, _openai_reply(2, content="done")]))
    return path


def two_call_agent(client, *, swap=False, reverse=False):
    messages = [{"role": "user", "content": "A and B?"}]
    r = client.chat.completions.create(model="gpt-6.1-sol", messages=messages, tools=TOOLS)
    msg = r.choices[0].message
    messages.append(msg)
    results = [(tc.id, {"order": json.loads(tc.function.arguments)["order_id"]})
               for tc in msg.tool_calls]
    if swap:
        results = [(results[0][0], results[1][1]), (results[1][0], results[0][1])]
    if reverse:
        results.reverse()
    for call_id, result in results:
        messages.append({"role": "tool", "tool_call_id": call_id, "content": json.dumps(result)})
    return client.chat.completions.create(model="gpt-6.1-sol", messages=messages, tools=TOOLS)


class TestStricterMatching:
    def test_results_attached_to_the_wrong_call_fail(self, tmp_path):
        path = _two_call_cassette(tmp_path)
        with playback(path):
            two_call_agent(LIVE)
        with playback(path):
            two_call_agent(LIVE, reverse=True)  # same answers, different order: fine
        with pytest.raises(PlaybackMismatchError), playback(path):
            two_call_agent(LIVE, swap=True)

    def test_tool_description_and_settings_are_compared(self, openai_cassette):
        changed = [dict(TOOLS[0], function=dict(TOOLS[0]["function"], description="Find it"))]
        with pytest.raises(PlaybackMismatchError, match="tools.lookup_order.description"), \
                playback(openai_cassette, require_all=False):
            LIVE.chat.completions.create(
                model="gpt-6.1-sol", tools=changed,
                messages=[{"role": "system", "content": "Support agent."},
                          {"role": "user", "content": "Where is ORDER-123?"}])
        with pytest.raises(PlaybackMismatchError, match="params.temperature"), \
                playback(openai_cassette, require_all=False):
            LIVE.chat.completions.create(
                model="gpt-6.1-sol", tools=TOOLS, temperature=0.9,
                messages=[{"role": "system", "content": "Support agent."},
                          {"role": "user", "content": "Where is ORDER-123?"}])

    def test_anthropic_is_error_is_compared(self, anthropic_cassette):
        live = anthropic.Anthropic(api_key="x")

        def agent(is_error):
            messages = [{"role": "user", "content": "Where is ORDER-123?"}]
            r = live.messages.create(model="claude-sonnet-5-5", max_tokens=512,
                                     system="Support agent.", messages=messages, tools=A_TOOLS)
            use = next(b for b in r.content if b.type == "tool_use")
            messages += [{"role": "assistant", "content": r.content},
                         {"role": "user", "content": [{
                             "type": "tool_result", "tool_use_id": use.id, "is_error": is_error,
                             "content": json.dumps({"status": "shipped"})}]}]
            live.messages.create(model="claude-sonnet-5-5", max_tokens=512,
                                 system="Support agent.", messages=messages, tools=A_TOOLS)
        with pytest.raises(PlaybackMismatchError, match="is_error"), \
                playback(anthropic_cassette):
            agent(True)

    def test_unknown_enum_values_still_play_back(self, openai_cassette):
        data = json.loads(openai_cassette.read_text())
        last = [s for s in data["spans"] if s.get("metadata", {}).get("response")][-1]
        last["metadata"]["response"]["choices"][0]["finish_reason"] = "something_new"
        openai_cassette.write_text(json.dumps(data))
        with playback(openai_cassette):
            assert openai_agent(LIVE, "Where is ORDER-123?") == "ORDER-123 has shipped."

    def test_legacy_anthropic_strict_ignores_generated_ids(self, anthropic_cassette):
        data = json.loads(anthropic_cassette.read_text())
        for span in data["spans"]:
            for key in ("request", "response", "provider"):
                (span.get("metadata") or {}).pop(key, None)
        anthropic_cassette.write_text(json.dumps(data))
        with playback(anthropic_cassette):
            anthropic_agent(anthropic.Anthropic(api_key="x"), "Where is ORDER-123?")

    def test_redacted_recording_still_matches(self, tmp_path):
        path = tmp_path / "r.json"
        with CaptureContext(name="r", save_path=path, redact=True), OpenAIAdapter():
            openai_agent(_scripted_openai(OPENAI_SCRIPT), "Mail me at jane@example.com")
        assert "jane@example.com" not in path.read_text()
        with playback(path):
            openai_agent(LIVE, "Mail me at jane@example.com")


PYTEST_CASES = '''
import json, pytest
from openai import OpenAI
from agent import run_agent

CASSETTE = "tests/cassettes/order_status.json"

@pytest.mark.evalcraft_playback(CASSETTE)
def test_swallowed(evalcraft_playback):
    try:
        run_agent(OpenAI(api_key="x"), "Where is ORDER-999?")
    except Exception:
        pass

@pytest.mark.evalcraft_playback(CASSETTE)
def test_plain_mismatch(evalcraft_playback):
    run_agent(OpenAI(api_key="x"), "Where is ORDER-999?")

@pytest.mark.evalcraft_playback(CASSETTE)
def test_user_assertion(evalcraft_playback):
    assert False, "my own check"
'''


class TestPytestReporting:
    def test_failures_are_reported_once_as_failures(self, example):
        (example / "tests" / "test_cases.py").write_text(PYTEST_CASES)
        result = _pytest(example, "tests/test_cases.py", "-rfE")
        out = result.stdout
        assert "3 failed" in out and "error" not in out.splitlines()[-1].lower(), out
        assert "FAILED tests/test_cases.py::test_swallowed - " in out
        assert "PlaybackIncompleteError" not in out.split("short test summary")[1]
        assert "my own check" in out

    def test_failing_live_run_keeps_the_old_recording(self, example):
        cassette = example / "tests" / "cassettes" / "order_status.json"
        before = cassette.read_bytes()
        (example / "tests" / "test_fail.py").write_text(
            "import pytest\n"
            "@pytest.mark.evalcraft_playback('tests/cassettes/order_status.json')\n"
            "def test_fail(evalcraft_playback):\n"
            "    assert evalcraft_playback.live\n"
            "    assert False\n")
        result = _pytest(example, "tests/test_fail.py", "--evalcraft-record=all")
        assert result.returncode != 0
        assert cassette.read_bytes() == before
        assert not list(cassette.parent.glob("*.tmp"))
