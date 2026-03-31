"""Tests for evalcraft.eval.pairwise — Arena-style A/B comparison."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from evalcraft.core.models import AgentRun, Cassette, Span, SpanKind
from evalcraft.eval.pairwise import (
    PairwiseResult,
    RankingEntry,
    pairwise_compare,
    pairwise_rank,
)


@pytest.fixture
def cassette_a():
    c = Cassette(name="agent_a")
    c.output_text = "Paris is the capital of France with 2.1 million people."
    return c


@pytest.fixture
def cassette_b():
    c = Cassette(name="agent_b")
    c.output_text = "Paris, France's capital, is home to about 2.1M residents and the Eiffel Tower."
    return c


@pytest.fixture
def cassette_c():
    c = Cassette(name="agent_c")
    c.output_text = "I don't know about Paris."
    return c


class TestPairwiseCompare:
    @patch("evalcraft.eval.pairwise._call_pairwise_judge")
    def test_returns_winner_a(self, mock_judge, cassette_a, cassette_b):
        mock_judge.return_value = {"winner": "A", "reason": "More concise", "confidence": 0.85}

        result = pairwise_compare(
            cassette_a, cassette_b,
            criteria="Which is more concise?",
            randomize_order=False,
        )

        assert result.winner == "A"
        assert result.reason == "More concise"
        assert result.confidence == 0.85

    @patch("evalcraft.eval.pairwise._call_pairwise_judge")
    def test_returns_winner_b(self, mock_judge, cassette_a, cassette_b):
        mock_judge.return_value = {"winner": "B", "reason": "More detailed", "confidence": 0.9}

        result = pairwise_compare(
            cassette_a, cassette_b,
            criteria="Which is more informative?",
            randomize_order=False,
        )

        assert result.winner == "B"

    @patch("evalcraft.eval.pairwise._call_pairwise_judge")
    def test_returns_tie(self, mock_judge, cassette_a, cassette_b):
        mock_judge.return_value = {"winner": "tie", "reason": "Equal quality", "confidence": 0.5}

        result = pairwise_compare(cassette_a, cassette_b, criteria="test", randomize_order=False)

        assert result.winner == "tie"

    @patch("evalcraft.eval.pairwise._call_pairwise_judge")
    def test_swap_corrects_winner(self, mock_judge, cassette_a, cassette_b):
        # When swapped, judge sees B as "A" and picks "A" → should map back to "B"
        mock_judge.return_value = {"winner": "A", "reason": "First is better", "confidence": 0.8}

        # Force swap by patching random
        with patch("evalcraft.eval.pairwise.random") as mock_random:
            mock_random.random.return_value = 0.1  # < 0.5, so swapped=True

            result = pairwise_compare(cassette_a, cassette_b, criteria="test")

        assert result.swapped is True
        assert result.winner == "B"  # Corrected from A→B due to swap

    @patch("evalcraft.eval.pairwise._call_pairwise_judge")
    def test_works_with_agent_run(self, mock_judge, cassette_a, cassette_b):
        mock_judge.return_value = {"winner": "A", "reason": "", "confidence": 0.7}
        run_a = AgentRun(cassette=cassette_a)
        run_b = AgentRun(cassette=cassette_b)

        result = pairwise_compare(run_a, run_b, criteria="test", randomize_order=False)
        assert result.winner == "A"

    @patch("evalcraft.eval.pairwise._call_pairwise_judge")
    def test_to_dict(self, mock_judge, cassette_a, cassette_b):
        mock_judge.return_value = {"winner": "A", "reason": "Better", "confidence": 0.9}

        result = pairwise_compare(cassette_a, cassette_b, criteria="test", randomize_order=False)
        d = result.to_dict()

        assert d["winner"] == "A"
        assert d["reason"] == "Better"
        assert d["confidence"] == 0.9


class TestPairwiseRank:
    @patch("evalcraft.eval.pairwise.pairwise_compare")
    def test_ranks_three_cassettes(self, mock_compare, cassette_a, cassette_b, cassette_c):
        # A beats B, A beats C, B beats C
        def side_effect(ca, cb, **kwargs):
            out_a = ca.output_text if hasattr(ca, "output_text") else ca.cassette.output_text
            out_c_text = "I don't know"
            if out_c_text in out_a:
                return PairwiseResult(winner="B", reason="")
            elif hasattr(cb, "output_text") and out_c_text in cb.output_text:
                return PairwiseResult(winner="A", reason="")
            else:
                return PairwiseResult(winner="A", reason="")

        mock_compare.side_effect = side_effect

        rankings = pairwise_rank(
            [cassette_a, cassette_b, cassette_c],
            criteria="Informativeness",
        )

        assert len(rankings) == 3
        assert rankings[0].name == "agent_a"  # 2 wins
        assert rankings[0].wins == 2
        assert rankings[0].score == pytest.approx(1.0)

    @patch("evalcraft.eval.pairwise.pairwise_compare")
    def test_all_ties(self, mock_compare, cassette_a, cassette_b):
        mock_compare.return_value = PairwiseResult(winner="tie", reason="Equal")

        rankings = pairwise_rank([cassette_a, cassette_b], criteria="test")

        assert len(rankings) == 2
        assert all(e.ties == 1 for e in rankings)
        assert all(e.score == 0.0 for e in rankings)

    def test_single_cassette(self, cassette_a):
        rankings = pairwise_rank([cassette_a], criteria="test")
        assert len(rankings) == 1
        assert rankings[0].score == 1.0

    def test_empty_list(self):
        rankings = pairwise_rank([], criteria="test")
        assert rankings == []

    @patch("evalcraft.eval.pairwise.pairwise_compare")
    def test_ranking_entry_to_dict(self, mock_compare, cassette_a, cassette_b):
        mock_compare.return_value = PairwiseResult(winner="A", reason="")

        rankings = pairwise_rank([cassette_a, cassette_b], criteria="test")
        d = rankings[0].to_dict()

        assert "name" in d
        assert "wins" in d
        assert "score" in d
