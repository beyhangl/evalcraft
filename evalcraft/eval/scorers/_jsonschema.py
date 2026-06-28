"""Pure-stdlib JSON-Schema validation for the structured-output scorers.

The default engine is a small, fully-implemented JSON-Schema *subset* validator
(no dependency). It validates the keywords agent-output schemas actually use and
**raises** on any keyword it does not implement — so a test can never get a false
PASS from a construct that was silently ignored. If the optional ``jsonschema``
package is installed, ``validate_schema`` transparently upgrades to full Draft
2020-12 coverage.
"""

from __future__ import annotations

import json
import re
from typing import Any

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
