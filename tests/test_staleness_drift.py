"""Tests for the 0.9 check-stale additions: volatile values, tool drift, model aliases."""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock

from click.testing import CliRunner

from evalcraft.adapters.anthropic_adapter import AnthropicAdapter
from evalcraft.adapters.openai_adapter import OpenAIAdapter
from evalcraft.capture.recorder import CaptureContext
from evalcraft.cli.main import cli
from evalcraft.core.models import Cassette, Provenance, Span, SpanKind
from evalcraft.core.tool_defs import (
    diff_tool_definitions,
    load_tool_definitions,
    normalize_tool_definition,
    normalize_tool_definitions,
    request_metadata,
)
from evalcraft.regression.detector import Severity
from evalcraft.staleness import StalenessChecker, find_alias_moves, find_volatile_values

SEARCH_SCHEMA = {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}
SEARCH_SCHEMA_V2 = {
    "type": "object",
    "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
    "required": ["query"],
}


def _openai_tool(name, description, schema):
    return {"type": "function", "function": {"name": name, "description": description,
                                             "parameters": schema}}


def _anthropic_tool(name, description, schema):
    return {"name": name, "description": description, "input_schema": schema}


def _prov(**kw):
    base = dict(recorded_at=time.time(), sdk_version="0.9.0", python_version="3.12",
                models=["m"], prompt_hash="h")
    base.update(kw)
    return Provenance(**base)


def _cats(report):
    return [f.category for f in report.findings]


# ── volatile values ──────────────────────────────────────────────────────────

class TestVolatileValues:
    def _cassette(self, llm_input="clean", tool_args=None, output="done"):
        c = Cassette(name="v")
        c.add_span(Span(kind=SpanKind.LLM_RESPONSE, model="m", input=llm_input, output=output))
        if tool_args is not None:
            c.add_span(Span(kind=SpanKind.TOOL_CALL, tool_name="save", tool_args=tool_args))
        return c

    def test_uuid_timestamp_and_temp_path_found(self):
        c = self._cassette(
            llm_input="request 3f2b8c1e-9d4a-4b6f-8a2e-1c5d7e9f0a3b sent 2026-09-24T17:12:03Z",
            tool_args={"path": "/var/folders/ab/T/tmpx1/out.csv"},
        )
        found = {(v.kind, v.value, v.where) for v in find_volatile_values(c)}
        assert ("uuid", "3f2b8c1e-9d4a-4b6f-8a2e-1c5d7e9f0a3b", "llm input #1") in found
        assert ("timestamp", "2026-09-24T17:12:03Z", "llm input #1") in found
        assert ("temp_path", "/var/folders/ab/T/tmpx1/out.csv", "tool args: save") in found

    def test_plain_dates_and_numbers_are_not_flagged(self):
        c = self._cassette(llm_input="ships 2026-09-26, order 1726650000, total 42")
        assert find_volatile_values(c) == []

    def test_outputs_are_ignored(self):
        out = "created at 2026-09-24T17:12:03Z id 3f2b8c1e-9d4a-4b6f-8a2e-1c5d7e9f0a3b"
        c = self._cassette(output=out)
        assert find_volatile_values(c) == []

    def test_trailing_punctuation_stripped_and_deduplicated(self):
        c = self._cassette(llm_input="see /tmp/run-1/x.json, then /tmp/run-1/x.json.")
        values = find_volatile_values(c)
        assert [v.value for v in values] == ["/tmp/run-1/x.json"]

    def test_tool_results_fed_back_are_not_flagged(self):
        uid = "3f2b8c1e-9d4a-4b6f-8a2e-1c5d7e9f0a3b"
        c = self._cassette(
            llm_input=f'user: find my order\ntool: {{"order_id": "{uid}", '
                      f'"created_at": "2025-01-02T03:04:05Z"}}',
            tool_args={"order_id": uid},
        )
        assert find_volatile_values(c) == []

    def test_message_list_tool_role_is_skipped(self):
        uid = "3f2b8c1e-9d4a-4b6f-8a2e-1c5d7e9f0a3b"
        c = self._cassette(llm_input=[{"role": "user", "content": "hi"},
                                      {"role": "tool", "content": uid}])
        assert find_volatile_values(c) == []

    def test_value_seen_in_an_output_is_not_flagged(self):
        uid = "3f2b8c1e-9d4a-4b6f-8a2e-1c5d7e9f0a3b"
        c = Cassette(name="v")
        c.add_span(Span(kind=SpanKind.TOOL_CALL, tool_name="create", tool_args={},
                        tool_result={"id": uid}))
        c.add_span(Span(kind=SpanKind.LLM_RESPONSE, model="m", input=f"user: created {uid}"))
        assert find_volatile_values(c) == []

    def test_path_lookalikes_and_windows_temp(self):
        c = self._cassette(llm_input="https://example.com/tmp/r.pdf and /var/tmp/fixture.csv")
        assert find_volatile_values(c) == []
        c = self._cassette(tool_args={"a": r"c:\users\bob\appdata\local\temp\x.txt",
                                      "b": r"D:\a\_temp\y.txt"})
        assert [v.kind for v in find_volatile_values(c)] == ["temp_path", "temp_path"]

    def test_timestamp_without_seconds_and_str_datetime(self):
        c = self._cassette(llm_input="at 2026-09-25T10:30Z and 2026-09-24 17:12:03.123456")
        assert [v.value for v in find_volatile_values(c)] == [
            "2026-09-25T10:30Z", "2026-09-24 17:12:03.123456"]

    def test_checker_warns_even_without_provenance(self):
        c = self._cassette(llm_input="now 2026-09-24 17:12:03")
        report = StalenessChecker().check(c)
        finding = next(f for f in report.findings if f.category == "volatile_content")
        assert finding.severity == Severity.WARNING
        assert not report.has_critical
        assert finding.recorded_value[0]["kind"] == "timestamp"

    def test_clean_cassette_has_no_volatile_finding(self):
        c = self._cassette(llm_input="What is the weather in Paris?", tool_args={"city": "Paris"})
        assert "volatile_content" not in _cats(StalenessChecker().check(c))


# ── tool definitions ─────────────────────────────────────────────────────────

class TestToolDefinitions:
    def test_formats_normalise_to_same_shape(self):
        a = normalize_tool_definition(_openai_tool("search", "Search the web", SEARCH_SCHEMA))
        b = normalize_tool_definition(_anthropic_tool("search", "Search the web", SEARCH_SCHEMA))
        c = normalize_tool_definition({"type": "function", "name": "search",
                                       "description": "Search the web",
                                       "parameters": SEARCH_SCHEMA})
        assert a == b == c
        assert a is not None and a["name"] == "search" and len(a["schema_hash"]) == 16

    def test_hosted_tool_and_junk(self):
        hosted = normalize_tool_definition({"type": "web_search_20250305", "name": "web_search"})
        assert hosted is not None and hosted["name"] == "web_search"
        bumped = normalize_tool_definition({"type": "web_search_20260101", "name": "web_search"})
        assert bumped is not None and bumped["schema_hash"] != hosted["schema_hash"]
        assert normalize_tool_definition({"type": "function"}) is None
        assert normalize_tool_definition("search") is None
        assert normalize_tool_definitions(None) == []

    def test_mcp_input_schema_matches_anthropic(self):
        mcp = normalize_tool_definition({"name": "s", "description": "d",
                                         "inputSchema": SEARCH_SCHEMA})
        assert mcp == normalize_tool_definition(_anthropic_tool("s", "d", SEARCH_SCHEMA))

    def test_strict_flag_counts_as_schema_change(self):
        loose = _openai_tool("s", "d", SEARCH_SCHEMA)
        strict = _openai_tool("s", "d", SEARCH_SCHEMA)
        strict["function"]["strict"] = True
        assert normalize_tool_definition(loose) != normalize_tool_definition(strict)

    def test_cache_control_is_ignored(self):
        cached = _anthropic_tool("s", "d", SEARCH_SCHEMA)
        cached["cache_control"] = {"type": "ephemeral"}
        assert normalize_tool_definition(cached) == normalize_tool_definition(
            _anthropic_tool("s", "d", SEARCH_SCHEMA))

    def test_partial_recorded_entries_do_not_crash_diff(self):
        assert diff_tool_definitions([{"name": "x"}], [{"name": "x"}]) == []

    def test_request_metadata_never_raises(self):
        weird = [_anthropic_tool("s", "d", {1: "a", "b": 2})]
        assert request_metadata({"model": "m", "tools": weird}, "m")["tool_definitions"]

    def test_schema_key_order_does_not_matter(self):
        reordered = {"required": ["q"], "properties": {"q": {"type": "string"}}, "type": "object"}
        a = normalize_tool_definition(_anthropic_tool("s", "d", SEARCH_SCHEMA))
        b = normalize_tool_definition(_anthropic_tool("s", "d", reordered))
        assert a == b

    def test_diff_kinds(self):
        old = normalize_tool_definitions([
            _anthropic_tool("search", "Search. Args: q", SEARCH_SCHEMA),
            _anthropic_tool("fetch", "Fetch a URL", {"type": "object"}),
            _anthropic_tool("gone", "Old tool", {}),
            _anthropic_tool("both", "v1", {"a": 1}),
        ])
        new = normalize_tool_definitions([
            _anthropic_tool("search", "Search. Args: q", SEARCH_SCHEMA_V2),
            _anthropic_tool("fetch", "Fetch a URL and return text", {"type": "object"}),
            _anthropic_tool("new", "New tool", {}),
            _anthropic_tool("both", "v2", {"a": 2}),
        ])
        kinds = {name: kind for kind, name, _ in diff_tool_definitions(old, new)}
        assert kinds == {
            "search": "schema_only",
            "fetch": "description_only",
            "gone": "removed",
            "new": "added",
            "both": "schema_and_description",
        }

    def test_load_accepts_list_or_request_body(self, tmp_path):
        tools = [_openai_tool("search", "d", SEARCH_SCHEMA)]
        p1 = tmp_path / "list.json"
        p1.write_text(json.dumps(tools))
        p2 = tmp_path / "body.json"
        p2.write_text(json.dumps({"model": "gpt-5.1", "tools": tools}))
        assert load_tool_definitions(str(p1)) == load_tool_definitions(str(p2))

    def test_request_metadata(self):
        tools = [_openai_tool("search", "d", SEARCH_SCHEMA)]
        meta = request_metadata({"model": "gpt-4o", "tools": tools}, "gpt-4o-2024-08-06")
        assert meta["requested_model"] == "gpt-4o"
        assert meta["tool_definitions"][0]["name"] == "search"
        assert request_metadata({"model": "gpt-4o"}, "gpt-4o") == {}

    def test_checker_reports_tool_drift(self):
        c = Cassette(name="t")
        c.provenance = _prov(tools=normalize_tool_definitions(
            [_anthropic_tool("search", "Search. Args: q", SEARCH_SCHEMA)]))
        current = normalize_tool_definitions(
            [_anthropic_tool("search", "Search. Args: q", SEARCH_SCHEMA_V2)])
        report = StalenessChecker().check(c, current_tools=current)
        finding = next(f for f in report.findings if f.category == "tool_drift")
        assert finding.severity == Severity.WARNING
        assert finding.metadata["change"] == "schema_only"
        assert "description did not" in finding.message
        assert not report.has_critical

    def test_checker_no_drift_when_identical(self):
        tools = normalize_tool_definitions([_anthropic_tool("search", "d", SEARCH_SCHEMA)])
        c = Cassette(name="t")
        c.provenance = _prov(tools=tools)
        assert StalenessChecker().check(c, current_tools=list(tools)).findings == []

    def test_legacy_cassette_without_tools_is_info(self):
        c = Cassette(name="t")
        c.provenance = _prov()
        report = StalenessChecker().check(c, current_tools=[])
        assert _cats(report) == ["no_tool_definitions"]
        assert report.findings[0].severity == Severity.INFO


# ── model aliases ────────────────────────────────────────────────────────────

class TestModelAliases:
    def test_floating_alias_is_info(self):
        c = Cassette(name="a")
        c.provenance = _prov(models=["gpt-4o-2024-08-06"], requested_models=["gpt-4o"],
                             model_aliases={"gpt-4o": ["gpt-4o-2024-08-06"]})
        report = StalenessChecker().check(c)
        finding = next(f for f in report.findings if f.category == "floating_model_alias")
        assert finding.severity == Severity.INFO
        assert (finding.recorded_value, finding.current_value) == ("gpt-4o", ["gpt-4o-2024-08-06"])

    def test_latest_id_is_info(self):
        c = Cassette(name="a")
        c.provenance = _prov(models=["gemini-flash-latest"])
        assert "floating_model_alias" in _cats(StalenessChecker().check(c))

    def test_alias_in_current_models_is_not_retired(self):
        c = Cassette(name="a")
        c.provenance = _prov(models=["gpt-4o-2024-08-06"], requested_models=["gpt-4o"],
                             model_aliases={"gpt-4o": ["gpt-4o-2024-08-06"]})
        assert not StalenessChecker().check(c, current_models=["gpt-4o"]).has_critical
        # Listing the snapshot you were served also counts.
        assert not StalenessChecker().check(
            c, current_models=["gpt-4o-2024-08-06"]).has_critical
        assert StalenessChecker().check(c, current_models=["gpt-5.1"]).has_critical

    def test_alias_served_two_snapshots_is_not_retired(self):
        c = Cassette(name="a")
        c.provenance = _prov(models=["snap-a", "snap-b"], requested_models=["gpt-4o"],
                             model_aliases={"gpt-4o": ["snap-a", "snap-b"]})
        assert not StalenessChecker().check(c, current_models=["gpt-4o"]).has_critical
        assert len(find_alias_moves([("a", c)])) == 1

    def test_direct_snapshot_call_is_still_checked(self):
        # One span asked for the alias, a sub-agent asked for the snapshot by name.
        c = Cassette(name="a")
        c.provenance = _prov(models=["gpt-4o-2024-08-06"],
                             requested_models=["gpt-4o", "gpt-4o-2024-08-06"],
                             model_aliases={"gpt-4o": ["gpt-4o-2024-08-06"]})
        report = StalenessChecker().check(c, current_models=["gpt-4o"])
        retired = [f.recorded_value for f in report.findings if f.category == "model_retired"]
        assert retired == ["gpt-4o-2024-08-06"]

    def test_legacy_cassette_keeps_exact_matching(self):
        c = Cassette(name="a")
        c.provenance = _prov(models=["gpt-4o-2024-08-06"])
        assert StalenessChecker().check(c, current_models=["gpt-4o"]).has_critical

    def test_alias_moved_across_cassettes(self):
        old, new, same = Cassette(name="old"), Cassette(name="new"), Cassette(name="same")
        old.provenance = _prov(recorded_at=1.0, model_aliases={"gpt-4o": ["gpt-4o-2024-08-06"]})
        new.provenance = _prov(recorded_at=2.0, model_aliases={"gpt-4o": ["gpt-4o-2024-11-20"]})
        same.provenance = _prov(recorded_at=3.0, model_aliases={"claude-x": ["claude-x-1"]})
        findings = find_alias_moves([("new.json", new), ("old.json", old), ("same.json", same),
                                     ("legacy.json", Cassette(name="legacy"))])
        assert len(findings) == 1
        f = findings[0]
        assert f.category == "model_alias_moved" and f.severity == Severity.WARNING
        assert f.current_value == ["gpt-4o-2024-08-06", "gpt-4o-2024-11-20"]
        assert f.metadata["served"]["gpt-4o-2024-11-20"] == ["new.json"]

    def test_no_move_when_consistent(self):
        a, b = Cassette(name="a"), Cassette(name="b")
        a.provenance = _prov(model_aliases={"gpt-4o": ["gpt-4o-2024-08-06"]})
        b.provenance = _prov(model_aliases={"gpt-4o": ["gpt-4o-2024-08-06"]})
        assert find_alias_moves([("a", a), ("b", b)]) == []


# ── provenance round trip + adapters ─────────────────────────────────────────

class TestProvenanceCapture:
    def test_round_trip_and_legacy_shape(self):
        p = _prov(tools=[{"name": "s", "description": "d", "schema_hash": "x"}],
                  requested_models=["a"], model_aliases={"a": ["b"]})
        assert Provenance.from_dict(p.to_dict()) == p
        legacy = _prov().to_dict()
        assert not {"tools", "requested_models", "model_aliases"} & legacy.keys()
        assert Provenance.from_dict(legacy).tools == []
        # requested_models equal to models is not written out.
        assert "requested_models" not in _prov(requested_models=["m"]).to_dict()

    def test_from_dict_tolerates_nulls_and_old_alias_shape(self):
        p = Provenance.from_dict({"models": None, "tools": None, "model_aliases": {"a": "b"},
                                  "prompt_hash": None})
        assert (p.models, p.tools, p.model_aliases, p.prompt_hash) == ([], [], {"a": ["b"]}, "")

    def test_capture_aggregates_span_metadata(self):
        with CaptureContext(name="cap") as ctx:
            ctx.record_llm_call(model="gpt-4o-2024-08-06", input="hi", output="x",
                                metadata={"requested_model": "gpt-4o", "tool_definitions": [
                                    {"name": "b", "description": "", "schema_hash": ""},
                                    {"name": "a", "description": "old", "schema_hash": ""}]})
            ctx.record_llm_call(model="gpt-4o-2024-08-06", input="hi", output="y",
                                metadata={"tool_definitions": [
                                    {"name": "a", "description": "new", "schema_hash": ""}]})
        prov = ctx.cassette.provenance
        assert prov is not None
        assert prov.model_aliases == {"gpt-4o": ["gpt-4o-2024-08-06"]}
        assert prov.requested_models == ["gpt-4o", "gpt-4o-2024-08-06"]
        assert [(t["name"], t["description"]) for t in prov.tools] == [("a", "new"), ("b", "")]

    def test_anthropic_adapter_records_tools_and_requested_model(self):
        response = MagicMock()
        response.model = "claude-sonnet-4-5-20250929"
        response.stop_reason = "end_turn"
        block = MagicMock()
        block.type = "text"
        block.text = "ok"
        response.content = [block]
        response.usage = MagicMock(input_tokens=1, output_tokens=1,
                                   cache_read_input_tokens=0, cache_creation_input_tokens=0)
        kwargs = {"model": "claude-sonnet-4-5", "messages": [{"role": "user", "content": "hi"}],
                  "tools": [_anthropic_tool("search", "d", SEARCH_SCHEMA)]}
        with CaptureContext(name="a") as ctx:
            AnthropicAdapter()._record_response(kwargs, response, 1.0)
        meta = ctx.cassette.spans[0].metadata
        assert meta["requested_model"] == "claude-sonnet-4-5"
        assert meta["tool_definitions"][0]["name"] == "search"
        assert meta["stop_reason"] == "end_turn"
        assert ctx.cassette.provenance is not None
        assert ctx.cassette.provenance.model_aliases == {
            "claude-sonnet-4-5": ["claude-sonnet-4-5-20250929"]}

    def test_openai_adapter_records_tools_and_requested_model(self):
        response = MagicMock()
        response.model = "gpt-4o-2024-08-06"
        response.choices = [MagicMock()]
        response.choices[0].message.tool_calls = None
        response.choices[0].message.content = "ok"
        response.choices[0].finish_reason = "stop"
        response.usage = MagicMock(prompt_tokens=1, completion_tokens=1,
                                   prompt_tokens_details=None)
        kwargs = {"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}],
                  "tools": [_openai_tool("search", "d", SEARCH_SCHEMA)]}
        with CaptureContext(name="o") as ctx:
            OpenAIAdapter()._record_response(kwargs, response, 1.0)
        meta = ctx.cassette.spans[0].metadata
        assert meta["requested_model"] == "gpt-4o"
        assert meta["finish_reason"] == "stop"
        assert ctx.cassette.provenance is not None
        assert [t["name"] for t in ctx.cassette.provenance.tools] == ["search"]


# ── CLI ──────────────────────────────────────────────────────────────────────

class TestCli:
    def _save(self, tmp_path, name, **prov):
        c = Cassette(name=name)
        c.provenance = _prov(**prov)
        path = tmp_path / f"{name}.json"
        c.save(path)
        return str(path)

    def test_tools_option_reports_drift_without_failing(self, tmp_path):
        recorded = normalize_tool_definitions([_anthropic_tool("search", "d", SEARCH_SCHEMA)])
        cass = self._save(tmp_path, "c1", tools=recorded)
        tools_file = tmp_path / "tools.json"
        tools_file.write_text(json.dumps([_anthropic_tool("search", "d", SEARCH_SCHEMA_V2)]))
        result = CliRunner().invoke(cli, ["check-stale", cass, "--tools", str(tools_file)])
        assert result.exit_code == 0, result.output
        assert "tool_drift" in result.output
        assert "description did not" in result.output

    def test_bad_tools_file_is_a_usage_error(self, tmp_path):
        cass = self._save(tmp_path, "c1")
        bad = tmp_path / "tools.json"
        bad.write_text('"nope"')
        result = CliRunner().invoke(cli, ["check-stale", cass, "--tools", str(bad)])
        assert result.exit_code == 2
        assert "--tools" in result.output

    def test_alias_moves_in_text_and_json(self, tmp_path):
        a = self._save(tmp_path, "a", recorded_at=time.time() - 10,
                       model_aliases={"gpt-4o": ["gpt-4o-2024-08-06"]})
        b = self._save(tmp_path, "b", model_aliases={"gpt-4o": ["gpt-4o-2024-11-20"]})
        result = CliRunner().invoke(cli, ["check-stale", a, b])
        assert result.exit_code == 0, result.output
        assert "across cassettes" in result.output and "model_alias_moved" in result.output
        result = CliRunner().invoke(cli, ["check-stale", a, b, "--json"])
        data = json.loads(result.output)
        assert data["across_cassettes"][0]["category"] == "model_alias_moved"
        assert len(data["cassettes"]) == 2
