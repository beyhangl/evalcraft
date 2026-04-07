"""Evalcraft — The pytest for AI agents.

Capture, replay, mock, and evaluate agent behavior.
"""

__version__ = "0.1.0"

from evalcraft.capture.recorder import capture, CaptureContext
from evalcraft.replay.engine import replay, ReplayEngine
from evalcraft.mock.llm import MockLLM
from evalcraft.mock.tool import MockTool
from evalcraft.eval import (
    # Core scorers
    assert_tool_called,
    assert_tool_order,
    assert_no_tool_called,
    assert_output_contains,
    assert_output_matches,
    assert_cost_under,
    assert_latency_under,
    assert_token_count_under,
    # LLM-as-Judge
    assert_output_semantic,
    assert_factual_consistency,
    assert_tone,
    assert_custom_criteria,
    # RAG
    assert_faithfulness,
    assert_context_relevance,
    assert_answer_relevance,
    assert_context_recall,
    # Pairwise
    pairwise_compare,
    pairwise_rank,
    # Statistical
    eval_n,
    # Jury
    JuryScorer,
    # Hallucination
    assert_no_hallucination,
    detect_hallucinations,
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
    "assert_output_semantic",
    "assert_factual_consistency",
    "assert_tone",
    "assert_custom_criteria",
    "assert_faithfulness",
    "assert_context_relevance",
    "assert_answer_relevance",
    "assert_context_recall",
    "pairwise_compare",
    "pairwise_rank",
    "eval_n",
    "JuryScorer",
    "assert_no_hallucination",
    "detect_hallucinations",
    "Span",
    "Cassette",
    "AgentRun",
    "EvalResult",
    "GoldenSet",
    "RegressionDetector",
    "RegressionReport",
    "EvalcraftCloud",
]
