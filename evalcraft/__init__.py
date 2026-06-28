"""Evalcraft — VCR for AI agents.

Record agent runs as cassettes and replay them deterministically in CI for $0;
mock LLMs/tools, score runs, and catch real model drift with live-eval.
"""

__version__ = "0.5.0"

from evalcraft.capture.recorder import CaptureContext, capture
from evalcraft.cloud.client import EvalcraftCloud
from evalcraft.core.models import AgentRun, Cassette, EvalResult, Span
from evalcraft.eval import (
    # Jury
    JuryScorer,
    LiveCaseResult,
    # Live eval
    LiveEvalCase,
    LiveEvalComparison,
    LiveEvalResult,
    # Loop / repetition detection
    LoopFinding,
    LoopReport,
    assert_answer_relevance,
    assert_context_recall,
    assert_context_relevance,
    assert_cost_under,
    assert_custom_criteria,
    assert_factual_consistency,
    # RAG
    assert_faithfulness,
    assert_latency_under,
    # Structured-output / tool-arg shape (deterministic, $0)
    assert_match_groups,
    # Hallucination
    assert_no_hallucination,
    # Loop / repetition detection
    assert_no_loops,
    assert_no_repeated_tool_calls,
    assert_no_tool_called,
    assert_output_contains,
    assert_output_field,
    assert_output_has_keys,
    assert_output_json,
    assert_output_json_schema,
    assert_output_matches,
    # LLM-as-Judge
    assert_output_semantic,
    assert_output_value_in,
    assert_output_value_in_range,
    assert_token_count_under,
    assert_tone,
    # Core scorers
    assert_tool_args_match_schema,
    assert_tool_called,
    assert_tool_order,
    compare_to_baseline,
    detect_hallucinations,
    detect_loops,
    # Statistical
    eval_n,
    # Pairwise
    pairwise_compare,
    pairwise_rank,
    run_live_eval,
)
from evalcraft.golden.manager import GoldenSet
from evalcraft.mock.llm import MockLLM
from evalcraft.mock.tool import MockTool
from evalcraft.regression.detector import RegressionDetector, RegressionReport
from evalcraft.replay.engine import ReplayEngine, replay
from evalcraft.staleness import StalenessChecker, StalenessFinding, StalenessReport

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
    "assert_output_json",
    "assert_output_json_schema",
    "assert_output_has_keys",
    "assert_output_field",
    "assert_output_value_in",
    "assert_output_value_in_range",
    "assert_match_groups",
    "assert_tool_args_match_schema",
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
    "assert_no_loops",
    "assert_no_repeated_tool_calls",
    "detect_loops",
    "LoopFinding",
    "LoopReport",
    "LiveEvalCase",
    "LiveCaseResult",
    "LiveEvalResult",
    "LiveEvalComparison",
    "run_live_eval",
    "compare_to_baseline",
    "Span",
    "Cassette",
    "AgentRun",
    "EvalResult",
    "GoldenSet",
    "RegressionDetector",
    "RegressionReport",
    "StalenessChecker",
    "StalenessFinding",
    "StalenessReport",
    "EvalcraftCloud",
]
