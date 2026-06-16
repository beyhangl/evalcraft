"""Tests for deterministic structured-output / tool-arg shape scorers.

Every scorer here is offline, deterministic, and $0 — it inspects only the
already-recorded cassette (output_text + Span.tool_args) and never calls a
model. Tests cover both schema engines (the pure-stdlib built-in subset and the
optional jsonschema upgrade) and prove the built-in path never false-passes.
"""

import json

import pytest

from evalcraft import (
    assert_match_groups,
    assert_output_field,
    assert_output_has_keys,
    assert_output_json,
    assert_output_json_schema,
    assert_output_value_in,
    assert_output_value_in_range,
    assert_tool_args_match_schema,
)
from evalcraft.core.models import AgentRun, Cassette, Span, SpanKind
from evalcraft.eval.scorers.structured import (
    _extract_json,
    _resolve_path,
    validate_schema,
)


def _out(text: str) -> Cassette:
    c = Cassette(name="t", agent_name="a")
    c.output_text = text
    return c


def _tool_cassette(tool_name: str, args_list: list[dict]) -> Cassette:
    c = Cassette(name="t", agent_name="a")
    for args in args_list:
        c.add_span(Span(kind=SpanKind.TOOL_CALL, name=f"tool:{tool_name}",
                        tool_name=tool_name, tool_args=args, tool_result={"ok": True}))
    c.output_text = "done"
    return c


# ── JSON extraction ──────────────────────────────────────────────────────────

class TestExtractAndJson:
    def test_valid_json_object(self):
        assert assert_output_json(_out('{"a": 1}')).passed

    def test_invalid_json_fails(self):
        r = assert_output_json(_out("not json {"))
        assert r.passed is False
        assert "not valid JSON" in r.message

    def test_markdown_fenced_json(self):
        assert assert_output_json(_out('```json\n{"a": 1}\n```')).passed

    def test_embedded_json_in_prose(self):
        text = 'Here you go: {"a": 1, "b": [2, 3]} — hope that helps!'
        assert assert_output_json(_out(text)).passed is False  # strict by default
        assert assert_output_json(_out(text), embedded=True).passed

    def test_embedded_balances_nested_braces(self):
        ok, value, _ = _extract_json('noise {"x": {"y": 1}} tail', embedded=True)
        assert ok and value == {"x": {"y": 1}}

    def test_json_array(self):
        assert assert_output_json(_out("[1, 2, 3]")).passed


# ── path resolution ──────────────────────────────────────────────────────────

class TestResolvePath:
    @pytest.mark.parametrize("path,expected", [
        ("a", 1),
        ("b.c", 2),
        ("b.items.1", "y"),
        ("b.items[0]", "x"),
    ])
    def test_resolves(self, path, expected):
        value = {"a": 1, "b": {"c": 2, "items": ["x", "y"]}}
        found, got = _resolve_path(value, path)
        assert found and got == expected

    def test_missing_path(self):
        assert _resolve_path({"a": 1}, "a.b.c") == (False, None)

    def test_index_out_of_range(self):
        assert _resolve_path({"xs": [1]}, "xs.5")[0] is False


# ── schema validation (both engines) ─────────────────────────────────────────

SCHEMA = {
    "type": "object",
    "required": ["city", "temp_c", "status"],
    "properties": {
        "city": {"type": "string", "minLength": 1},
        "temp_c": {"type": "number", "minimum": -90, "maximum": 60},
        "status": {"enum": ["ok", "error"]},
        "tags": {"type": "array", "items": {"type": "string"}, "minItems": 1},
    },
}
GOOD = '{"city": "Paris", "temp_c": 18.5, "status": "ok", "tags": ["eu"]}'


class TestSchema:
    @pytest.mark.parametrize("engine", ["builtin", "auto"])
    def test_conforming_passes(self, engine):
        assert assert_output_json_schema(_out(GOOD), SCHEMA, engine=engine).passed

    def test_missing_required_key(self):
        r = assert_output_json_schema(_out('{"city": "Paris"}'), SCHEMA, engine="builtin")
        assert r.passed is False
        assert "missing required key" in r.message

    def test_wrong_type(self):
        bad = '{"city": "Paris", "temp_c": "warm", "status": "ok"}'
        r = assert_output_json_schema(_out(bad), SCHEMA, engine="builtin")
        assert r.passed is False
        assert "expected type" in r.message

    def test_enum_violation(self):
        bad = '{"city": "Paris", "temp_c": 18, "status": "broken"}'
        r = assert_output_json_schema(_out(bad), SCHEMA, engine="builtin")
        assert r.passed is False and "not one of" in r.message

    def test_range_violation(self):
        bad = '{"city": "Paris", "temp_c": 999, "status": "ok"}'
        r = assert_output_json_schema(_out(bad), SCHEMA, engine="builtin")
        assert r.passed is False and "maximum" in r.message

    def test_pattern_violation(self):
        schema = {"type": "object",
                  "properties": {"id": {"type": "string", "pattern": "^[A-Z]{3}$"}}}
        r = assert_output_json_schema(_out('{"id": "abc"}'), schema, engine="builtin")
        assert r.passed is False and "pattern" in r.message

    def test_array_items_and_min_items(self):
        bad = '{"city": "Paris", "temp_c": 18, "status": "ok", "tags": []}'
        r = assert_output_json_schema(_out(bad), SCHEMA, engine="builtin")
        assert r.passed is False and "minItems" in r.message

    def test_output_not_json(self):
        r = assert_output_json_schema(_out("hello"), SCHEMA)
        assert r.passed is False and "not valid JSON" in r.message

    def test_additional_properties_false(self):
        schema = {"type": "object", "properties": {"a": {"type": "integer"}},
                  "additionalProperties": False}
        assert assert_output_json_schema(_out('{"a": 1}'), schema, engine="builtin").passed
        r = assert_output_json_schema(_out('{"a": 1, "b": 2}'), schema, engine="builtin")
        assert r.passed is False and "additionalProperties" in r.message

    def test_anyof(self):
        schema = {"anyOf": [{"type": "string"}, {"type": "integer"}]}
        assert assert_output_json_schema(_out('"hi"'), schema, engine="builtin").passed
        assert assert_output_json_schema(_out("42"), schema, engine="builtin").passed
        assert assert_output_json_schema(_out("1.5"), schema, engine="builtin").passed is False


class TestSchemaSources:
    def test_dict_path_and_inline_agree(self, tmp_path):
        from_dict = assert_output_json_schema(_out(GOOD), SCHEMA, engine="builtin")
        p = tmp_path / "schema.json"
        p.write_text(json.dumps(SCHEMA))
        from_file = assert_output_json_schema(_out(GOOD), str(p), engine="builtin")
        from_inline = assert_output_json_schema(_out(GOOD), json.dumps(SCHEMA), engine="builtin")
        assert from_dict.passed and from_file.passed and from_inline.passed

    def test_pydantic_model_schema(self):
        from pydantic import BaseModel

        class Weather(BaseModel):
            city: str
            temp_c: float

        assert assert_output_json_schema(
            _out('{"city": "Paris", "temp_c": 18.0}'), Weather, engine="builtin"
        ).passed
        r = assert_output_json_schema(_out('{"city": "Paris"}'), Weather, engine="builtin")
        assert r.passed is False  # temp_c required by the model

    def test_pydantic_nested_model_uses_ref(self):
        from pydantic import BaseModel

        class Geo(BaseModel):
            lat: float
            lon: float

        class Place(BaseModel):
            name: str
            geo: Geo

        good = '{"name": "Paris", "geo": {"lat": 48.8, "lon": 2.3}}'
        # builtin must resolve the pydantic-emitted $ref/$defs with no jsonschema
        assert assert_output_json_schema(_out(good), Place, engine="builtin").passed
        bad = '{"name": "Paris", "geo": {"lat": 48.8}}'
        assert assert_output_json_schema(_out(bad), Place, engine="builtin").passed is False


class TestEngineSafety:
    def test_builtin_raises_on_unsupported_keyword(self):
        # No silent false-pass: an unimplemented keyword errors loudly.
        with pytest.raises(ValueError, match="does not support keyword"):
            validate_schema({"a": 1}, {"type": "object", "patternProperties": {"^x": {}}},
                            engine="builtin")

    def test_invalid_engine_name(self):
        with pytest.raises(ValueError, match="engine must be"):
            validate_schema({}, {}, engine="bogus")

    def test_builtin_engine_reported(self):
        used, errors = validate_schema(json.loads(GOOD), SCHEMA, engine="builtin")
        assert used == "builtin" and errors == []

    def test_integer_not_bool(self):
        # booleans must not satisfy integer/number
        used, errors = validate_schema(True, {"type": "integer"}, engine="builtin")
        assert errors  # True is not an integer for schema purposes


# ── field / keys / enum / range scorers ──────────────────────────────────────

class TestFieldScorers:
    def test_has_keys(self):
        c = _out('{"a": 1, "b": {"c": 2}}')
        assert assert_output_has_keys(c, ["a", "b.c"]).passed
        r = assert_output_has_keys(c, ["a", "z"])
        assert r.passed is False and "z" in r.message

    def test_has_keys_with_base_path(self):
        c = _out('{"user": {"id": 1, "name": "x"}}')
        assert assert_output_has_keys(c, ["id", "name"], path="user").passed

    def test_field_equals(self):
        c = _out('{"city": "Paris", "n": 3}')
        assert assert_output_field(c, "city", equals="Paris").passed
        r = assert_output_field(c, "city", equals="London")
        assert r.passed is False and "expected" in r.message

    def test_field_exists_and_missing(self):
        c = _out('{"a": {"b": 1}}')
        assert assert_output_field(c, "a.b").passed
        assert assert_output_field(c, "a.z").passed is False

    def test_field_equals_falsey(self):
        # equals=None / 0 must still compare (sentinel, not None default)
        assert assert_output_field(_out('{"x": null}'), "x", equals=None).passed
        assert assert_output_field(_out('{"x": 0}'), "x", equals=0).passed

    def test_value_in(self):
        c = _out('{"status": "ok"}')
        assert assert_output_value_in(c, "status", ["ok", "error"]).passed
        assert assert_output_value_in(c, "status", ["error"]).passed is False

    def test_value_in_range_inclusive(self):
        c = _out('{"score": 0.8}')
        assert assert_output_value_in_range(c, "score", minimum=0.0, maximum=1.0).passed
        assert assert_output_value_in_range(c, "score", minimum=0.9).passed is False

    def test_value_in_range_exclusive(self):
        c = _out('{"score": 1.0}')
        assert assert_output_value_in_range(c, "score", maximum=1.0).passed
        assert assert_output_value_in_range(c, "score", maximum=1.0, exclusive=True).passed is False

    def test_value_in_range_non_number(self):
        r = assert_output_value_in_range(_out('{"x": "nope"}'), "x", minimum=0)
        assert r.passed is False and "not a number" in r.message

    def test_value_in_range_bool_is_not_number(self):
        r = assert_output_value_in_range(_out('{"x": true}'), "x", minimum=0)
        assert r.passed is False


# ── regex capture groups ─────────────────────────────────────────────────────

class TestMatchGroups:
    def test_positional_groups(self):
        c = _out("order #4521 shipped")
        assert assert_match_groups(c, r"#(\d+)", expected_groups=("4521",)).passed
        assert assert_match_groups(c, r"#(\d+)", expected_groups=("9999",)).passed is False

    def test_named_groups(self):
        c = _out("status=done count=7")
        r = assert_match_groups(c, r"status=(?P<s>\w+)", expected_named={"s": "done"})
        assert r.passed
        assert assert_match_groups(c, r"status=(?P<s>\w+)",
                                   expected_named={"s": "pending"}).passed is False

    def test_no_match(self):
        r = assert_match_groups(_out("nothing here"), r"#(\d+)")
        assert r.passed is False and "does not match" in r.message


# ── tool-arg schema (agent-native crown jewel) ───────────────────────────────

ARGS_SCHEMA = {"type": "object", "required": ["city"],
               "properties": {"city": {"type": "string"}, "units": {"enum": ["c", "f"]}}}


class TestToolArgsSchema:
    def test_conforming_call_passes(self):
        c = _tool_cassette("get_weather", [{"city": "NYC", "units": "f"}])
        assert assert_tool_args_match_schema(c, "get_weather", ARGS_SCHEMA, engine="builtin").passed

    def test_missing_required_arg_fails(self):
        c = _tool_cassette("get_weather", [{"units": "f"}])
        r = assert_tool_args_match_schema(c, "get_weather", ARGS_SCHEMA, engine="builtin")
        assert r.passed is False and "city" in r.message

    def test_enum_violation_fails(self):
        c = _tool_cassette("get_weather", [{"city": "NYC", "units": "kelvin"}])
        r = assert_tool_args_match_schema(c, "get_weather", ARGS_SCHEMA, engine="builtin")
        assert r.passed is False

    def test_which_all_vs_any(self):
        c = _tool_cassette("get_weather", [{"city": "NYC"}, {"units": "f"}])  # 2nd bad
        assert assert_tool_args_match_schema(c, "get_weather", ARGS_SCHEMA,
                                             which="all", engine="builtin").passed is False
        assert assert_tool_args_match_schema(c, "get_weather", ARGS_SCHEMA,
                                             which="any", engine="builtin").passed

    def test_tool_never_called(self):
        c = _tool_cassette("get_weather", [{"city": "NYC"}])
        r = assert_tool_args_match_schema(c, "send_email", ARGS_SCHEMA)
        assert r.passed is False and "never called" in r.message

    def test_invalid_which(self):
        c = _tool_cassette("get_weather", [{"city": "NYC"}])
        with pytest.raises(ValueError, match="which must be"):
            assert_tool_args_match_schema(c, "get_weather", ARGS_SCHEMA, which="some")

    def test_pydantic_tool_schema(self):
        from pydantic import BaseModel

        class WeatherArgs(BaseModel):
            city: str

        c = _tool_cassette("get_weather", [{"city": "NYC"}])
        assert assert_tool_args_match_schema(c, "get_weather", WeatherArgs, engine="builtin").passed


# ── cross-cutting guarantees ─────────────────────────────────────────────────

class TestGuarantees:
    def test_accepts_agentrun(self):
        c = _out(GOOD)
        run = AgentRun(cassette=c)
        assert assert_output_json(run).passed
        assert assert_output_json_schema(run, SCHEMA, engine="builtin").passed
        assert assert_output_field(run, "city", equals="Paris").passed

    def test_deterministic_byte_identical(self):
        c = _out('{"city": "Paris", "temp_c": 999, "status": "ok"}')
        a = assert_output_json_schema(c, SCHEMA, engine="builtin").to_dict()
        b = assert_output_json_schema(c, SCHEMA, engine="builtin").to_dict()
        assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)

    def test_uses_simple_cassette_fixture(self, simple_cassette):
        # the recorded get_weather call has tool_args {"city": "NYC"}
        assert assert_tool_args_match_schema(
            simple_cassette, "get_weather",
            {"type": "object", "required": ["city"]}, engine="builtin",
        ).passed
