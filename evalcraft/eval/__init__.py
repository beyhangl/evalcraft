"""Eval — scorers, judges, and evaluation utilities for agent runs.

All scorers are re-exported here for convenient access::

    from evalcraft.eval import assert_tool_called, assert_output_semantic, assert_faithfulness
"""

# Core scorers (regex/exact-match)
from evalcraft.eval.scorers import (
    assert_tool_called,
    assert_tool_order,
    assert_no_tool_called,
    assert_output_contains,
    assert_output_matches,
    assert_cost_under,
    assert_latency_under,
    assert_token_count_under,
    Evaluator,
)

# LLM-as-Judge scorers
from evalcraft.eval.llm_judge import (
    assert_output_semantic,
    assert_factual_consistency,
    assert_tone,
    assert_custom_criteria,
)

# RAG evaluation scorers
from evalcraft.eval.rag_scorers import (
    assert_faithfulness,
    assert_context_relevance,
    assert_answer_relevance,
    assert_context_recall,
)

# Pairwise comparison
from evalcraft.eval.pairwise import pairwise_compare, pairwise_rank

# Statistical evaluation
from evalcraft.eval.statistical import eval_n

# Multi-judge consensus
from evalcraft.eval.jury import JuryScorer

# Hallucination detection
from evalcraft.eval.hallucination import assert_no_hallucination, detect_hallucinations

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
]
