"""Guarantee: the *offline* (structural) scorers make no network calls.

These scorers operate purely on recorded cassette data and must run with
zero network access — that is the deterministic, $0 path evalcraft advertises.
We prove it by executing each one inside a ``NetworkGuard`` (which raises
``ReplayNetworkViolation`` on any outgoing socket) and confirming it still
returns an ``AssertionResult``.

The LLM-as-Judge / RAG / pairwise / jury / statistical scorers are
deliberately NOT covered here: they call a real model at evaluation time and
are documented as the *live, paid, non-deterministic* scorer family
(see docs/user-guide/scorers.md).
"""

import pytest

from evalcraft.core.models import AssertionResult
from evalcraft.eval.scorers import (
    assert_cost_under,
    assert_latency_under,
    assert_no_tool_called,
    assert_output_contains,
    assert_output_matches,
    assert_token_count_under,
    assert_tool_called,
    assert_tool_order,
)
from evalcraft.replay.network_guard import NetworkGuard, ReplayNetworkViolation

# (label, scorer-thunk) for every offline / deterministic scorer.
OFFLINE_SCORERS = [
    ("assert_tool_called", lambda c: assert_tool_called(c, "get_weather")),
    ("assert_tool_order", lambda c: assert_tool_order(c, ["get_weather"])),
    ("assert_no_tool_called", lambda c: assert_no_tool_called(c, "delete_database")),
    ("assert_output_contains", lambda c: assert_output_contains(c, "sunny")),
    ("assert_output_matches", lambda c: assert_output_matches(c, r"\d+")),
    ("assert_cost_under", lambda c: assert_cost_under(c, 1.0)),
    ("assert_latency_under", lambda c: assert_latency_under(c, 10_000)),
    ("assert_token_count_under", lambda c: assert_token_count_under(c, 10_000)),
]


@pytest.mark.parametrize(
    "label,scorer", OFFLINE_SCORERS, ids=[s[0] for s in OFFLINE_SCORERS]
)
def test_offline_scorer_makes_no_network_call(label, scorer, simple_cassette):
    """Each offline scorer must run to completion with the network blocked."""
    with NetworkGuard():  # any outgoing socket -> ReplayNetworkViolation
        try:
            result = scorer(simple_cassette)
        except ReplayNetworkViolation as exc:  # pragma: no cover - failure path
            pytest.fail(f"offline scorer {label} attempted a network call: {exc}")
    assert isinstance(result, AssertionResult)
