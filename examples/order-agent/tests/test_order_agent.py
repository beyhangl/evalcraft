"""Offline regression tests for agent.py: real agent code, recorded model replies."""

import os

import pytest
from openai import OpenAI

from agent import run_agent
from evalcraft import assert_cost_under, assert_tool_called


@pytest.mark.evalcraft_playback("tests/cassettes/order_status.json")
def test_answers_order_status(evalcraft_playback):
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "playback"))

    answer = run_agent(client, "Where is ORDER-123?")

    assert "shipped" in answer
    run = evalcraft_playback.cassette  # what the current code just did
    assert assert_tool_called(run, "lookup_order", with_args={"order_id": "ORDER-123"}).passed
    assert assert_cost_under(run, max_usd=0.01).passed
