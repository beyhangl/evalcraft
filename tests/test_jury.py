"""Tests for evalcraft.eval.jury — multi-judge consensus scoring."""

from __future__ import annotations

from unittest.mock import patch, call

import pytest

from evalcraft.core.models import AgentRun, Cassette, Span, SpanKind
from evalcraft.eval.jury import JuryScorer, JuryResult, JudgeVote


@pytest.fixture
def cassette():
    c = Cassette(name="jury_test")
    c.output_text = "Paris is the capital of France with 2.1 million people."
    return c


@pytest.fixture
def empty_cassette():
    c = Cassette(name="empty")
    c.output_text = ""
    return c


class TestJuryScorerInit:
    def test_default_judges(self):
        jury = JuryScorer()
        assert len(jury.judges) == 3
        assert jury.threshold == 0.5

    def test_custom_judges(self):
        judges = [
            {"provider": "openai", "model": "gpt-4.1-nano"},
            {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
        ]
        jury = JuryScorer(judges=judges)
        assert len(jury.judges) == 2

    def test_empty_judges_raises(self):
        with pytest.raises(ValueError, match="At least one judge"):
            JuryScorer(judges=[])

    def test_custom_threshold(self):
        jury = JuryScorer(threshold=0.8)
        assert jury.threshold == 0.8


class TestJuryEvaluate:
    @patch("evalcraft.eval.jury._call_judge")
    def test_unanimous_pass(self, mock_judge, cassette):
        mock_judge.return_value = {"pass": True, "reason": "Good", "score": 0.9}

        jury = JuryScorer(judges=[
            {"provider": "openai", "model": "a"},
            {"provider": "openai", "model": "b"},
            {"provider": "openai", "model": "c"},
        ])
        result = jury.evaluate(cassette, criteria="Is it accurate?")

        assert result.passed
        assert result.verdict == "pass"
        assert result.votes_for == 3
        assert result.votes_against == 0
        assert result.agreement == 1.0
        assert result.mean_score == pytest.approx(0.9)
        assert len(result.votes) == 3

    @patch("evalcraft.eval.jury._call_judge")
    def test_unanimous_fail(self, mock_judge, cassette):
        mock_judge.return_value = {"pass": False, "reason": "Bad", "score": 0.1}

        jury = JuryScorer(judges=[
            {"provider": "openai", "model": "a"},
            {"provider": "openai", "model": "b"},
        ])
        result = jury.evaluate(cassette, criteria="test")

        assert not result.passed
        assert result.verdict == "fail"
        assert result.votes_for == 0
        assert result.votes_against == 2

    @patch("evalcraft.eval.jury._call_judge")
    def test_majority_pass(self, mock_judge, cassette):
        mock_judge.side_effect = [
            {"pass": True, "reason": "Good", "score": 0.8},
            {"pass": False, "reason": "Bad", "score": 0.3},
            {"pass": True, "reason": "OK", "score": 0.7},
        ]

        jury = JuryScorer(judges=[
            {"provider": "openai", "model": "a"},
            {"provider": "openai", "model": "b"},
            {"provider": "openai", "model": "c"},
        ])
        result = jury.evaluate(cassette, criteria="test")

        assert result.passed  # 2/3 >= 0.5
        assert result.verdict == "pass"
        assert result.votes_for == 2
        assert result.votes_against == 1

    @patch("evalcraft.eval.jury._call_judge")
    def test_majority_fail_with_high_threshold(self, mock_judge, cassette):
        mock_judge.side_effect = [
            {"pass": True, "reason": "Good", "score": 0.8},
            {"pass": False, "reason": "Bad", "score": 0.3},
            {"pass": True, "reason": "OK", "score": 0.7},
        ]

        jury = JuryScorer(
            judges=[
                {"provider": "openai", "model": "a"},
                {"provider": "openai", "model": "b"},
                {"provider": "openai", "model": "c"},
            ],
            threshold=0.8,  # Need 80% agreement
        )
        result = jury.evaluate(cassette, criteria="test")

        assert not result.passed  # 2/3 = 66% < 80%
        assert result.verdict == "split"

    @patch("evalcraft.eval.jury._call_judge")
    def test_split_verdict(self, mock_judge, cassette):
        mock_judge.side_effect = [
            {"pass": True, "reason": "", "score": 0.8},
            {"pass": False, "reason": "", "score": 0.2},
        ]

        jury = JuryScorer(
            judges=[{"provider": "openai", "model": "a"}, {"provider": "openai", "model": "b"}],
            threshold=0.8,
        )
        result = jury.evaluate(cassette, criteria="test")

        assert not result.passed
        assert result.verdict == "split"
        assert result.agreement == 0.5

    def test_empty_output_fails(self, empty_cassette):
        jury = JuryScorer(judges=[{"provider": "openai", "model": "a"}])
        result = jury.evaluate(empty_cassette, criteria="test")

        assert not result.passed
        assert result.verdict == "fail"

    @patch("evalcraft.eval.jury._call_judge")
    def test_works_with_agent_run(self, mock_judge, cassette):
        mock_judge.return_value = {"pass": True, "reason": "", "score": 1.0}
        run = AgentRun(cassette=cassette)

        jury = JuryScorer(judges=[{"provider": "openai", "model": "a"}])
        result = jury.evaluate(run, criteria="test")
        assert result.passed

    @patch("evalcraft.eval.jury._call_judge")
    def test_passes_provider_and_model_to_judge(self, mock_judge, cassette):
        mock_judge.return_value = {"pass": True, "reason": "", "score": 1.0}

        jury = JuryScorer(judges=[
            {"provider": "anthropic", "model": "claude-haiku-4-5-20251001", "api_key": "sk-test"},
        ])
        jury.evaluate(cassette, criteria="test")

        mock_judge.assert_called_once()
        _, kwargs = mock_judge.call_args
        assert kwargs["provider"] == "anthropic"
        assert kwargs["model"] == "claude-haiku-4-5-20251001"
        assert kwargs["api_key"] == "sk-test"

    @patch("evalcraft.eval.jury._call_judge")
    def test_agreement_calculation(self, mock_judge, cassette):
        # 4 pass, 1 fail → agreement = 4/5 = 0.8
        mock_judge.side_effect = [
            {"pass": True, "reason": "", "score": 0.9},
            {"pass": True, "reason": "", "score": 0.8},
            {"pass": True, "reason": "", "score": 0.85},
            {"pass": True, "reason": "", "score": 0.7},
            {"pass": False, "reason": "", "score": 0.3},
        ]

        jury = JuryScorer(judges=[{"provider": "openai", "model": str(i)} for i in range(5)])
        result = jury.evaluate(cassette, criteria="test")

        assert result.agreement == pytest.approx(0.8)
        assert result.votes_for == 4
        assert result.votes_against == 1


class TestJuryAssertConsensus:
    @patch("evalcraft.eval.jury._call_judge")
    def test_returns_assertion_result(self, mock_judge, cassette):
        mock_judge.return_value = {"pass": True, "reason": "Good", "score": 0.9}

        jury = JuryScorer(judges=[{"provider": "openai", "model": "a"}])
        result = jury.assert_consensus(cassette, criteria="test")

        assert result.passed
        assert "jury_consensus" in result.name
        assert "1/1" in result.actual

    @patch("evalcraft.eval.jury._call_judge")
    def test_failed_consensus_has_message(self, mock_judge, cassette):
        mock_judge.return_value = {"pass": False, "reason": "Bad", "score": 0.1}

        jury = JuryScorer(judges=[{"provider": "openai", "model": "a"}])
        result = jury.assert_consensus(cassette, criteria="test")

        assert not result.passed
        assert "fail" in result.message


class TestJuryResultSerialization:
    def test_to_dict(self):
        result = JuryResult(
            verdict="pass",
            passed=True,
            votes_for=2,
            votes_against=1,
            total_judges=3,
            agreement=0.67,
            mean_score=0.8,
            votes=[
                JudgeVote(provider="openai", model="a", passed=True, score=0.9, reason="Good"),
                JudgeVote(provider="openai", model="b", passed=True, score=0.8, reason="OK"),
                JudgeVote(provider="anthropic", model="c", passed=False, score=0.3, reason="Bad"),
            ],
        )
        d = result.to_dict()

        assert d["verdict"] == "pass"
        assert d["votes_for"] == 2
        assert d["agreement"] == 0.67
        assert len(d["votes"]) == 3
        assert d["votes"][0]["provider"] == "openai"

    def test_judge_vote_to_dict(self):
        vote = JudgeVote(provider="openai", model="gpt-4.1", passed=True, score=0.95, reason="Excellent")
        d = vote.to_dict()
        assert d["provider"] == "openai"
        assert d["model"] == "gpt-4.1"
        assert d["passed"] is True
