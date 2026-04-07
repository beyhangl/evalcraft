"""Tests for evalcraft.eval.rag_scorers — RAG evaluation metrics."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from evalcraft.core.models import AgentRun, Cassette, Span, SpanKind
from evalcraft.eval.rag_scorers import (
    _call_rag_judge,
    assert_answer_relevance,
    assert_context_recall,
    assert_context_relevance,
    assert_faithfulness,
)


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

@pytest.fixture
def rag_cassette():
    c = Cassette(name="rag_test", agent_name="rag_agent")
    c.output_text = "Paris has a population of 2.1 million and is known for the Eiffel Tower."
    c.input_text = "Tell me about Paris"
    c.add_span(Span(kind=SpanKind.AGENT_OUTPUT, output=c.output_text))
    return c


@pytest.fixture
def empty_cassette():
    c = Cassette(name="empty")
    c.output_text = ""
    return c


@pytest.fixture
def sample_contexts():
    return [
        "Paris is the capital of France with a population of approximately 2.1 million in the city proper.",
        "The Eiffel Tower was built in 1889 and stands 330 meters tall.",
        "French cuisine is renowned worldwide for its techniques and flavors.",
    ]


# ──────────────────────────────────────────────
# assert_faithfulness
# ──────────────────────────────────────────────

class TestAssertFaithfulness:
    @patch("evalcraft.eval.rag_scorers._call_rag_judge")
    def test_passes_when_faithful(self, mock_judge, rag_cassette, sample_contexts):
        mock_judge.return_value = {
            "pass": True,
            "score": 1.0,
            "reason": "",
            "claims": [
                {"claim": "Paris has a population of 2.1 million", "supported": True},
                {"claim": "Paris is known for the Eiffel Tower", "supported": True},
            ],
        }

        result = assert_faithfulness(rag_cassette, contexts=sample_contexts)

        assert result.passed
        assert result.name == "assert_faithfulness"
        assert "2/2" in result.actual

    @patch("evalcraft.eval.rag_scorers._call_rag_judge")
    def test_fails_when_unfaithful(self, mock_judge, rag_cassette, sample_contexts):
        mock_judge.return_value = {
            "pass": False,
            "score": 0.5,
            "reason": "One claim is unsupported",
            "claims": [
                {"claim": "Paris has a population of 2.1 million", "supported": True},
                {"claim": "fabricated detail", "supported": False},
            ],
        }

        result = assert_faithfulness(rag_cassette, contexts=sample_contexts)

        assert not result.passed
        assert "1/2" in result.actual

    def test_fails_on_empty_output(self, empty_cassette, sample_contexts):
        result = assert_faithfulness(empty_cassette, contexts=sample_contexts)
        assert not result.passed
        assert "no output" in result.message.lower()

    def test_fails_on_empty_contexts(self, rag_cassette):
        result = assert_faithfulness(rag_cassette, contexts=[])
        assert not result.passed
        assert "no contexts" in result.message.lower()

    @patch("evalcraft.eval.rag_scorers._call_rag_judge")
    def test_custom_threshold(self, mock_judge, rag_cassette, sample_contexts):
        mock_judge.return_value = {"pass": True, "score": 0.6, "reason": "", "claims": []}

        result = assert_faithfulness(rag_cassette, contexts=sample_contexts, threshold=0.5)
        assert result.passed

        result = assert_faithfulness(rag_cassette, contexts=sample_contexts, threshold=0.9)
        assert not result.passed

    @patch("evalcraft.eval.rag_scorers._call_rag_judge")
    def test_works_with_agent_run(self, mock_judge, rag_cassette, sample_contexts):
        mock_judge.return_value = {"pass": True, "score": 1.0, "reason": "", "claims": []}
        run = AgentRun(cassette=rag_cassette)

        result = assert_faithfulness(run, contexts=sample_contexts)
        assert result.passed


# ──────────────────────────────────────────────
# assert_context_relevance
# ──────────────────────────────────────────────

class TestAssertContextRelevance:
    @patch("evalcraft.eval.rag_scorers._call_rag_judge")
    def test_passes_when_relevant(self, mock_judge, rag_cassette, sample_contexts):
        mock_judge.return_value = {
            "pass": True,
            "score": 0.67,
            "reason": "",
            "claims": [
                {"claim": "Context about population", "supported": True},
                {"claim": "Context about Eiffel Tower", "supported": True},
                {"claim": "Context about French cuisine", "supported": False},
            ],
        }

        result = assert_context_relevance(
            rag_cassette, query="Tell me about Paris landmarks", contexts=sample_contexts
        )

        # 0.67 < 0.7 default threshold — should fail
        assert not result.passed

    @patch("evalcraft.eval.rag_scorers._call_rag_judge")
    def test_passes_with_lower_threshold(self, mock_judge, rag_cassette, sample_contexts):
        mock_judge.return_value = {
            "pass": True,
            "score": 0.67,
            "reason": "",
            "claims": [
                {"claim": "Context 1", "supported": True},
                {"claim": "Context 2", "supported": True},
                {"claim": "Context 3", "supported": False},
            ],
        }

        result = assert_context_relevance(
            rag_cassette, query="Paris", contexts=sample_contexts, threshold=0.5
        )
        assert result.passed

    def test_fails_on_empty_contexts(self, rag_cassette):
        result = assert_context_relevance(rag_cassette, query="test", contexts=[])
        assert not result.passed

    @patch("evalcraft.eval.rag_scorers._call_rag_judge")
    def test_includes_detail_in_actual(self, mock_judge, rag_cassette, sample_contexts):
        mock_judge.return_value = {
            "pass": True,
            "score": 1.0,
            "reason": "",
            "claims": [
                {"claim": "c1", "supported": True},
                {"claim": "c2", "supported": True},
            ],
        }

        result = assert_context_relevance(
            rag_cassette, query="Paris", contexts=sample_contexts
        )
        assert "2/2 contexts relevant" in result.actual


# ──────────────────────────────────────────────
# assert_answer_relevance
# ──────────────────────────────────────────────

class TestAssertAnswerRelevance:
    @patch("evalcraft.eval.rag_scorers._call_rag_judge")
    def test_passes_when_relevant(self, mock_judge, rag_cassette):
        mock_judge.return_value = {"pass": True, "score": 0.95, "reason": "", "claims": []}

        result = assert_answer_relevance(rag_cassette, query="Tell me about Paris")

        assert result.passed
        assert result.name == "assert_answer_relevance"
        assert "0.95" in result.actual

    @patch("evalcraft.eval.rag_scorers._call_rag_judge")
    def test_fails_when_irrelevant(self, mock_judge, rag_cassette):
        mock_judge.return_value = {
            "pass": False,
            "score": 0.2,
            "reason": "Answer discusses weather instead of Paris",
            "claims": [],
        }

        result = assert_answer_relevance(rag_cassette, query="Tell me about Tokyo")
        assert not result.passed
        assert "weather" in result.message

    def test_fails_on_empty_output(self, empty_cassette):
        result = assert_answer_relevance(empty_cassette, query="test")
        assert not result.passed

    @patch("evalcraft.eval.rag_scorers._call_rag_judge")
    def test_custom_threshold(self, mock_judge, rag_cassette):
        mock_judge.return_value = {"pass": True, "score": 0.6, "reason": "", "claims": []}

        result = assert_answer_relevance(rag_cassette, query="Paris", threshold=0.5)
        assert result.passed

        result = assert_answer_relevance(rag_cassette, query="Paris", threshold=0.9)
        assert not result.passed


# ──────────────────────────────────────────────
# assert_context_recall
# ──────────────────────────────────────────────

class TestAssertContextRecall:
    @patch("evalcraft.eval.rag_scorers._call_rag_judge")
    def test_passes_when_good_recall(self, mock_judge, rag_cassette, sample_contexts):
        mock_judge.return_value = {
            "pass": True,
            "score": 1.0,
            "reason": "",
            "claims": [
                {"claim": "population of 2.1 million", "supported": True},
                {"claim": "known for Eiffel Tower", "supported": True},
            ],
        }

        result = assert_context_recall(
            rag_cassette,
            query="Tell me about Paris",
            contexts=sample_contexts,
            ground_truth="Paris has 2.1 million people and is famous for the Eiffel Tower.",
        )

        assert result.passed
        assert "2/2 facts recalled" in result.actual

    @patch("evalcraft.eval.rag_scorers._call_rag_judge")
    def test_fails_when_poor_recall(self, mock_judge, rag_cassette, sample_contexts):
        mock_judge.return_value = {
            "pass": False,
            "score": 0.33,
            "reason": "Most facts from ground truth not in contexts",
            "claims": [
                {"claim": "fact 1", "supported": True},
                {"claim": "fact 2", "supported": False},
                {"claim": "fact 3", "supported": False},
            ],
        }

        result = assert_context_recall(
            rag_cassette,
            query="test",
            contexts=sample_contexts,
            ground_truth="Extensive facts not in contexts",
        )

        assert not result.passed
        assert "1/3" in result.actual

    def test_fails_on_empty_contexts(self, rag_cassette):
        result = assert_context_recall(
            rag_cassette, query="test", contexts=[], ground_truth="truth"
        )
        assert not result.passed


# ──────────────────────────────────────────────
# _call_rag_judge
# ──────────────────────────────────────────────

class TestCallRagJudge:
    def test_unsupported_provider_raises(self):
        with pytest.raises(ValueError, match="Unsupported.*provider"):
            _call_rag_judge("test", provider="unsupported")

    def test_openai_provider(self):
        import json

        mock_openai = MagicMock()
        msg = MagicMock()
        msg.content = json.dumps({
            "pass": True,
            "score": 0.9,
            "reason": "Good",
            "claims": [{"claim": "test", "supported": True}],
        })
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]
        client = MagicMock()
        client.chat.completions.create.return_value = resp
        mock_openai.OpenAI.return_value = client

        with patch.dict("sys.modules", {"openai": mock_openai}):
            result = _call_rag_judge("test prompt", provider="openai")

        assert result["pass"] is True
        assert result["score"] == 0.9
        assert len(result["claims"]) == 1
