"""One shape for a provider request, shared by recording and playback.

Playback answers a model call from a recording only if the current code sent
the same request the recording was made with. "The same" has to ignore what
legitimately changes between runs (SDK object types, generated tool-call ids,
key order) and keep everything the agent decides: the model, the messages, the
tool calls it echoed back, the tool results it computed, and which tools it
offered. Adapters store this shape in span metadata when they record, and
playback computes it again from the live call and compares the two.
"""

from __future__ import annotations

import json
from typing import Any

REQUEST_KEY = "request"
RESPONSE_KEY = "response"
PROVIDER_KEY = "provider"


def _plain(value: Any) -> Any:
    """SDK objects (pydantic models) to plain dicts and lists."""
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        try:
            data = dump(exclude_none=True)
        except TypeError:
            data = dump()
        # Only trust real dumps; a mock's model_dump returns another mock.
        return _plain(data) if isinstance(data, (dict, list)) else str(value)
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def _json_or_text(value: Any) -> Any:
    if isinstance(value, str):
        text = value.strip()
        if text[:1] in ("{", "["):
            try:
                return json.loads(text)
            except ValueError:
                return value
    return value


def _text(content: Any) -> Any:
    """Message content as text when it is only text, else normalised blocks."""
    content = _plain(content)
    if isinstance(content, list):
        blocks = [_block(b) for b in content]
        if all(isinstance(b, dict) and set(b) == {"text"} for b in blocks):
            return "".join(b["text"] for b in blocks)
        return blocks
    return content if content is not None else ""


def _block(block: Any) -> Any:
    if not isinstance(block, dict):
        return block
    kind = block.get("type")
    if kind == "text":
        return {"text": block.get("text", "")}
    if kind == "tool_use":
        return {"tool_use": block.get("name"), "input": block.get("input", {})}
    if kind == "tool_result":
        return {"tool_result": _json_or_text(_text(block.get("content", "")))}
    if kind in ("thinking", "redacted_thinking"):
        # Opaque reasoning is passed back verbatim; its text says nothing about
        # what the agent decided.
        return {"type": kind}
    return {k: v for k, v in block.items() if k not in ("id", "tool_use_id", "cache_control")}


#: Request arguments that only affect transport, never what the model decides.
_TRANSPORT_KWARGS = {
    "messages", "model", "tools", "system", "stream", "stream_options",
    "extra_headers", "extra_query", "extra_body", "timeout",
}


def _tools(tools: Any) -> dict[str, Any]:
    """Offered tools by name, with their description and a hash of the rest."""
    from evalcraft.core.tool_defs import normalize_tool_definitions

    return {
        t["name"]: {"description": t["description"], "schema": t["schema_hash"]}
        for t in normalize_tool_definitions(_plain(tools) or [])
    }


def _params(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Everything else the caller chose: temperature, tool_choice, max_tokens, ..."""
    return {
        k: _plain(v) for k, v in sorted(kwargs.items())
        if k not in _TRANSPORT_KWARGS and v is not None and not _is_sentinel(v)
    }


def _is_sentinel(value: Any) -> bool:
    # The SDKs' NOT_GIVEN / Omit markers mean "argument not passed".
    return type(value).__name__ in ("NotGiven", "Omit")


def openai_request(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Canonical form of a Chat Completions ``create(**kwargs)`` call.

    Tool-call ids are generated per run, so each call is named by position
    instead ("assistant message 2, call 1" is ``"2.1"``) and every tool result
    says which call it answers. Results answering the same turn are sorted, so
    the order they were appended in doesn't matter but which call they answer
    does.
    """
    refs: dict[str, str] = {}
    messages: list[dict[str, Any]] = []
    for position, msg in enumerate(_plain(kwargs.get("messages") or [])):
        if not isinstance(msg, dict):
            messages.append({"content": str(msg)})
            continue
        item: dict[str, Any] = {"role": msg.get("role", "")}
        content = _text(msg.get("content"))
        if item["role"] == "tool":
            content = _json_or_text(content)
            item["answers"] = refs.get(str(msg.get("tool_call_id")), "unknown call")
        if content not in ("", None):
            item["content"] = content
        calls = [c for c in (msg.get("tool_calls") or []) if isinstance(c, dict)]
        if calls:
            item["tool_calls"] = []
            for k, c in enumerate(calls):
                ref = f"{position}.{k}"
                refs[str(c.get("id"))] = ref
                fn = c.get("function") or {}
                item["tool_calls"].append({
                    "ref": ref, "name": fn.get("name"),
                    "arguments": _json_or_text(fn.get("arguments", "")),
                })
        messages.append(item)
    request: dict[str, Any] = {"model": kwargs.get("model"), "messages": _sort_results(messages)}
    tools = _tools(kwargs.get("tools"))
    if tools:
        request["tools"] = tools
    params = _params(kwargs)
    if params:
        request["params"] = params
    return request


def _sort_results(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort each run of consecutive tool messages by the call they answer."""
    out: list[dict[str, Any]] = []
    run: list[dict[str, Any]] = []
    for msg in messages + [{}]:
        if msg.get("role") == "tool":
            run.append(msg)
            continue
        out.extend(sorted(run, key=lambda m: str(m.get("answers"))))
        run = []
        if msg:
            out.append(msg)
    return out


def anthropic_request(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Canonical form of a Messages ``create(**kwargs)`` call.

    As for OpenAI, ``tool_use`` ids are replaced by their position and every
    ``tool_result`` names the call it answers; results in one message are
    sorted by that.
    """
    refs: dict[str, str] = {}
    messages = []
    for position, msg in enumerate(_plain(kwargs.get("messages") or [])):
        if not isinstance(msg, dict):
            messages.append({"content": str(msg)})
            continue
        content = msg.get("content")
        if isinstance(content, list):
            blocks = []
            for k, raw in enumerate(content):
                block = _block(raw)
                if isinstance(raw, dict) and raw.get("type") == "tool_use":
                    ref = f"{position}.{k}"
                    refs[str(raw.get("id"))] = ref
                    block["ref"] = ref
                elif isinstance(raw, dict) and raw.get("type") == "tool_result":
                    block["answers"] = refs.get(str(raw.get("tool_use_id")), "unknown call")
                    if raw.get("is_error"):
                        block["is_error"] = True
                blocks.append(block)
            results = sorted((b for b in blocks if isinstance(b, dict) and "answers" in b),
                             key=lambda b: str(b["answers"]))
            others = [b for b in blocks if not (isinstance(b, dict) and "answers" in b)]
            normalised: Any = others + results
            if all(isinstance(b, dict) and set(b) == {"text"} for b in normalised):
                normalised = "".join(b["text"] for b in normalised)
        else:
            normalised = _text(content)
        messages.append({"role": msg.get("role", ""), "content": normalised})
    request: dict[str, Any] = {"model": kwargs.get("model"), "messages": messages}
    system = kwargs.get("system")
    if system:
        request["system"] = _text(system)
    tools = _tools(kwargs.get("tools"))
    if tools:
        request["tools"] = tools
    params = _params(kwargs)
    if params:
        request["params"] = params
    return request


def response_payload(response: Any) -> dict[str, Any] | None:
    """The provider response as JSON-safe data, for exact playback later."""
    dump = getattr(response, "model_dump", None)
    if not callable(dump):
        return None
    try:
        data = dump(mode="json")
        json.dumps(data)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def recording_metadata(
    provider: str, kwargs: dict[str, Any], response: Any
) -> dict[str, Any]:
    """Span metadata that lets playback reproduce this call exactly."""
    meta: dict[str, Any] = {PROVIDER_KEY: provider}
    try:
        request = openai_request(kwargs) if provider == "openai" else anthropic_request(kwargs)
        # Round-trip so whatever lands in the cassette is plain JSON.
        meta[REQUEST_KEY] = json.loads(json.dumps(request, default=str))
    except Exception:
        pass
    payload = response_payload(response)
    if payload is not None:
        meta[RESPONSE_KEY] = payload
    return meta
