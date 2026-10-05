"""Run current agent code against a recording's model responses.

``replay()`` reads a recording back; it never runs your code. Playback does:
your agent runs for real (its prompts, its tools, its control flow) and every
OpenAI Chat Completions or Anthropic Messages call it makes is answered from
the recording instead of the network. Each call must match the request the
recording was made with, so a change in what the code sends (a tool that no
longer runs, a result computed differently, a prompt edited) fails right away
with the field that changed, and a call with no recording fails instead of
reaching a paid API.

    from evalcraft import capture, playback

    with capture() as run, playback("tests/cassettes/refund.json"):
        answer = my_agent("Where is order 123?")
    assert_tool_called(run.cassette, "lookup_order")

Inside a capture, the calls playback answers are recorded into the new
cassette, so assertions read what the current code did.
"""

from __future__ import annotations

import ast
import json
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evalcraft.core.models import Cassette, Span, SpanKind
from evalcraft.playback import registry
from evalcraft.playback.canonical import (
    PROVIDER_KEY,
    REQUEST_KEY,
    RESPONSE_KEY,
    anthropic_request,
    openai_request,
)
from evalcraft.replay.network_guard import NetworkGuard

MAX_FIELDS_SHOWN = 6


class PlaybackError(AssertionError):
    """The code under test did not do what the recording expects."""


class PlaybackMismatchError(PlaybackError):
    """A model call differs from the request the recording was made with."""


class PlaybackExhaustedError(PlaybackError):
    """The code made more model calls than the recording holds."""


class PlaybackIncompleteError(PlaybackError):
    """The code made fewer model calls than the recording holds."""


class PlaybackUnsupportedError(PlaybackError):
    """The code used a client method or connection playback doesn't answer."""


#: Hosts the code may still reach during playback: local test servers.
DEFAULT_ALLOW_HOSTS = ("localhost", "127.0.0.1", "::1")


@dataclass
class Interaction:
    """One recorded model call: what was sent and what came back."""

    index: int
    provider: str
    model: str | None
    request: dict[str, Any] | None
    input_text: str
    response: dict[str, Any]


def _display(path: str | Path) -> str:
    """``path`` relative to the working directory when it is inside it."""
    try:
        return str(Path(path).resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


# ── loading ──────────────────────────────────────────────────────────────────

_OPENAI_CALL = re.compile(r"\[tool_call:(?P<name>[^(\]]+)\((?P<args>.*?)\)\](?=\s|$)", re.S)
_ANTHROPIC_CALL = re.compile(r"\[tool_use:(?P<name>[^(\]]+)\((?P<input>.*?)\)\](?=\s|$)", re.S)


def _provider(span: Span) -> str:
    meta = span.metadata or {}
    if meta.get(PROVIDER_KEY) in ("openai", "anthropic"):
        return str(meta[PROVIDER_KEY])
    if "stop_reason" in meta or (span.model or "").startswith("claude"):
        return "anthropic"
    return "openai"


def _usage(span: Span) -> tuple[int, int]:
    u = span.token_usage
    return (u.prompt_tokens, u.completion_tokens) if u else (0, 0)


def _rebuild_openai(index: int, span: Span) -> dict[str, Any]:
    text = str(span.output or "")
    calls = [(m.group("name").strip(), m.group("args")) for m in _OPENAI_CALL.finditer(text)]
    text = _OPENAI_CALL.sub("", text).strip()
    prompt, completion = _usage(span)
    tool_calls = [
        {"id": f"call_playback_{index}_{k}", "type": "function",
         "function": {"name": name, "arguments": args}}
        for k, (name, args) in enumerate(calls)
    ]
    finish = (span.metadata or {}).get("finish_reason") or ("tool_calls" if calls else "stop")
    return {
        "id": f"chatcmpl-playback-{index}", "object": "chat.completion", "created": 0,
        "model": span.model or "unknown",
        "choices": [{"index": 0, "finish_reason": finish, "message": {
            "role": "assistant", "content": text or None,
            **({"tool_calls": tool_calls} if tool_calls else {}),
        }}],
        "usage": {"prompt_tokens": prompt, "completion_tokens": completion,
                  "total_tokens": prompt + completion},
    }


def _rebuild_anthropic(index: int, span: Span) -> dict[str, Any]:
    text = str(span.output or "")
    blocks: list[dict[str, Any]] = list((span.metadata or {}).get("reasoning") or [])
    calls = []
    for k, m in enumerate(_ANTHROPIC_CALL.finditer(text)):
        try:
            tool_input = ast.literal_eval(m.group("input"))
        except (ValueError, SyntaxError):
            tool_input = {}
        calls.append({"type": "tool_use", "id": f"toolu_playback_{index}_{k}",
                      "name": m.group("name").strip(), "input": tool_input})
    text = _ANTHROPIC_CALL.sub("", text).strip()
    if text:
        blocks.append({"type": "text", "text": text})
    blocks.extend(calls)
    prompt, completion = _usage(span)
    stop = (span.metadata or {}).get("stop_reason") or ("tool_use" if calls else "end_turn")
    return {
        "id": f"msg_playback_{index}", "type": "message", "role": "assistant",
        "model": span.model or "unknown", "content": blocks, "stop_reason": stop,
        "stop_sequence": None,
        "usage": {"input_tokens": prompt, "output_tokens": completion},
    }


def load_interactions(cassette: Cassette) -> list[Interaction]:
    """The model calls of ``cassette``, in order, ready to be played back.

    Recordings made with evalcraft 0.13+ carry the exact provider request and
    response. Older ones are rebuilt from the recorded text and tool calls,
    which is enough for the usual tool-calling loop.
    """
    out: list[Interaction] = []
    for span in cassette.spans:
        if span.kind not in (SpanKind.LLM_REQUEST, SpanKind.LLM_RESPONSE) or span.error:
            continue
        index = len(out)
        meta = span.metadata or {}
        provider = _provider(span)
        response = meta.get(RESPONSE_KEY)
        if not isinstance(response, dict):
            response = (_rebuild_anthropic if provider == "anthropic" else _rebuild_openai)(
                index, span
            )
        request = meta.get(REQUEST_KEY)
        out.append(Interaction(
            index=index, provider=provider, model=span.model,
            request=request if isinstance(request, dict) else None,
            input_text=str(span.input or ""), response=response,
        ))
    return out


# ── comparison ───────────────────────────────────────────────────────────────

def _flat(value: Any) -> dict[str, Any]:
    from evalcraft.replay.tool_diff import _flatten

    return _flatten(value, "request")


_MISSING = object()


def _show(value: Any) -> str:
    if value is _MISSING:
        return "(missing)"
    text = json.dumps(value, default=str)
    return text if len(text) <= 120 else text[:117] + '..."'


def _differences(recorded: dict[str, Any], current: dict[str, Any],
                 ignore: tuple[str, ...]) -> list[str]:
    from evalcraft.replay.tool_diff import glob_match

    a, b = _flat(recorded), _flat(current)
    lines = []
    for key in sorted(set(a) | set(b)):
        field = key.removeprefix("request.")
        if any(glob_match(p, field) for p in ignore):
            continue
        x, y = a.get(key, _MISSING), b.get(key, _MISSING)
        if x != y and not _redacted_match(x, y):
            lines.append(f"  {field}: recorded {_show(x)}, now {_show(y)}")
    return lines


#: Default mask written by ``CaptureContext(redact=True)``.
REDACTION_MASK = "***"
_IDS = re.compile(r"\b(?:toolu|call|chatcmpl|msg)_[A-Za-z0-9_]+")


def _redacted_match(recorded: Any, current: Any) -> bool:
    """A redacted recorded value matches any live value it could have come from."""
    if not (isinstance(recorded, str) and isinstance(current, str)):
        return False
    if REDACTION_MASK not in recorded:
        return False
    pattern = ".+".join(re.escape(part) for part in recorded.split(REDACTION_MASK))
    return re.fullmatch(pattern, current, re.S) is not None


def _text_difference(recorded: str, current: str) -> list[str]:
    # Older recordings compare as text; generated ids differ on every run.
    recorded, current = _IDS.sub("<id>", recorded), _IDS.sub("<id>", current)
    old, new = recorded.splitlines(), current.splitlines()
    for n in range(max(len(old), len(new))):
        x: Any = old[n] if n < len(old) else _MISSING
        y: Any = new[n] if n < len(new) else _MISSING
        if x != y and not _redacted_match(x, y):
            return [f"  line {n + 1}: recorded {_show(x)}, now {_show(y)}"]
    return []


# ── playback ─────────────────────────────────────────────────────────────────

class Playback:
    """Answer the code's model calls from a recording. See the module docstring.

    Args:
        cassette: a :class:`Cassette` or a path to one.
        match: ``"strict"`` (default) fails when a call's request differs from
            the recorded one. ``"sequence"`` answers calls in order without
            comparing them, for when only the responses matter.
        ignore_request_fields: glob patterns of request fields to leave out of
            the comparison, such as ``"messages[0].content"`` for a system
            prompt that embeds today's date.
        block_network: block other outgoing connections while active, so
            nothing the recording doesn't cover reaches a paid API. A blocked
            connection fails the playback even if the code catches the error.
        allow_hosts: hosts still reachable while the network is blocked
            (default: localhost, for your own test servers).
        require_all: fail on exit when the code made fewer calls than recorded.
    """

    def __init__(
        self,
        cassette: Cassette | str | Path,
        *,
        match: str = "strict",
        ignore_request_fields: tuple[str, ...] | list[str] = (),
        block_network: bool = True,
        allow_hosts: tuple[str, ...] | list[str] = DEFAULT_ALLOW_HOSTS,
        require_all: bool = True,
    ) -> None:
        if match not in ("strict", "sequence"):
            raise ValueError("match must be 'strict' or 'sequence'")
        self.source = _display(cassette) if isinstance(cassette, (str, Path)) else cassette.name
        self.recorded = cassette if isinstance(cassette, Cassette) else Cassette.load(cassette)
        self.match = match
        self.ignore = tuple(ignore_request_fields)
        self.block_network = block_network
        self.allow_hosts = tuple(allow_hosts)
        self.require_all = require_all
        self._lock = threading.Lock()
        self.interactions = load_interactions(self.recorded)
        self.calls_made = 0
        self.failure: PlaybackError | None = None
        self._guard: NetworkGuard | None = None
        self._restore: list[tuple[Any, str, Any]] = []

    @property
    def remaining(self) -> int:
        return len(self.interactions) - self.calls_made

    # -- answering ------------------------------------------------------------

    def _answer(self, provider: str, kwargs: dict[str, Any]) -> Any:
        __tracebackhide__ = True
        try:
            with self._lock:
                return self._answer_or_raise(provider, kwargs)
        except PlaybackError as exc:
            self._latch(exc)
            raise

    def _latch(self, exc: PlaybackError) -> None:
        # Remember it: agent code that catches every exception around its
        # model call would otherwise turn this failure into a pass.
        if self.failure is None:
            self.failure = exc

    def _refuse(self, what: str) -> PlaybackUnsupportedError:
        exc = PlaybackUnsupportedError(
            f"{what} isn't answered by playback (recording: {self.source}). Playback "
            "covers client.chat.completions.create and client.messages.create without "
            "streaming. Use one of those in this test, or run it live."
        )
        self._latch(exc)
        return exc

    def _answer_or_raise(self, provider: str, kwargs: dict[str, Any]) -> Any:
        __tracebackhide__ = True
        number = self.calls_made + 1
        where = f"model call {number} (recording: {self.source})"
        if kwargs.get("stream"):
            raise PlaybackUnsupportedError(f"{where}: streaming calls can't be played back yet.")
        if self.calls_made >= len(self.interactions):
            raise PlaybackExhaustedError(
                f"{where}: the code made more model calls than the recording holds "
                f"({len(self.interactions)}). The agent's control flow changed, or the "
                "recording is incomplete. Re-record if the change is intended."
            )
        it = self.interactions[self.calls_made]
        if it.provider != provider:
            raise PlaybackMismatchError(
                f"{where}: the code called {provider}, the recording has a {it.provider} "
                "call here."
            )
        if self.match == "strict":
            self._compare(where, provider, it, kwargs)
        self.calls_made += 1
        response = self._build(provider, it.response)
        self._record(provider, kwargs, response)
        registry.mark_played(response)
        return response

    def _compare(self, where: str, provider: str, it: Interaction,
                 kwargs: dict[str, Any]) -> None:
        __tracebackhide__ = True
        if it.request is not None:
            current = openai_request(kwargs) if provider == "openai" else anthropic_request(kwargs)
            current = json.loads(json.dumps(current, default=str))
            lines = _differences(it.request, current, self.ignore)
        else:
            if provider == "openai":
                from evalcraft.adapters.openai_adapter import _messages_to_str
            else:
                from evalcraft.adapters.anthropic_adapter import (
                    _messages_to_str,  # type: ignore[assignment]
                )
            lines = _text_difference(it.input_text, _messages_to_str(kwargs.get("messages") or []))
        if lines:
            more = len(lines) - MAX_FIELDS_SHOWN
            shown = "\n".join(lines[:MAX_FIELDS_SHOWN])
            if more > 0:
                shown += f"\n  ... and {more} more"
            raise PlaybackMismatchError(
                f"{where} does not match the recording:\n{shown}\n"
                "The current code sent a different request than the one recorded. If the "
                "change is intended, re-record (pytest --evalcraft-record=all)."
            )

    @staticmethod
    def _build(provider: str, payload: dict[str, Any]) -> Any:
        # The SDKs read live responses leniently (an unknown stop reason from a
        # newer API version is fine), so playback does too.
        if provider == "openai":
            from openai._models import construct_type as openai_construct
            from openai.types.chat import ChatCompletion

            return openai_construct(type_=ChatCompletion, value=payload)
        from anthropic._models import construct_type as anthropic_construct
        from anthropic.types import Message

        return anthropic_construct(type_=Message, value=payload)

    @staticmethod
    def _record(provider: str, kwargs: dict[str, Any], response: Any) -> None:
        if provider == "openai":
            from evalcraft.adapters.openai_adapter import OpenAIAdapter

            OpenAIAdapter()._record_response(kwargs, response, 0.0)
        else:
            from evalcraft.adapters.anthropic_adapter import AnthropicAdapter

            AnthropicAdapter()._record_response(kwargs, response, 0.0)

    # -- patching -------------------------------------------------------------

    def _patch(self) -> None:
        player = self

        def answer(provider: str, is_async: bool) -> Any:
            if is_async:
                async def acreate(_self: Any, *args: Any, **kwargs: Any) -> Any:
                    __tracebackhide__ = True
                    return player._answer(provider, kwargs)
                return acreate

            def create(_self: Any, *args: Any, **kwargs: Any) -> Any:
                __tracebackhide__ = True
                return player._answer(provider, kwargs)
            return create

        def refuse(what: str, is_async: bool) -> Any:
            if is_async:
                async def arefused(_self: Any, *args: Any, **kwargs: Any) -> Any:
                    __tracebackhide__ = True
                    raise player._refuse(what)
                return arefused

            def refused(_self: Any, *args: Any, **kwargs: Any) -> Any:
                __tracebackhide__ = True
                raise player._refuse(what)
            return refused

        def install(cls: Any, name: str, replacement: Any) -> None:
            self._restore.append((cls, name, cls.__dict__.get(name, _MISSING)))
            setattr(cls, name, replacement)

        try:
            from openai.resources.chat.completions import AsyncCompletions, Completions

            for cls, is_async in _sync_and_async(Completions, AsyncCompletions):
                install(cls, "create", answer("openai", is_async))
                for name in ("parse", "stream"):
                    if hasattr(cls, name):
                        install(cls, name, refuse(f"client.chat.completions.{name}", is_async))
        except ImportError:
            pass
        try:
            from openai.resources.responses import AsyncResponses, Responses

            for cls, is_async in _sync_and_async(Responses, AsyncResponses):
                for name in ("create", "parse", "stream"):
                    if hasattr(cls, name):
                        install(cls, name, refuse(f"client.responses.{name}", is_async))
        except ImportError:
            pass
        try:
            from anthropic.resources.messages import AsyncMessages, Messages

            for cls, is_async in _sync_and_async(Messages, AsyncMessages):
                install(cls, "create", answer("anthropic", is_async))
                if hasattr(cls, "stream"):
                    install(cls, "stream", refuse("client.messages.stream", False))
        except ImportError:
            pass
        if self.block_network:
            self._patch_transports()

    def _patch_transports(self) -> None:
        """Refuse HTTP requests that leave the machine, sync and async.

        Blocking sockets alone misses async clients, which connect through the
        event loop, so the httpx transports are patched as well.
        """
        try:
            import httpx
        except ImportError:
            return
        player = self

        def blocked(request: Any) -> PlaybackUnsupportedError:
            return player._refuse(f"a network request to {request.url.host}")

        def allowed(request: Any) -> bool:
            return request.url.host in player.allow_hosts

        sync_original = httpx.HTTPTransport.handle_request
        async_original = httpx.AsyncHTTPTransport.handle_async_request

        def handle_request(transport: Any, request: Any) -> Any:
            if not allowed(request):
                raise blocked(request)
            return sync_original(transport, request)

        async def handle_async_request(transport: Any, request: Any) -> Any:
            if not allowed(request):
                raise blocked(request)
            return await async_original(transport, request)

        for cls, name, fn in ((httpx.HTTPTransport, "handle_request", handle_request),
                              (httpx.AsyncHTTPTransport, "handle_async_request",
                               handle_async_request)):
            self._restore.append((cls, name, cls.__dict__.get(name, _MISSING)))
            setattr(cls, name, fn)

    def _unpatch(self) -> None:
        for cls, name, original in reversed(self._restore):
            if original is _MISSING:
                delattr(cls, name)
            else:
                setattr(cls, name, original)
        self._restore.clear()

    # -- lifecycle ------------------------------------------------------------

    def pending_failure(self) -> PlaybackError | None:
        """The failure to report once the code under test has finished, if any."""
        if self.failure is not None:
            return self.failure
        if self.require_all and self.remaining > 0:
            return PlaybackIncompleteError(
                f"The code made {self.calls_made} model call(s); the recording "
                f"({self.source}) holds {len(self.interactions)}. The agent stopped "
                "earlier than when this was recorded."
            )
        return None

    def start(self) -> Playback:
        self._patch()
        registry.enter(self)
        if self.block_network:
            self._guard = NetworkGuard(allowlist=self.allow_hosts)
            self._guard.__enter__()
        return self

    def stop(self) -> None:
        if self._guard is not None:
            self._guard.__exit__(None, None, None)
            self._guard = None
        self._unpatch()
        registry.leave(self)

    def __enter__(self) -> Playback:
        return self.start()

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.stop()
        if exc_type is None:
            failure = self.pending_failure()
            if failure is not None:
                raise failure

    async def __aenter__(self) -> Playback:
        return self.__enter__()

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.__exit__(exc_type, exc, tb)


def _sync_and_async(sync_cls: Any, async_cls: Any) -> list[tuple[Any, bool]]:
    return [(sync_cls, False), (async_cls, True)]


def playback(cassette: Cassette | str | Path, **options: Any) -> Playback:
    """Play back ``cassette``'s model responses to the code run inside the block."""
    return Playback(cassette, **options)
