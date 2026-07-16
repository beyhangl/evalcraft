"""Tests for assert_tool_trajectory — deterministic, $0 tool-trajectory matching.

Covers all four modes (strict / unordered / subset / superset), the mode/edge
semantics that distinguish them, error handling, and AgentRun acceptance. No
model is called — every assertion reads only the recorded tool spans.
"""

import pytest

from evalcraft import assert_tool_trajectory
from evalcraft.core.models import AgentRun, Cassette, Span, SpanKind


def _traj(tools: list[str]) -> Cassette:
    c = Cassette(name="t", agent_name="a")
    for t in tools:
        c.add_span(Span(kind=SpanKind.TOOL_CALL, name=f"tool:{t}", tool_name=t,
                        tool_args={}, tool_result={"ok": True}))
    c.output_text = "done"
    return c


REF = ["search", "summarize", "send_email"]


class TestStrict:
    def test_exact_match_passes(self):
        assert assert_tool_trajectory(_traj(REF), REF, mode="strict").passed

    def test_reorder_fails(self):
        r = assert_tool_trajectory(_traj(["summarize", "search", "send_email"]), REF, mode="strict")
        assert r.passed is False and "strict" in r.message

    def test_missing_fails(self):
        r = assert_tool_trajectory(_traj(["search", "summarize"]), REF, mode="strict")
        assert r.passed is False

    def test_extra_fails(self):
        r = assert_tool_trajectory(_traj(REF + ["search"]), REF, mode="strict")
        assert r.passed is False


class TestUnordered:
    def test_same_multiset_any_order_passes(self):
        assert assert_tool_trajectory(
            _traj(["send_email", "search", "summarize"]), REF, mode="unordered"
        ).passed

    def test_count_mismatch_fails(self):
        # extra call of 'search' — multiset differs even though the set matches
        r = assert_tool_trajectory(_traj(["search", "search", "summarize", "send_email"]),
                                   REF, mode="unordered")
        assert r.passed is False
        assert "extra=['search']" in r.message

    def test_missing_reported(self):
        r = assert_tool_trajectory(_traj(["search", "summarize"]), REF, mode="unordered")
        assert r.passed is False and "missing=['send_email']" in r.message


class TestSubset:
    def test_fewer_tools_passes(self):
        # only allowed tools used (a subset) — passes even though it skipped some
        assert assert_tool_trajectory(_traj(["search", "summarize"]), REF, mode="subset").passed

    def test_exact_passes(self):
        assert assert_tool_trajectory(_traj(REF), REF, mode="subset").passed

    def test_unexpected_tool_fails(self):
        r = assert_tool_trajectory(_traj(["search", "delete_db"]), REF, mode="subset")
        assert r.passed is False and "unexpected tool(s)=['delete_db']" in r.message

    def test_repeated_allowed_tool_still_subset(self):
        # subset is set-based: repeats of an allowed tool are fine
        assert assert_tool_trajectory(_traj(["search", "search"]), REF, mode="subset").passed


class TestSuperset:
    def test_all_required_plus_extra_passes(self):
        assert assert_tool_trajectory(_traj(REF + ["log"]), REF, mode="superset").passed

    def test_exact_passes(self):
        assert assert_tool_trajectory(_traj(REF), REF, mode="superset").passed

    def test_missing_required_fails(self):
        r = assert_tool_trajectory(_traj(["search", "summarize", "log"]), REF, mode="superset")
        assert r.passed is False and "missing required tool(s)=['send_email']" in r.message


class TestSemanticsAndEdges:
    def test_modes_are_distinct(self):
        # a reordered-with-extra trajectory: passes superset, fails the other three
        c = _traj(["send_email", "search", "summarize", "log"])
        assert assert_tool_trajectory(c, REF, mode="superset").passed
        assert assert_tool_trajectory(c, REF, mode="strict").passed is False
        assert assert_tool_trajectory(c, REF, mode="unordered").passed is False
        assert assert_tool_trajectory(c, REF, mode="subset").passed is False

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="mode must be one of"):
            assert_tool_trajectory(_traj(REF), REF, mode="loose")

    def test_empty_expected_subset_of_anything(self):
        # no reference tools: superset trivially true; subset only if nothing called
        assert assert_tool_trajectory(_traj(["x"]), [], mode="superset").passed
        assert assert_tool_trajectory(_traj(["x"]), [], mode="subset").passed is False
        assert assert_tool_trajectory(_traj([]), [], mode="strict").passed

    def test_accepts_agent_run(self):
        run = AgentRun(cassette=_traj(REF))
        assert assert_tool_trajectory(run, REF, mode="strict").passed

    def test_actual_and_expected_recorded(self):
        r = assert_tool_trajectory(_traj(["search"]), REF, mode="strict")
        assert r.actual == ["search"] and r.expected == REF
