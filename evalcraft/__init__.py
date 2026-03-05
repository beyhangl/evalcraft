"""Evalcraft — The pytest for AI agents.

Capture, replay, mock, and evaluate agent behavior.
"""

__version__ = "0.1.0"

from evalcraft.capture.recorder import capture, CaptureContext
from evalcraft.replay.engine import replay, ReplayEngine
from evalcraft.mock.llm import MockLLM
from evalcraft.mock.tool import MockTool
from evalcraft.eval.scorers import (
    assert_tool_called,
    assert_tool_order,
    assert_no_tool_called,
    assert_output_contains,
    assert_output_matches,
    assert_cost_under,
    assert_latency_under,
    assert_token_count_under,
)
from evalcraft.core.models import Span, Cassette, AgentRun, EvalResult
from evalcraft.golden.manager import GoldenSet
from evalcraft.regression.detector import RegressionDetector, RegressionReport
from evalcraft.cloud.client import EvalcraftCloud

__all__ = [
    "capture",
    "CaptureContext",
    "replay",
    "ReplayEngine",
    "MockLLM",
    "MockTool",
    "assert_tool_called",
    "assert_tool_order",
    "assert_no_tool_called",
    "assert_output_contains",
    "assert_output_matches",
    "assert_cost_under",
    "assert_latency_under",
    "assert_token_count_under",
    "Span",
    "Cassette",
    "AgentRun",
    "EvalResult",
    "GoldenSet",
    "RegressionDetector",
    "RegressionReport",
    "EvalcraftCloud",
]
