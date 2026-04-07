"""Tests for evalcraft.eval.hallucination — hallucination detection scorer."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from evalcraft.core.models import AgentRun, Cassette
from evalcraft.eval.hallucination import (
    Claim,
    HallucinationResult,
    assert_no_hallucination,
    detect_hallucinations,
)


@pytest.fixture
def faithful_cassette():
    c = Cassette(name="faithful")
    c.output_text = "Paris has a population of 2.1 million and is known for the Eiffel Tower."
    return c


@pytest.fixture
def hallucinating_cassette():
    c = Cassette(name="hallucinating")
    c.output_text = "Paris has 5 million people and the Eiffel Tower is 500m tall."
    return c


@pytest.fixture
def empty_cassette():
    c = Cassette(name="empty")
    c.output_text = ""
    return c


CONTEXT = "Paris has a population of 2.1 million. The Eiffel Tower is 330 meters tall."


class TestDetectHallucinations:
    @patch("evalcraft.eval.hallucination._call_hallucination_judge")
    def test_no_hallucinations(self, mock_judge, faithful_cassette):
        mock_judge.return_value = {
            "claims": [
                {"text": "Paris has 2.1 million people", "supported": True, "reason": "Matches context", "category": "supported"},
                {"text": "Known for the Eiffel Tower", "supported": True, "reason": "Matches context", "category": "supported"},
            ]
        }

        result = detect_hallucinations(faithful_cassette, context=CONTEXT)

        assert result.passed
        assert result.hallucination_rate == 0.0
        assert result.total_claims == 2
        assert result.supported_claims == 2
        assert result.unsupported_claims == 0
        assert len(result.hallucinated_claims) == 0

    @patch("evalcraft.eval.hallucination._call_hallucination_judge")
    def test_all_hallucinated(self, mock_judge, hallucinating_cassette):
        mock_judge.return_value = {
            "claims": [
                {"text": "Paris has 5 million people", "supported": False, "reason": "Context says 2.1 million", "category": "contradicted"},
                {"text": "Eiffel Tower is 500m tall", "supported": False, "reason": "Context says 330m", "category": "contradicted"},
            ]
        }

        result = detect_hallucinations(hallucinating_cassette, context=CONTEXT)

        assert not result.passed
        assert result.hallucination_rate == 1.0
        assert result.unsupported_claims == 2
        assert len(result.hallucinated_claims) == 2

    @patch("evalcraft.eval.hallucination._call_hallucination_judge")
    def test_partial_hallucination(self, mock_judge, hallucinating_cassette):
        mock_judge.return_value = {
            "claims": [
                {"text": "Paris has 5 million people", "supported": False, "reason": "Wrong number", "category": "contradicted"},
                {"text": "Eiffel Tower exists", "supported": True, "reason": "Confirmed", "category": "supported"},
                {"text": "Tower is 500m tall", "supported": False, "reason": "Wrong height", "category": "contradicted"},
            ]
        }

        result = detect_hallucinations(hallucinating_cassette, context=CONTEXT)

        assert not result.passed  # 2/3 = 66% > 50% threshold
        assert result.hallucination_rate == pytest.approx(2 / 3)
        assert result.total_claims == 3
        assert result.supported_claims == 1

    @patch("evalcraft.eval.hallucination._call_hallucination_judge")
    def test_custom_threshold(self, mock_judge, hallucinating_cassette):
        mock_judge.return_value = {
            "claims": [
                {"text": "claim1", "supported": True, "reason": "", "category": "supported"},
                {"text": "claim2", "supported": False, "reason": "", "category": "unsupported"},
            ]
        }

        # 50% hallucination rate
        result = detect_hallucinations(hallucinating_cassette, context=CONTEXT, threshold=0.6)
        assert result.passed  # 50% <= 60%

        result = detect_hallucinations(hallucinating_cassette, context=CONTEXT, threshold=0.3)
        assert not result.passed  # 50% > 30%

    def test_empty_output_passes(self, empty_cassette):
        result = detect_hallucinations(empty_cassette, context=CONTEXT)
        assert result.passed
        assert result.total_claims == 0

    @patch("evalcraft.eval.hallucination._call_hallucination_judge")
    def test_context_as_list(self, mock_judge, faithful_cassette):
        mock_judge.return_value = {
            "claims": [{"text": "claim", "supported": True, "reason": "", "category": "supported"}]
        }

        result = detect_hallucinations(
            faithful_cassette,
            context=["Paris has 2.1 million.", "Eiffel Tower is 330m."],
        )
        assert result.passed

        # Verify the prompt included numbered contexts
        call_args = mock_judge.call_args
        prompt = call_args.args[0]
        assert "Context 1:" in prompt
        assert "Context 2:" in prompt

    @patch("evalcraft.eval.hallucination._call_hallucination_judge")
    def test_works_with_agent_run(self, mock_judge, faithful_cassette):
        mock_judge.return_value = {
            "claims": [{"text": "claim", "supported": True, "reason": "", "category": "supported"}]
        }
        run = AgentRun(cassette=faithful_cassette)

        result = detect_hallucinations(run, context=CONTEXT)
        assert result.passed


class TestAssertNoHallucination:
    @patch("evalcraft.eval.hallucination.detect_hallucinations")
    def test_passes_when_no_hallucination(self, mock_detect, faithful_cassette):
        mock_detect.return_value = HallucinationResult(
            passed=True,
            hallucination_rate=0.0,
            total_claims=2,
            supported_claims=2,
            unsupported_claims=0,
            claims=[
                Claim(text="claim1", supported=True, category="supported"),
                Claim(text="claim2", supported=True, category="supported"),
            ],
        )

        result = assert_no_hallucination(faithful_cassette, context=CONTEXT)

        assert result.passed
        assert result.name == "assert_no_hallucination"
        assert "0%" in result.actual

    @patch("evalcraft.eval.hallucination.detect_hallucinations")
    def test_fails_with_hallucination_details(self, mock_detect, hallucinating_cassette):
        mock_detect.return_value = HallucinationResult(
            passed=False,
            hallucination_rate=1.0,
            total_claims=2,
            supported_claims=0,
            unsupported_claims=2,
            claims=[
                Claim(text="Paris has 5 million", supported=False, category="contradicted", reason="Wrong"),
                Claim(text="Tower is 500m", supported=False, category="contradicted", reason="Wrong"),
            ],
        )

        result = assert_no_hallucination(hallucinating_cassette, context=CONTEXT)

        assert not result.passed
        assert "Paris has 5 million" in result.message
        assert "contradicted" in result.message

    @patch("evalcraft.eval.hallucination.detect_hallucinations")
    def test_truncates_long_message(self, mock_detect, hallucinating_cassette):
        mock_detect.return_value = HallucinationResult(
            passed=False,
            hallucination_rate=1.0,
            total_claims=5,
            supported_claims=0,
            unsupported_claims=5,
            claims=[
                Claim(text=f"claim {i}", supported=False, category="unsupported")
                for i in range(5)
            ],
        )

        result = assert_no_hallucination(hallucinating_cassette, context=CONTEXT)

        assert "... and 2 more" in result.message


class TestHallucinationResultAPI:
    def test_to_dict(self):
        result = HallucinationResult(
            passed=False,
            hallucination_rate=0.5,
            total_claims=4,
            supported_claims=2,
            unsupported_claims=2,
            claims=[
                Claim(text="claim1", supported=True, category="supported"),
                Claim(text="claim2", supported=False, category="contradicted", reason="Wrong"),
            ],
        )
        d = result.to_dict()

        assert d["hallucination_rate"] == 0.5
        assert d["total_claims"] == 4
        assert len(d["claims"]) == 2
        assert d["claims"][1]["category"] == "contradicted"

    def test_hallucinated_claims_property(self):
        result = HallucinationResult(
            passed=False,
            hallucination_rate=0.5,
            total_claims=2,
            supported_claims=1,
            unsupported_claims=1,
            claims=[
                Claim(text="good", supported=True, category="supported"),
                Claim(text="bad", supported=False, category="contradicted"),
            ],
        )
        assert len(result.hallucinated_claims) == 1
        assert result.hallucinated_claims[0].text == "bad"

    def test_claim_to_dict(self):
        claim = Claim(text="Paris is big", supported=True, reason="Confirmed", category="supported")
        d = claim.to_dict()
        assert d["text"] == "Paris is big"
        assert d["supported"] is True
