"""Deterministic structured-output and tool-call-argument scorers.

Every scorer in this module is **offline, deterministic, and $0** — it inspects
only what the cassette already recorded (``cassette.output_text`` and each
``Span.tool_args``) and never calls a model or the network. They make the
"lock the *shape* of the output" promise concrete: agents increasingly emit
structured JSON (function calling, ``response_format`` / structured outputs),
and these assertions turn "did the agent return the right shape?" into a
byte-stable pytest check instead of an LLM-judge call.

    from evalcraft import (
        replay, assert_output_json, assert_output_json_schema,
        assert_tool_args_match_schema,
    )

    run = replay("tests/cassettes/weather.json")
    assert assert_output_json(run).passed
    assert assert_output_json_schema(run, {
        "type": "object",
        "required": ["city", "temp_c"],
        "properties": {"city": {"type": "string"}, "temp_c": {"type": "number"}},
    }).passed
    assert assert_tool_args_match_schema(run, "get_weather", {
        "type": "object",
        "required": ["city"],
        "properties": {"city": {"type": "string"}},
    }).passed

Schema validation uses a small, fully-implemented JSON-Schema **subset** by
default (pure stdlib, no new dependency). If the optional ``jsonschema`` package
is installed it is used transparently for full Draft 2020-12 coverage. The
subset validator never silently ignores a keyword it does not understand — it
raises a clear error pointing at ``pip install "evalcraft[schema]"`` — so a test
can never get a false PASS from an unsupported construct.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from evalcraft.core.models import (
    AgentRun,
    AssertionResult,
    Cassette,
)
from evalcraft.eval._utils import get_cassette as _get_cassette
from evalcraft.eval.scorers._jsonschema import validate_schema

__all__ = [
    "assert_match_groups",
    "assert_output_field",
    "assert_output_has_keys",
    "assert_output_json",
    "assert_output_json_schema",
    "assert_output_value_in",
    "assert_output_value_in_range",
    "assert_tool_args_match_schema",
    "validate_schema",
]

_UNSET = object()

# ──────────────────────────────────────────────
# JSON extraction
# ──────────────────────────────────────────────

def _strip_code_fence(text: str) -> str:
    """Strip a leading/trailing markdown code fence (``` or ```json)."""
    t = text.strip()
    if not t.startswith("```"):
        return t
    lines = t.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _first_json_block(text: str) -> str | None:
    """Return the first balanced ``{...}`` or ``[...]`` block in noisy prose."""
    start = next((i for i, ch in enumerate(text) if ch in "{["), None)
    if start is None:
        return None
    depth = 0
    in_str = False
    escaped = False
    for j in range(start, len(text)):
        ch = text[j]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
            if depth == 0:
                return text[start : j + 1]
    return None


def _extract_json(text: str, embedded: bool = False) -> tuple[bool, Any, str]:
    """Parse JSON from ``text``. Returns ``(ok, value, error)``.

    Tries the whole string (raw, then with a markdown fence stripped). When
    ``embedded`` is True and that fails, scans for the first balanced JSON
    block embedded in surrounding prose.
    """
    err = "empty output"
    for candidate in (text.strip(), _strip_code_fence(text)):
        if not candidate:
            continue
        try:
            return True, json.loads(candidate), ""
        except (json.JSONDecodeError, TypeError) as e:
            err = str(e)
    if embedded:
        block = _first_json_block(text)
        if block is not None:
            try:
                return True, json.loads(block), ""
            except json.JSONDecodeError as e:
                err = str(e)
    return False, None, err


# ──────────────────────────────────────────────
# Path resolution ("user.id", "items.0.name", "items[0].name")
# ──────────────────────────────────────────────

def _split_path(path: str) -> list[str]:
    return [seg for seg in path.replace("[", ".").replace("]", "").split(".") if seg != ""]


def _resolve_path(value: Any, path: str) -> tuple[bool, Any]:
    """Resolve a dotted/bracket path into nested objects/arrays."""
    cur = value
    for seg in _split_path(path):
        if isinstance(cur, dict):
            if seg not in cur:
                return False, None
            cur = cur[seg]
        elif isinstance(cur, list):
            try:
                idx = int(seg)
            except ValueError:
                return False, None
            if not (-len(cur) <= idx < len(cur)):
                return False, None
            cur = cur[idx]
        else:
            return False, None
    return True, cur


# ──────────────────────────────────────────────
# Schema loading (dict | path/file | pydantic model)
# ──────────────────────────────────────────────

def _load_schema(schema: Any) -> dict:
    """Coerce a dict, a JSON file path, or a pydantic model into a schema dict."""
    if isinstance(schema, dict):
        return schema
    if isinstance(schema, type):  # a pydantic BaseModel subclass
        model_schema = getattr(schema, "model_json_schema", None)
        if callable(model_schema):
            return model_schema()
        raise TypeError(
            f"Schema type {schema!r} is not a pydantic BaseModel subclass "
            "(no .model_json_schema())."
        )
    if isinstance(schema, Path):
        return json.loads(schema.read_text())
    if isinstance(schema, str):
        # An inline JSON document starts with '{' or '['; anything else is a path.
        if schema.lstrip()[:1] in "{[":
            return json.loads(schema)
        return json.loads(Path(schema).read_text())
    raise TypeError(
        f"Unsupported schema type {type(schema).__name__}: pass a dict, a path to "
        "a .json file, an inline JSON string, or a pydantic model class."
    )


# ──────────────────────────────────────────────
# Output-shape scorers
# ──────────────────────────────────────────────

def _parse_or_fail(
    cassette: Cassette | AgentRun, name: str, expected: Any, embedded: bool
) -> tuple[Any, AssertionResult | None]:
    """Parse the run's output as JSON. Returns ``(value, None)`` on success, or
    ``(None, failing_AssertionResult)`` when the output is not valid JSON."""
    c = _get_cassette(cassette)
    ok, value, err = _extract_json(c.output_text, embedded=embedded)
    if ok:
        return value, None
    fail = AssertionResult(
        name=name, passed=False, expected=expected,
        actual=c.output_text[:200], message=f"Output is not valid JSON: {err}",
    )
    return None, fail


def assert_output_json(
    cassette: Cassette | AgentRun,
    embedded: bool = False,
) -> AssertionResult:
    """Assert the agent output is valid (parseable) JSON.

    Args:
        cassette: The cassette or agent run to check.
        embedded: If True, also accept JSON embedded in surrounding prose
            (the first balanced ``{...}`` / ``[...]`` block is parsed).
    """
    c = _get_cassette(cassette)
    ok, _value, err = _extract_json(c.output_text, embedded=embedded)
    return AssertionResult(
        name="assert_output_json",
        passed=ok,
        expected="valid JSON",
        actual=c.output_text[:200],
        message="" if ok else f"Output is not valid JSON: {err}",
    )


def assert_output_json_schema(
    cassette: Cassette | AgentRun,
    schema: Any,
    embedded: bool = False,
    engine: str = "auto",
) -> AssertionResult:
    """Assert the agent output is JSON conforming to a JSON Schema.

    Args:
        cassette: The cassette or agent run to check.
        schema: A schema as a dict, a path to a ``.json`` file, an inline JSON
            string, or a pydantic ``BaseModel`` subclass.
        embedded: Accept JSON embedded in prose (see ``assert_output_json``).
        engine: ``"auto"`` / ``"builtin"`` / ``"jsonschema"``.
    """
    value, fail = _parse_or_fail(
        cassette, "assert_output_json_schema", "JSON matching schema", embedded
    )
    if fail:
        return fail
    schema_dict = _load_schema(schema)
    _used, errors = validate_schema(value, schema_dict, engine=engine)
    return AssertionResult(
        name="assert_output_json_schema",
        passed=not errors,
        expected="JSON matching schema",
        actual=value,
        message="" if not errors else "Schema violations: " + "; ".join(errors),
    )


def assert_output_has_keys(
    cassette: Cassette | AgentRun,
    keys: list[str],
    path: str | None = None,
    embedded: bool = False,
) -> AssertionResult:
    """Assert the JSON output contains every key/path in ``keys``.

    Each entry may be a top-level key or a dotted/bracket path. ``path`` is an
    optional base path to descend into before checking the keys.
    """
    value, fail = _parse_or_fail(cassette, "assert_output_has_keys", keys, embedded)
    if fail:
        return fail
    root = value
    if path is not None:
        found, root = _resolve_path(value, path)
        if not found:
            return AssertionResult(
                name="assert_output_has_keys", passed=False, expected=keys, actual=value,
                message=f"Base path '{path}' not found in output",
            )
    missing = [k for k in keys if not _resolve_path(root, k)[0]]
    return AssertionResult(
        name="assert_output_has_keys",
        passed=not missing,
        expected=keys,
        actual=list(root.keys()) if isinstance(root, dict) else root,
        message="" if not missing else f"Missing keys: {missing}",
    )


def assert_output_field(
    cassette: Cassette | AgentRun,
    path: str,
    equals: Any = _UNSET,
    exists: bool = False,
    embedded: bool = False,
) -> AssertionResult:
    """Assert a field at ``path`` exists (and optionally equals a value).

    With ``equals`` set, the resolved value must equal it. Otherwise the field
    just has to be present.
    """
    expected = equals if equals is not _UNSET else "present"
    value, fail = _parse_or_fail(cassette, f"assert_output_field({path})", expected, embedded)
    if fail:
        return fail
    found, resolved = _resolve_path(value, path)
    if not found:
        return AssertionResult(
            name=f"assert_output_field({path})", passed=False,
            expected=expected, actual=None,
            message=f"Field '{path}' not found in output",
        )
    if equals is not _UNSET and resolved != equals:
        return AssertionResult(
            name=f"assert_output_field({path})", passed=False, expected=equals,
            actual=resolved, message=f"Field '{path}' is {resolved!r}, expected {equals!r}",
        )
    return AssertionResult(
        name=f"assert_output_field({path})", passed=True,
        expected=expected, actual=resolved,
    )


def assert_output_value_in(
    cassette: Cassette | AgentRun,
    path: str,
    allowed: list,
    embedded: bool = False,
) -> AssertionResult:
    """Assert the value at ``path`` is one of ``allowed`` (enum membership)."""
    value, fail = _parse_or_fail(cassette, f"assert_output_value_in({path})", allowed, embedded)
    if fail:
        return fail
    found, resolved = _resolve_path(value, path)
    if not found:
        return AssertionResult(
            name=f"assert_output_value_in({path})", passed=False, expected=allowed,
            actual=None, message=f"Field '{path}' not found in output",
        )
    passed = resolved in allowed
    return AssertionResult(
        name=f"assert_output_value_in({path})", passed=passed, expected=allowed,
        actual=resolved,
        message="" if passed else f"Field '{path}' is {resolved!r}, not one of {allowed!r}",
    )


def assert_output_value_in_range(
    cassette: Cassette | AgentRun,
    path: str,
    minimum: float | None = None,
    maximum: float | None = None,
    exclusive: bool = False,
    embedded: bool = False,
) -> AssertionResult:
    """Assert the numeric value at ``path`` falls within ``[minimum, maximum]``.

    With ``exclusive=True`` the bounds are exclusive.
    """
    value, fail = _parse_or_fail(
        cassette, f"assert_output_value_in_range({path})", (minimum, maximum), embedded
    )
    if fail:
        return fail
    found, resolved = _resolve_path(value, path)
    if not found:
        return AssertionResult(
            name=f"assert_output_value_in_range({path})", passed=False,
            expected=(minimum, maximum), actual=None,
            message=f"Field '{path}' not found in output",
        )
    if isinstance(resolved, bool) or not isinstance(resolved, (int, float)):
        return AssertionResult(
            name=f"assert_output_value_in_range({path})", passed=False,
            expected=(minimum, maximum), actual=resolved,
            message=f"Field '{path}' is not a number (got {resolved!r})",
        )
    failures = []
    if minimum is not None:
        if exclusive and not resolved > minimum:
            failures.append(f"{resolved} <= {minimum}")
        elif not exclusive and not resolved >= minimum:
            failures.append(f"{resolved} < {minimum}")
    if maximum is not None:
        if exclusive and not resolved < maximum:
            failures.append(f"{resolved} >= {maximum}")
        elif not exclusive and not resolved <= maximum:
            failures.append(f"{resolved} > {maximum}")
    return AssertionResult(
        name=f"assert_output_value_in_range({path})", passed=not failures,
        expected=(minimum, maximum), actual=resolved,
        message="" if not failures else f"Field '{path}' out of range: " + ", ".join(failures),
    )


def assert_match_groups(
    cassette: Cassette | AgentRun,
    pattern: str,
    expected_groups: tuple | list | None = None,
    expected_named: dict | None = None,
) -> AssertionResult:
    """Assert the output matches ``pattern`` and (optionally) its capture groups.

    Fills the regex capture-group gap left by ``assert_output_matches``:
    compares ``re.search(...).groups()`` against ``expected_groups`` and
    ``.groupdict()`` against ``expected_named``.
    """
    c = _get_cassette(cassette)
    match = re.search(pattern, c.output_text)
    if match is None:
        return AssertionResult(
            name=f"assert_match_groups({pattern!r})", passed=False, expected=pattern,
            actual=c.output_text[:200], message=f"Output does not match pattern {pattern!r}",
        )
    if expected_groups is not None and tuple(match.groups()) != tuple(expected_groups):
        return AssertionResult(
            name=f"assert_match_groups({pattern!r})", passed=False,
            expected=tuple(expected_groups), actual=match.groups(),
            message=f"Capture groups {match.groups()} != expected {tuple(expected_groups)}",
        )
    if expected_named is not None:
        gd = match.groupdict()
        mismatched = {k: gd.get(k) for k, v in expected_named.items() if gd.get(k) != v}
        if mismatched:
            return AssertionResult(
                name=f"assert_match_groups({pattern!r})", passed=False,
                expected=expected_named, actual=gd,
                message=f"Named groups mismatch: {mismatched}",
            )
    return AssertionResult(
        name=f"assert_match_groups({pattern!r})", passed=True, expected=pattern,
        actual=match.groupdict() or match.groups(),
    )


# ──────────────────────────────────────────────
# Tool-call-argument shape scorer (agent-native)
# ──────────────────────────────────────────────

def assert_tool_args_match_schema(
    cassette: Cassette | AgentRun,
    tool_name: str,
    schema: Any,
    which: str = "all",
    engine: str = "auto",
) -> AssertionResult:
    """Assert recorded calls to ``tool_name`` have args matching a JSON Schema.

    Validates each recorded ``tool_args`` dict deterministically — the same
    "is this tool call shaped correctly?" check other tools spend a live LLM on.

    Args:
        cassette: The cassette or agent run to check.
        tool_name: Name of the tool whose arguments to validate.
        schema: dict / ``.json`` path / inline JSON / pydantic model.
        which: ``"all"`` (every call must conform) or ``"any"`` (≥1 must).
        engine: ``"auto"`` / ``"builtin"`` / ``"jsonschema"``.
    """
    if which not in ("all", "any"):
        raise ValueError(f"which must be 'all' or 'any', got {which!r}")
    c = _get_cassette(cassette)
    calls = [s for s in c.get_tool_calls() if s.tool_name == tool_name]
    name = f"assert_tool_args_match_schema({tool_name})"
    if not calls:
        return AssertionResult(
            name=name, passed=False, expected=tool_name, actual=c.get_tool_sequence(),
            message=f"Tool '{tool_name}' was never called. Called: {c.get_tool_sequence()}",
        )
    schema_dict = _load_schema(schema)
    results = []
    for call in calls:
        _used, errors = validate_schema(call.tool_args or {}, schema_dict, engine=engine)
        results.append((call.tool_args, errors))

    conforming = sum(1 for _args, errors in results if not errors)
    if which == "all":
        passed = conforming == len(results)
    else:
        passed = conforming >= 1

    if passed:
        return AssertionResult(name=name, passed=True, expected="args match schema",
                               actual=f"{conforming}/{len(results)} calls conform")
    first_bad = next((r for r in results if r[1]), results[0])
    return AssertionResult(
        name=name, passed=False, expected="args match schema", actual=first_bad[0],
        message=(
            f"{conforming}/{len(results)} call(s) to '{tool_name}' conform "
            f"(which='{which}'). First violation: " + "; ".join(first_bad[1])
        ),
    )
