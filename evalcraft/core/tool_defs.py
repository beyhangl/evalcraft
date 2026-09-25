"""Tool definitions as the model saw them.

The model picks a tool from its name and description. When the parameters of a
tool change but the description still documents the old ones, the model keeps
calling it the old way and the agent breaks quietly. A recording that remembers
the definitions it was captured with can be diffed against the definitions the
code ships today (``evalcraft check-stale --tools``).

Each definition is normalised to ``{"name", "description", "schema_hash"}``.
``schema_hash`` covers everything in the definition except its name and
description (the parameter schema, ``strict``, a hosted tool's version, its
options). Only the hash is stored, so cassettes stay small.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

TOOL_DEFINITIONS_METADATA_KEY = "tool_definitions"


_SCHEMA_KEYS = ("parameters", "input_schema", "inputSchema")
_IGNORED_KEYS = {"name", "description", "cache_control"}


def _schema_hash(data: dict[str, Any]) -> str:
    rest = {k: v for k, v in data.items() if k not in _IGNORED_KEYS}
    # The three formats name the parameter schema differently; hash it under one key.
    for key in _SCHEMA_KEYS:
        if key in rest:
            rest["parameters"] = rest.pop(key)
    if rest.get("type") == "function":
        del rest["type"]
    if not rest:
        return ""
    try:
        basis = json.dumps(rest, sort_keys=True, default=str)
    except (TypeError, ValueError):
        basis = repr(rest)
    return hashlib.sha256(basis.encode()).hexdigest()[:16]


def _as_dict(tool: Any) -> dict[str, Any] | None:
    if isinstance(tool, dict):
        return tool
    dump = getattr(tool, "model_dump", None)
    if callable(dump):
        try:
            data = dump()
        except Exception:
            return None
        return data if isinstance(data, dict) else None
    return None


def normalize_tool_definition(tool: Any) -> dict[str, str] | None:
    """Normalise one OpenAI or Anthropic tool definition, or return ``None``.

    Accepted shapes:

    - OpenAI Chat Completions:
      ``{"type": "function", "function": {"name", "description", "parameters"}}``
    - OpenAI Responses / flat: ``{"type": "function", "name", "description", "parameters"}``
    - Anthropic: ``{"name", "description", "input_schema"}``
    - MCP ``tools/list`` entries: ``{"name", "description", "inputSchema"}``
    - provider-hosted tools such as ``{"type": "web_search_20250305", "name": "web_search"}``
    """
    data = _as_dict(tool)
    if data is None:
        return None
    fn = data.get("function")
    if isinstance(fn, dict):
        data = fn
    name = data.get("name")
    if not isinstance(name, str) or not name:
        return None
    return {
        "name": name,
        "description": str(data.get("description") or ""),
        "schema_hash": _schema_hash(data),
    }


def normalize_tool_definitions(tools: Any) -> list[dict[str, str]]:
    """Normalise a list of tool definitions, sorted by name, last duplicate wins."""
    if not isinstance(tools, (list, tuple)):
        return []
    by_name: dict[str, dict[str, str]] = {}
    for tool in tools:
        norm = normalize_tool_definition(tool)
        if norm is not None:
            by_name[norm["name"]] = norm
    return [by_name[n] for n in sorted(by_name)]


def load_tool_definitions(path: str) -> list[dict[str, str]]:
    """Read the tool definitions your code ships today from a JSON file.

    The file holds a list of tool definitions in any accepted shape, or an
    object with a ``tools`` list (a saved request body works as is).
    """
    with open(path) as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        data = data.get("tools", [])
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a list of tool definitions or an object with 'tools'")
    return normalize_tool_definitions(data)


def diff_tool_definitions(
    recorded: list[dict[str, str]], current: list[dict[str, str]]
) -> list[tuple[str, str, str]]:
    """Compare two normalised definition lists.

    Returns ``(kind, tool_name, message)`` tuples where ``kind`` is one of
    ``added``, ``removed``, ``schema_only`` (parameters changed but the
    description did not), ``schema_and_description`` or ``description_only``.
    """
    old = {t["name"]: t for t in recorded if t.get("name")}
    new = {t["name"]: t for t in current if t.get("name")}
    changes: list[tuple[str, str, str]] = []
    for name in sorted(old.keys() - new.keys()):
        changes.append(("removed", name, f"tool {name!r} was recorded but is no longer defined"))
    for name in sorted(new.keys() - old.keys()):
        changes.append((
            "added", name, f"tool {name!r} is defined now but was not offered in the recording",
        ))
    for name in sorted(old.keys() & new.keys()):
        a, b = old[name], new[name]
        schema_changed = a.get("schema_hash", "") != b.get("schema_hash", "")
        desc_changed = a.get("description", "") != b.get("description", "")
        if schema_changed and not desc_changed:
            changes.append((
                "schema_only", name,
                f"tool {name!r} parameters changed but its description did not; "
                "the model may keep calling it the old way",
            ))
        elif schema_changed:
            changes.append((
                "schema_and_description", name,
                f"tool {name!r} parameters and description changed",
            ))
        elif desc_changed:
            changes.append(("description_only", name, f"tool {name!r} description changed"))
    return changes


def request_metadata(kwargs: dict[str, Any], served_model: str | None) -> dict[str, Any]:
    """Span metadata describing what a provider request asked for.

    Adds the normalised ``tool_definitions`` when the request offered tools,
    and ``requested_model`` when the id the caller asked for differs from the
    model the provider served (a floating alias such as ``gpt-4o`` resolving to
    a dated snapshot).
    """
    meta: dict[str, Any] = {}
    # Never let bookkeeping fail a provider call that already succeeded.
    try:
        tools = normalize_tool_definitions(kwargs.get("tools"))
    except Exception:
        tools = []
    if tools:
        meta[TOOL_DEFINITIONS_METADATA_KEY] = tools
    requested = kwargs.get("model")
    if isinstance(requested, str) and requested and served_model and requested != served_model:
        meta["requested_model"] = requested
    return meta
