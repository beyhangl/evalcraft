"""Field-level tool-call diffs: the same tool, different arguments."""

from __future__ import annotations

import json

from click.testing import CliRunner

from evalcraft import assert_same_tool_calls
from evalcraft.cli.main import cli
from evalcraft.core.models import Cassette, Span, SpanKind
from evalcraft.replay.engine import ReplayDiff
from evalcraft.replay.tool_diff import CONTRACT, INFO, diff_tool_calls


def _run(*calls, output="Your order has shipped."):
    c = Cassette(name="run")
    c.output_text = output
    for name, args, result in calls:
        c.add_span(Span(kind=SpanKind.TOOL_CALL, tool_name=name, tool_args=args,
                        tool_result=result))
    return c


BASE = _run(("lookup_order", {"order_id": "ORDER-123"}, '{"status": "shipped"}'))
WRONG = _run(("lookup_order", {"order_id": "ORDER-999"}, '{"status": "shipped"}'))


class TestDiffToolCalls:
    def test_argument_only_change_is_reported(self):
        d = ReplayDiff.compute(BASE, WRONG)
        # Same tools, same output, same metrics, yet the agent asked for the wrong order.
        assert not d.tool_sequence_changed and not d.output_changed
        assert d.has_changes and d.tool_args_changed
        [change] = d.contract_changes
        assert (change.tool, change.field, change.old, change.new) == (
            "lookup_order", "arguments.order_id", "ORDER-123", "ORDER-999")
        assert "Tool contract changed: lookup_order (call 1)" in d.summary()
        assert 'arguments.order_id: "ORDER-123" → "ORDER-999"' in d.summary()

    def test_identical_runs_have_no_tool_changes(self):
        assert ReplayDiff.compute(BASE, _run(*[("lookup_order", {"order_id": "ORDER-123"},
                                                 '{"status": "shipped"}')])).tool_changes == []

    def test_result_changes_are_info_and_json_strings_compared_structurally(self):
        new = _run(("lookup_order", {"order_id": "ORDER-123"}, '{"status":"delayed"}'))
        [change] = diff_tool_calls(BASE, new)
        assert change.field == "result.status" and change.severity == INFO
        assert change.label == "Tool result changed"
        assert diff_tool_calls(BASE, new, compare_results=False) == []

    def test_nested_added_and_removed_fields(self):
        old = _run(("search", {"q": "x", "filters": {"lang": "en"}}, None))
        new = _run(("search", {"q": "x", "filters": {"region": "eu"}, "limit": 5}, None))
        fields = {(c.field, c.severity) for c in diff_tool_calls(old, new)}
        assert fields == {("arguments.filters.lang", CONTRACT),
                          ("arguments.filters.region", CONTRACT),
                          ("arguments.limit", CONTRACT)}
        missing = next(c for c in diff_tool_calls(old, new) if c.field == "arguments.limit")
        assert "(missing) → 5" in missing.describe()

    def test_list_items_are_indexed(self):
        old = _run(("send", {"to": ["a@x.io", "b@x.io"]}, None))
        new = _run(("send", {"to": ["a@x.io", "c@x.io"]}, None))
        [change] = diff_tool_calls(old, new)
        assert change.field == "arguments.to[1]"

    def test_ignore_patterns(self):
        old = _run(("lookup_order", {"order_id": "1", "request_id": "r1"}, None))
        new = _run(("lookup_order", {"order_id": "1", "request_id": "r2"}, None))
        assert diff_tool_calls(old, new, ignore=["*.arguments.request_id"]) == []
        assert diff_tool_calls(old, new, ignore=["arguments.request_id"]) == []
        assert diff_tool_calls(old, new, ignore=["other.arguments.request_id"]) != []

    def test_runtime_values_are_info(self):
        old = _run(("log", {"at": "2026-10-05T10:00:00Z"}, None))
        new = _run(("log", {"at": "2026-10-06T11:00:00Z"}, None))
        [change] = diff_tool_calls(old, new)
        assert change.severity == INFO and "run-time value" in change.label

    def test_calls_pair_per_tool_in_order(self):
        old = _run(("a", {"n": 1}, None), ("b", {"n": 1}, None), ("a", {"n": 2}, None))
        new = _run(("a", {"n": 1}, None), ("b", {"n": 1}, None), ("a", {"n": 3}, None))
        [change] = diff_tool_calls(old, new)
        assert (change.tool, change.call, change.old, change.new) == ("a", 2, 2, 3)

    def test_to_dict(self):
        data = ReplayDiff.compute(BASE, WRONG).to_dict()
        assert data["tool_args_changed"] is True
        assert data["tool_changes"][0]["field"] == "arguments.order_id"


class TestAssertSameToolCalls:
    def test_fails_with_the_field(self):
        result = assert_same_tool_calls(WRONG, BASE)
        assert not result.passed
        assert 'arguments.order_id: "ORDER-123" → "ORDER-999"' in result.message

    def test_passes_when_equal_and_ignores_results_by_default(self):
        same_args = _run(("lookup_order", {"order_id": "ORDER-123"}, '{"status": "lost"}'))
        assert assert_same_tool_calls(same_args, BASE).passed
        assert not assert_same_tool_calls(same_args, BASE, compare_results=True).passed

    def test_sequence_change_fails(self):
        result = assert_same_tool_calls(_run(), BASE)
        assert not result.passed and "tool sequence" in result.message

    def test_baseline_path(self, tmp_path):
        BASE.save(tmp_path / "base.json")
        assert not assert_same_tool_calls(WRONG, str(tmp_path / "base.json")).passed


class TestCli:
    def _paths(self, tmp_path):
        BASE.save(tmp_path / "a.json")
        WRONG.save(tmp_path / "b.json")
        return str(tmp_path / "a.json"), str(tmp_path / "b.json")

    def test_text_output_and_exit_codes(self, tmp_path):
        a, b = self._paths(tmp_path)
        result = CliRunner().invoke(cli, ["diff", a, b])
        assert result.exit_code == 0
        assert "tool contract changed: lookup_order (call 1)" in result.output
        assert CliRunner().invoke(cli, ["diff", a, b, "--fail-on-contract"]).exit_code == 1
        ignored = CliRunner().invoke(
            cli, ["diff", a, b, "--fail-on-contract", "--ignore", "*.order_id"])
        assert ignored.exit_code == 0, ignored.output

    def test_json(self, tmp_path):
        a, b = self._paths(tmp_path)
        data = json.loads(CliRunner().invoke(cli, ["diff", a, b, "--json"]).output)
        assert data["tool_changes"][0]["new"] == "ORDER-999"
