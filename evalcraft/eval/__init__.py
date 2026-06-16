"""Eval — scorers, judges, and evaluation utilities for agent runs.

All scorers are re-exported here for convenient access::

    from evalcraft.eval import assert_tool_called, assert_output_semantic, assert_faithfulness
"""

# Core scorers (regex/exact-match)
# Hallucination detection
from evalcraft.eval.hallucination import assert_no_hallucination, detect_hallucinations

# Multi-judge consensus
from evalcraft.eval.jury import JuryScorer

# Live eval (run scorers against the real model on a golden input set)
from evalcraft.eval.live import (
    LiveCaseResult,
    LiveEvalCase,
    LiveEvalComparison,
    LiveEvalResult,
    compare_to_baseline,
    run_live_eval,
)

# LLM-as-Judge scorers
from evalcraft.eval.llm_judge import (
    assert_custom_criteria,
    assert_factual_consistency,
    assert_output_semantic,
    assert_tone,
)

# Pairwise comparison
from evalcraft.eval.pairwise import pairwise_compare, pairwise_rank

# RAG evaluation scorers
from evalcraft.eval.rag_scorers import (
    assert_answer_relevance,
    assert_context_recall,
    assert_context_relevance,
    assert_faithfulness,
)
from evalcraft.eval.scorers import (
    Evaluator,
    assert_cost_under,
    assert_latency_under,
    assert_no_tool_called,
    assert_output_contains,
    assert_output_matches,
    assert_token_count_under,
    assert_tool_called,
    assert_tool_order,
)

# Structured-output / tool-arg shape scorers (deterministic, $0)
from evalcraft.eval.scorers.structured import (
    assert_match_groups,
    assert_output_field,
    assert_output_has_keys,
    assert_output_json,
    assert_output_json_schema,
    assert_output_value_in,
    assert_output_value_in_range,
    assert_tool_args_match_schema,
)

# Statistical evaluation
from evalcraft.eval.statistical import eval_n

__all__ = [
    # Core
    "assert_tool_called",
    "assert_tool_order",
    "assert_no_tool_called",
    "assert_output_contains",
    "assert_output_matches",
    "assert_cost_under",
    "assert_latency_under",
    "assert_token_count_under",
    "Evaluator",
    # Structured-output / tool-arg shape (deterministic, $0)
    "assert_output_json",
    "assert_output_json_schema",
    "assert_output_has_keys",
    "assert_output_field",
    "assert_output_value_in",
    "assert_output_value_in_range",
    "assert_match_groups",
    "assert_tool_args_match_schema",
    # LLM-as-Judge
    "assert_output_semantic",
    "assert_factual_consistency",
    "assert_tone",
    "assert_custom_criteria",
    # RAG
    "assert_faithfulness",
    "assert_context_relevance",
    "assert_answer_relevance",
    "assert_context_recall",
    # Pairwise
    "pairwise_compare",
    "pairwise_rank",
    # Statistical
    "eval_n",
    # Jury
    "JuryScorer",
    # Hallucination
    "assert_no_hallucination",
    "detect_hallucinations",
    # Live eval
    "LiveEvalCase",
    "LiveCaseResult",
    "LiveEvalResult",
    "LiveEvalComparison",
    "run_live_eval",
    "compare_to_baseline",
]
