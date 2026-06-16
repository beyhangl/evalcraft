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
# Built-in JSON-Schema subset validator (pure stdlib)
# ──────────────────────────────────────────────

# Keywords the built-in validator enforces.
_SUPPORTED = frozenset({
    "type", "enum", "const", "properties", "required", "additionalProperties",
    "items", "minItems", "maxItems", "uniqueItems", "minLength", "maxLength",
    "pattern", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
    "multipleOf", "anyOf", "allOf", "oneOf", "$ref",
})
# Annotation/metadata keywords that are ignored (never affect validation).
_IGNORED = frozenset({
    "title", "description", "default", "examples", "$schema", "$id", "$comment",
    "$defs", "definitions", "readOnly", "writeOnly", "deprecated", "format",
})


def _is_type(value: Any, t: str) -> bool:
    if t == "object":
        return isinstance(value, dict)
    if t == "array":
        return isinstance(value, list)
    if t == "string":
        return isinstance(value, str)
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "boolean":
        return isinstance(value, bool)
    if t == "null":
        return value is None
    raise ValueError(f"Unknown JSON-Schema type {t!r}")


def _resolve_ref(root: dict, ref: str) -> dict:
    if not ref.startswith("#/"):
        raise ValueError(
            f"The built-in schema validator only supports local '#/...' $refs (got {ref!r}). "
            "Install the full engine with: pip install \"evalcraft[schema]\""
        )
    node: Any = root
    for raw in ref[2:].split("/"):
        key = raw.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or key not in node:
            raise ValueError(f"Unresolvable $ref {ref!r}: missing segment {key!r}")
        node = node[key]
    if not isinstance(node, dict):
        raise ValueError(f"$ref {ref!r} does not point at a schema object")
    return node


def _validate_subset(value: Any, schema: dict, root: dict, path: str) -> list[str]:
    """Validate ``value`` against ``schema``; return a list of error strings."""
    if "$ref" in schema:
        schema = _resolve_ref(root, schema["$ref"])

    unknown = set(schema) - _SUPPORTED - _IGNORED
    if unknown:
        raise ValueError(
            f"The built-in schema validator does not support keyword(s) "
            f"{sorted(unknown)} at {path}. Install full Draft 2020-12 support with: "
            'pip install "evalcraft[schema]"'
        )

    errors: list[str] = []

    for kw in ("allOf", "anyOf", "oneOf"):
        if kw not in schema:
            continue
        subs = schema[kw]
        results = [_validate_subset(value, s, root, path) for s in subs]
        ok = sum(1 for r in results if not r)
        if kw == "allOf" and ok != len(subs):
            errors.append(f"{path}: does not match all of the required schemas")
        elif kw == "anyOf" and ok == 0:
            errors.append(f"{path}: does not match any of the allowed schemas")
        elif kw == "oneOf" and ok != 1:
            errors.append(f"{path}: must match exactly one schema (matched {ok})")

    if "type" in schema:
        types = schema["type"]
        types = [types] if isinstance(types, str) else types
        if not any(_is_type(value, t) for t in types):
            errors.append(f"{path}: expected type {schema['type']}, got {_typename(value)}")
            return errors  # further checks assume the right type

    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: expected const {schema['const']!r}, got {value!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} is not one of {schema['enum']!r}")

    if isinstance(value, str):
        errors += _validate_string(value, schema, path)
    if isinstance(value, bool):
        pass  # booleans are not numbers
    elif isinstance(value, (int, float)):
        errors += _validate_number(value, schema, path)
    if isinstance(value, list):
        errors += _validate_array(value, schema, root, path)
    if isinstance(value, dict):
        errors += _validate_object(value, schema, root, path)

    return errors


def _validate_string(value: str, schema: dict, path: str) -> list[str]:
    errors = []
    if "minLength" in schema and len(value) < schema["minLength"]:
        errors.append(f"{path}: string shorter than minLength {schema['minLength']}")
    if "maxLength" in schema and len(value) > schema["maxLength"]:
        errors.append(f"{path}: string longer than maxLength {schema['maxLength']}")
    if "pattern" in schema and re.search(schema["pattern"], value) is None:
        errors.append(f"{path}: {value!r} does not match pattern {schema['pattern']!r}")
    return errors


def _validate_number(value: float, schema: dict, path: str) -> list[str]:
    errors = []
    if "minimum" in schema and value < schema["minimum"]:
        errors.append(f"{path}: {value} < minimum {schema['minimum']}")
    if "maximum" in schema and value > schema["maximum"]:
        errors.append(f"{path}: {value} > maximum {schema['maximum']}")
    if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
        errors.append(f"{path}: {value} <= exclusiveMinimum {schema['exclusiveMinimum']}")
    if "exclusiveMaximum" in schema and value >= schema["exclusiveMaximum"]:
        errors.append(f"{path}: {value} >= exclusiveMaximum {schema['exclusiveMaximum']}")
    if "multipleOf" in schema and schema["multipleOf"]:
        q = value / schema["multipleOf"]
        if abs(q - round(q)) > 1e-9:
            errors.append(f"{path}: {value} is not a multiple of {schema['multipleOf']}")
    return errors


def _validate_array(value: list, schema: dict, root: dict, path: str) -> list[str]:
    errors = []
    if "minItems" in schema and len(value) < schema["minItems"]:
        errors.append(f"{path}: array shorter than minItems {schema['minItems']}")
    if "maxItems" in schema and len(value) > schema["maxItems"]:
        errors.append(f"{path}: array longer than maxItems {schema['maxItems']}")
    if schema.get("uniqueItems"):
        seen = [json.dumps(v, sort_keys=True, default=str) for v in value]
        if len(set(seen)) != len(seen):
            errors.append(f"{path}: array items are not unique")
    if "items" in schema and isinstance(schema["items"], dict):
        for i, item in enumerate(value):
            errors += _validate_subset(item, schema["items"], root, f"{path}[{i}]")
    return errors


def _validate_object(value: dict, schema: dict, root: dict, path: str) -> list[str]:
    errors = []
    props = schema.get("properties", {})
    for key in schema.get("required", []):
        if key not in value:
            errors.append(f"{path}: missing required key {key!r}")
    for key, sub in props.items():
        if key in value:
            errors += _validate_subset(value[key], sub, root, f"{path}.{key}")
    ap = schema.get("additionalProperties", True)
    if ap is not True:
        extra = [k for k in value if k not in props]
        if ap is False and extra:
            errors.append(f"{path}: unexpected keys {extra} (additionalProperties is false)")
        elif isinstance(ap, dict):
            for k in extra:
                errors += _validate_subset(value[k], ap, root, f"{path}.{k}")
    return errors


def _typename(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _jsonschema_available() -> bool:
    try:
        import jsonschema  # noqa: F401
        return True
    except ImportError:
        return False


def validate_schema(value: Any, schema: dict, engine: str = "auto") -> tuple[str, list[str]]:
    """Validate ``value`` against ``schema``. Returns ``(engine_used, errors)``.

    ``engine``: ``"auto"`` (use ``jsonschema`` if installed, else the built-in
    subset), ``"builtin"`` (force the stdlib subset), or ``"jsonschema"`` (force
    the optional full engine, raising if it is not installed).
    """
    if engine not in ("auto", "builtin", "jsonschema"):
        raise ValueError(f"engine must be 'auto', 'builtin', or 'jsonschema', got {engine!r}")

    use_jsonschema = engine == "jsonschema" or (engine == "auto" and _jsonschema_available())
    if use_jsonschema:
        import jsonschema
        validator = jsonschema.Draft202012Validator(schema)
        errors = [
            f"${''.join(f'.{p}' if isinstance(p, str) else f'[{p}]' for p in e.absolute_path)}"
            f": {e.message}"
            for e in sorted(validator.iter_errors(value), key=lambda e: list(e.absolute_path))
        ]
        return "jsonschema", errors
    return "builtin", _validate_subset(value, schema, schema, "$")


# ──────────────────────────────────────────────
# Output-shape scorers
# ──────────────────────────────────────────────

def _get_cassette(obj: Cassette | AgentRun) -> Cassette:
    if isinstance(obj, AgentRun):
        return obj.cassette
    return obj


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
    c = _get_cassette(cassette)
    ok, value, err = _extract_json(c.output_text, embedded=embedded)
    if not ok:
        return AssertionResult(
            name="assert_output_json_schema",
            passed=False,
            expected="JSON matching schema",
            actual=c.output_text[:200],
            message=f"Output is not valid JSON: {err}",
        )
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
    c = _get_cassette(cassette)
    ok, value, err = _extract_json(c.output_text, embedded=embedded)
    if not ok:
        return AssertionResult(
            name="assert_output_has_keys",
            passed=False, expected=keys, actual=c.output_text[:200],
            message=f"Output is not valid JSON: {err}",
        )
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
    c = _get_cassette(cassette)
    ok, value, err = _extract_json(c.output_text, embedded=embedded)
    if not ok:
        return AssertionResult(
            name=f"assert_output_field({path})", passed=False,
            expected=equals if equals is not _UNSET else "present",
            actual=c.output_text[:200], message=f"Output is not valid JSON: {err}",
        )
    found, resolved = _resolve_path(value, path)
    if not found:
        return AssertionResult(
            name=f"assert_output_field({path})", passed=False,
            expected=equals if equals is not _UNSET else "present", actual=None,
            message=f"Field '{path}' not found in output",
        )
    if equals is not _UNSET and resolved != equals:
        return AssertionResult(
            name=f"assert_output_field({path})", passed=False, expected=equals,
            actual=resolved, message=f"Field '{path}' is {resolved!r}, expected {equals!r}",
        )
    return AssertionResult(
        name=f"assert_output_field({path})", passed=True,
        expected=equals if equals is not _UNSET else "present", actual=resolved,
    )


def assert_output_value_in(
    cassette: Cassette | AgentRun,
    path: str,
    allowed: list,
    embedded: bool = False,
) -> AssertionResult:
    """Assert the value at ``path`` is one of ``allowed`` (enum membership)."""
    c = _get_cassette(cassette)
    ok, value, err = _extract_json(c.output_text, embedded=embedded)
    if not ok:
        return AssertionResult(
            name=f"assert_output_value_in({path})", passed=False, expected=allowed,
            actual=c.output_text[:200], message=f"Output is not valid JSON: {err}",
        )
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
    c = _get_cassette(cassette)
    ok, value, err = _extract_json(c.output_text, embedded=embedded)
    if not ok:
        return AssertionResult(
            name=f"assert_output_value_in_range({path})", passed=False,
            expected=(minimum, maximum), actual=c.output_text[:200],
            message=f"Output is not valid JSON: {err}",
        )
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
            message=f"Field '{path}' is {_typename(resolved)}, not a number",
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
